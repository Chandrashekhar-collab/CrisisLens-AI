"""
CrisisLens AI Data Service.

Provides a decoupled, read-only analytical query interface over DuckDB and Parquet.
Enforces explicit separation between Reporting Activity Time (DATEADDED) and
Event Context Date (SQLDATE / event_date).
"""

from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple
import csv
import logging
import pandas as pd

from crisislens.storage.event_store import EventStore
from crisislens.features.baseline import DataReadinessGate, DataReadinessReport
from crisislens.models.baseline import StatisticalBaselineDetector
from crisislens.models.synthetic import generate_synthetic_benchmark_fixture

logger = logging.getLogger(__name__)


class DataService:
    """
    Analytical data service layer for the CrisisLens AI dashboard.
    Executes bounded, read-only SQL queries against DuckDB.
    """

    def __init__(self, db_path: Path, static_data_dir: Optional[Path] = None):
        self.db_path = Path(db_path)
        self.static_data_dir = static_data_dir or (Path(__file__).resolve().parent.parent / "data")
        self._fips_to_iso_cache: Optional[Dict[str, Dict[str, str]]] = None
        self._cameo_lookup_cache: Optional[Dict[str, Dict[str, str]]] = None

    def get_read_only_store(self) -> EventStore:
        """Create a dedicated read-only connection to DuckDB."""
        if not self.db_path.exists():
            raise FileNotFoundError(f"CrisisLens database not found at {self.db_path}. Please run ingestion first.")
        return EventStore(self.db_path, read_only=True)

    def _load_fips_to_iso_map(self) -> Dict[str, Dict[str, str]]:
        """Load static FIPS 10-4 to ISO-3166 cross-reference table."""
        if self._fips_to_iso_cache is not None:
            return self._fips_to_iso_cache

        csv_file = self.static_data_dir / "fips_to_iso.csv"
        mapping = {}
        if csv_file.exists():
            with open(csv_file, mode="r", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    fips = row["fips_code"].strip().upper()
                    mapping[fips] = {
                        "iso2": row["iso2_code"].strip(),
                        "iso3": row["iso3_code"].strip(),
                        "name": row["country_name"].strip(),
                    }
        self._fips_to_iso_cache = mapping
        return mapping

    def _load_cameo_lookup(self) -> Dict[str, Dict[str, str]]:
        """Load static CAMEO event codes lookup table."""
        if self._cameo_lookup_cache is not None:
            return self._cameo_lookup_cache

        csv_file = self.static_data_dir / "cameo_event_codes.csv"
        mapping = {}
        if csv_file.exists():
            with open(csv_file, mode="r", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    code = row["event_code"].strip()
                    mapping[code] = {
                        "root_code": row["root_code"].strip(),
                        "root_name": row["root_name"].strip(),
                        "quad_class": row["quad_class"].strip(),
                        "quad_class_name": row["quad_class_name"].strip(),
                        "description": row["description"].strip(),
                    }
        self._cameo_lookup_cache = mapping
        return mapping

    def get_data_freshness_info(self) -> Dict[str, Any]:
        """
        Inspect the database to report overall data health, row counts, and date bounds.
        Distinguishes:
        - Reporting Activity Time: min/max of try_strptime(CAST(date_added AS VARCHAR), '%Y%m%d%H%M%S')
        - Event Context Date: min/max of event_date (SQLDATE)
        """
        store = self.get_read_only_store()
        try:
            total_events = store.get_total_events_count()
            if total_events == 0:
                return {
                    "has_data": False,
                    "total_events": 0,
                    "min_event_date": None,
                    "max_event_date": None,
                    "min_reporting_time": None,
                    "max_reporting_time": None,
                    "latest_batch_id": None,
                    "latest_ingested_at": None,
                }

            # Query overall bounds
            bounds_sql = """
                SELECT 
                    MIN(event_date) AS min_event_date,
                    MAX(event_date) AS max_event_date,
                    MIN(try_strptime(CAST(date_added AS VARCHAR), '%Y%m%d%H%M%S')) AS min_reporting_time,
                    MAX(try_strptime(CAST(date_added AS VARCHAR), '%Y%m%d%H%M%S')) AS max_reporting_time
                FROM events;
            """
            bounds_df = store.query(bounds_sql)

            # Query latest batch from manifest
            manifest_sql = """
                SELECT batch_id, source_file, completed_at, valid_rows
                FROM ingestion_manifest
                WHERE status = 'SUCCESS'
                ORDER BY completed_at DESC
                LIMIT 1;
            """
            manifest_df = store.query(manifest_sql)

            latest_batch = manifest_df.iloc[0].to_dict() if not manifest_df.empty else {}

            return {
                "has_data": True,
                "total_events": total_events,
                "min_event_date": str(bounds_df["min_event_date"].iloc[0]),
                "max_event_date": str(bounds_df["max_event_date"].iloc[0]),
                "min_reporting_time": str(bounds_df["min_reporting_time"].iloc[0]),
                "max_reporting_time": str(bounds_df["max_reporting_time"].iloc[0]),
                "latest_batch_id": latest_batch.get("batch_id"),
                "latest_source_file": latest_batch.get("source_file"),
                "latest_ingested_at": str(latest_batch.get("completed_at")),
            }
        finally:
            store.close()

    def get_overview_summary_metrics(
        self,
        date_start: Optional[str] = None,
        date_end: Optional[str] = None,
        use_reporting_time: bool = False,
    ) -> Dict[str, Any]:
        """
        Compute high-level summary KPIs:
        Total Events, Active Countries, Conflict Ratio, Avg Goldstein, and Top Actor.
        """
        store = self.get_read_only_store()
        try:
            where_clauses = ["1=1"]
            params: List[Any] = []

            date_field = (
                "CAST(try_strptime(CAST(date_added AS VARCHAR), '%Y%m%d%H%M%S') AS DATE)"
                if use_reporting_time
                else "event_date"
            )

            if date_start:
                where_clauses.append(f"{date_field} >= ?")
                params.append(date_start)
            if date_end:
                where_clauses.append(f"{date_field} <= ?")
                params.append(date_end)

            sql = f"""
                SELECT 
                    COUNT(*) AS total_events,
                    COUNT(DISTINCT NULLIF(action_country, '')) AS distinct_countries,
                    COUNT(CASE WHEN quad_class IN (3, 4) THEN 1 END) AS conflict_events,
                    AVG(goldstein_scale) AS avg_goldstein,
                    AVG(avg_tone) AS avg_tone
                FROM events
                WHERE {' AND '.join(where_clauses)};
            """
            df = store.query(sql, params)
            if df.empty or df["total_events"].iloc[0] == 0:
                return {
                    "total_events": 0,
                    "distinct_countries": 0,
                    "conflict_events": 0,
                    "conflict_ratio_pct": 0.0,
                    "avg_goldstein": 0.0,
                    "avg_tone": 0.0,
                    "top_actor": "N/A",
                }

            total = int(df["total_events"].iloc[0])
            conflict = int(df["conflict_events"].iloc[0])
            conflict_pct = round((conflict / total * 100.0), 1) if total > 0 else 0.0
            avg_goldstein = round(float(df["avg_goldstein"].iloc[0] or 0.0), 2)
            avg_tone = round(float(df["avg_tone"].iloc[0] or 0.0), 2)
            countries = int(df["distinct_countries"].iloc[0])

            # Query top actor
            actor_sql = f"""
                SELECT actor1_name, COUNT(*) AS cnt
                FROM events
                WHERE {' AND '.join(where_clauses)}
                  AND actor1_name IS NOT NULL AND TRIM(actor1_name) != ''
                GROUP BY 1
                ORDER BY cnt DESC
                LIMIT 1;
            """
            actor_df = store.query(actor_sql, params)
            top_actor = actor_df["actor1_name"].iloc[0] if not actor_df.empty else "N/A"

            return {
                "total_events": total,
                "distinct_countries": countries,
                "conflict_events": conflict,
                "conflict_ratio_pct": conflict_pct,
                "avg_goldstein": avg_goldstein,
                "avg_tone": avg_tone,
                "top_actor": top_actor,
            }
        finally:
            store.close()

    def get_activity_trend(
        self,
        date_start: Optional[str] = None,
        date_end: Optional[str] = None,
        use_reporting_time: bool = False,
    ) -> pd.DataFrame:
        """
        Aggregate event counts and QuadClass breakdown over time.
        """
        store = self.get_read_only_store()
        try:
            where_clauses = ["1=1"]
            params: List[Any] = []

            if use_reporting_time:
                date_expr = "CAST(try_strptime(CAST(date_added AS VARCHAR), '%Y%m%d%H%M%S') AS DATE)"
            else:
                date_expr = "event_date"

            if date_start:
                where_clauses.append(f"{date_expr} >= ?")
                params.append(date_start)
            if date_end:
                where_clauses.append(f"{date_expr} <= ?")
                params.append(date_end)

            sql = f"""
                SELECT 
                    {date_expr} AS time_bucket,
                    COUNT(*) AS total_events,
                    COUNT(CASE WHEN quad_class = 1 THEN 1 END) AS verbal_coop,
                    COUNT(CASE WHEN quad_class = 2 THEN 1 END) AS material_coop,
                    COUNT(CASE WHEN quad_class = 3 THEN 1 END) AS verbal_conflict,
                    COUNT(CASE WHEN quad_class = 4 THEN 1 END) AS material_conflict,
                    AVG(goldstein_scale) AS mean_goldstein
                FROM events
                WHERE {' AND '.join(where_clauses)}
                  AND {date_expr} IS NOT NULL
                GROUP BY 1
                ORDER BY 1 ASC;
            """
            df = store.query(sql, params)
            if df.empty:
                return pd.DataFrame()

            df["time_bucket"] = pd.to_datetime(df["time_bucket"]).dt.strftime("%Y-%m-%d")
            return df
        finally:
            store.close()

    def get_country_distribution(
        self,
        date_start: Optional[str] = None,
        date_end: Optional[str] = None,
        use_reporting_time: bool = False,
        limit: int = 15,
    ) -> pd.DataFrame:
        """
        Aggregate top countries by event volume and map to ISO names and ISO-3 codes.
        """
        store = self.get_read_only_store()
        try:
            where_clauses = ["action_country IS NOT NULL AND TRIM(action_country) != ''"]
            params: List[Any] = []

            date_field = (
                "CAST(try_strptime(CAST(date_added AS VARCHAR), '%Y%m%d%H%M%S') AS DATE)"
                if use_reporting_time
                else "event_date"
            )

            if date_start:
                where_clauses.append(f"{date_field} >= ?")
                params.append(date_start)
            if date_end:
                where_clauses.append(f"{date_field} <= ?")
                params.append(date_end)

            sql = f"""
                SELECT 
                    action_country,
                    COUNT(*) AS total_events,
                    COUNT(CASE WHEN quad_class IN (3, 4) THEN 1 END) AS conflict_events
                FROM events
                WHERE {' AND '.join(where_clauses)}
                GROUP BY 1
                ORDER BY total_events DESC
                LIMIT ?;
            """
            params.append(limit)
            df = store.query(sql, params)
            if df.empty:
                return pd.DataFrame()

            # Enrich with ISO mapping
            iso_map = self._load_fips_to_iso_map()
            names = []
            iso3_codes = []

            for fips in df["action_country"]:
                entry = iso_map.get(str(fips).strip().upper(), {})
                names.append(entry.get("name", fips))
                iso3_codes.append(entry.get("iso3", fips))

            df["country_name"] = names
            df["iso3"] = iso3_codes
            return df
        finally:
            store.close()

    def get_quad_class_distribution(
        self,
        date_start: Optional[str] = None,
        date_end: Optional[str] = None,
        use_reporting_time: bool = False,
    ) -> pd.DataFrame:
        """
        Return event count by QuadClass with official CAMEO labels and standard colors.
        """
        store = self.get_read_only_store()
        try:
            where_clauses = ["quad_class IN (1, 2, 3, 4)"]
            params: List[Any] = []

            date_field = (
                "CAST(try_strptime(CAST(date_added AS VARCHAR), '%Y%m%d%H%M%S') AS DATE)"
                if use_reporting_time
                else "event_date"
            )

            if date_start:
                where_clauses.append(f"{date_field} >= ?")
                params.append(date_start)
            if date_end:
                where_clauses.append(f"{date_field} <= ?")
                params.append(date_end)

            sql = f"""
                SELECT 
                    quad_class,
                    COUNT(*) AS event_count
                FROM events
                WHERE {' AND '.join(where_clauses)}
                GROUP BY 1
                ORDER BY quad_class ASC;
            """
            df = store.query(sql, params)
            if df.empty:
                return pd.DataFrame()

            label_map = {
                1: "Verbal Cooperation",
                2: "Material Cooperation",
                3: "Verbal Conflict",
                4: "Material Conflict",
            }
            color_map = {
                1: "#2196F3",  # Blue
                2: "#4CAF50",  # Green
                3: "#FF9800",  # Orange
                4: "#F44336",  # Red
            }
            df["quad_class_name"] = df["quad_class"].map(label_map)
            df["color"] = df["quad_class"].map(color_map)
            return df
        finally:
            store.close()

    def get_recent_events_feed(self, limit: int = 25) -> pd.DataFrame:
        """
        Retrieve recent records ordered by GDELT reporting time (date_added DESC).
        """
        store = self.get_read_only_store()
        try:
            sql = """
                SELECT 
                    event_id,
                    strftime(try_strptime(CAST(date_added AS VARCHAR), '%Y%m%d%H%M%S'), '%Y-%m-%d %H:%M') AS reporting_time,
                    event_date,
                    actor1_name,
                    actor2_name,
                    event_code,
                    quad_class,
                    goldstein_scale,
                    action_country,
                    action_geo_name,
                    source_url
                FROM events
                ORDER BY date_added DESC, event_id DESC
                LIMIT ?;
            """
            df = store.query(sql, [limit])
            return df
        finally:
            store.close()

    def query_explorer_events(
        self,
        date_start: Optional[str] = None,
        date_end: Optional[str] = None,
        country: Optional[str] = None,
        quad_classes: Optional[List[int]] = None,
        event_root_code: Optional[str] = None,
        search_text: Optional[str] = None,
        goldstein_min: Optional[float] = None,
        goldstein_max: Optional[float] = None,
        min_mentions: Optional[int] = None,
        use_reporting_time: bool = False,
        page: int = 1,
        page_size: int = 50,
    ) -> Tuple[pd.DataFrame, int]:
        """
        Execute a bounded, paginated search query across event records.
        Returns:
            (records_page_df, total_matching_count)
        """
        store = self.get_read_only_store()
        try:
            where_clauses = ["1=1"]
            params: List[Any] = []

            date_field = (
                "CAST(try_strptime(CAST(date_added AS VARCHAR), '%Y%m%d%H%M%S') AS DATE)"
                if use_reporting_time
                else "event_date"
            )

            if date_start:
                where_clauses.append(f"{date_field} >= ?")
                params.append(date_start)
            if date_end:
                where_clauses.append(f"{date_field} <= ?")
                params.append(date_end)

            if country and country != "ALL":
                where_clauses.append("action_country = ?")
                params.append(country)

            if quad_classes:
                placeholders = ", ".join(["?"] * len(quad_classes))
                where_clauses.append(f"quad_class IN ({placeholders})")
                params.extend(quad_classes)

            if event_root_code and event_root_code != "ALL":
                where_clauses.append("event_root_code = ?")
                params.append(str(event_root_code))

            if goldstein_min is not None:
                where_clauses.append("goldstein_scale >= ?")
                params.append(goldstein_min)

            if goldstein_max is not None:
                where_clauses.append("goldstein_scale <= ?")
                params.append(goldstein_max)

            if min_mentions is not None and min_mentions > 0:
                where_clauses.append("num_mentions >= ?")
                params.append(min_mentions)

            if search_text and search_text.strip():
                term = f"%{search_text.strip().lower()}%"
                where_clauses.append("""(
                    LOWER(COALESCE(actor1_name, '')) LIKE ? OR
                    LOWER(COALESCE(actor2_name, '')) LIKE ? OR
                    LOWER(COALESCE(action_geo_name, '')) LIKE ? OR
                    LOWER(COALESCE(source_url, '')) LIKE ?
                )""")
                params.extend([term, term, term, term])

            where_sql = " AND ".join(where_clauses)

            # 1. Total matching count
            count_sql = f"SELECT COUNT(*) AS total FROM events WHERE {where_sql};"
            count_df = store.query(count_sql, list(params))
            total_count = int(count_df["total"].iloc[0]) if not count_df.empty else 0

            if total_count == 0:
                return pd.DataFrame(), 0

            # 2. Paginated rows
            offset = max(0, (page - 1) * page_size)
            page_sql = f"""
                SELECT 
                    event_id,
                    event_date,
                    strftime(try_strptime(CAST(date_added AS VARCHAR), '%Y%m%d%H%M%S'), '%Y-%m-%d %H:%M') AS reporting_time,
                    actor1_name,
                    actor2_name,
                    event_code,
                    quad_class,
                    goldstein_scale,
                    num_mentions,
                    action_country,
                    action_geo_name,
                    source_url
                FROM events
                WHERE {where_sql}
                ORDER BY event_date DESC, event_id DESC
                LIMIT ? OFFSET ?;
            """
            page_params = list(params) + [page_size, offset]
            page_df = store.query(page_sql, page_params)

            return page_df, total_count
        finally:
            store.close()

    def get_event_detail(self, event_id: int) -> Optional[Dict[str, Any]]:
        """
        Retrieve complete record for a single event_id enriched with taxonomy labels.
        """
        store = self.get_read_only_store()
        try:
            sql = "SELECT * FROM events WHERE event_id = ?;"
            df = store.query(sql, [event_id])
            if df.empty:
                return None

            rec = df.iloc[0].to_dict()

            # Enrich with CAMEO taxonomy
            cameo_map = self._load_cameo_lookup()
            code_str = str(rec.get("event_code", "")).strip()
            cameo_info = cameo_map.get(code_str, {})
            rec["cameo_description"] = cameo_info.get("description", "Unknown CAMEO event")
            rec["cameo_root_name"] = cameo_info.get("root_name", "Unknown Root")

            # Enrich with FIPS country lookup
            iso_map = self._load_fips_to_iso_map()
            fips = str(rec.get("action_country", "")).strip().upper()
            country_info = iso_map.get(fips, {})
            rec["country_full_name"] = country_info.get("name", fips)
            rec["iso3_code"] = country_info.get("iso3", fips)

            # Friendly QuadClass
            quad_names = {
                1: "Verbal Cooperation",
                2: "Material Cooperation",
                3: "Verbal Conflict",
                4: "Material Conflict",
            }
            rec["quad_class_name"] = quad_names.get(rec.get("quad_class"), "Unknown")

            return rec
        finally:
            store.close()

    def get_filter_options(self) -> Dict[str, Any]:
        """
        Retrieve available distinct countries and event codes from current dataset.
        """
        store = self.get_read_only_store()
        try:
            country_sql = """
                SELECT DISTINCT action_country 
                FROM events 
                WHERE action_country IS NOT NULL AND TRIM(action_country) != ''
                ORDER BY action_country ASC;
            """
            countries = store.query(country_sql)["action_country"].tolist()

            root_codes_sql = """
                SELECT DISTINCT event_root_code 
                FROM events 
                WHERE event_root_code IS NOT NULL AND TRIM(event_root_code) != ''
                ORDER BY event_root_code ASC;
            """
            root_codes = store.query(root_codes_sql)["event_root_code"].tolist()

            return {
                "countries": countries,
                "root_codes": root_codes,
            }
        finally:
            store.close()

    def check_data_readiness(self, min_intervals: int = 28) -> DataReadinessReport:
        """
        Evaluate DuckDB reporting time coverage to determine whether statistical
        baseline anomaly detection can be run safely against live data.
        """
        store = self.get_read_only_store()
        try:
            total_events = store.get_total_events_count()
            if total_events == 0:
                gate = DataReadinessGate(min_intervals=min_intervals)
                return gate.evaluate(pd.DataFrame(), time_col="timestamp")

            sql = """
                SELECT 
                    time_bucket(INTERVAL '15 minutes', try_strptime(CAST(date_added AS VARCHAR), '%Y%m%d%H%M%S')) AS timestamp,
                    COUNT(*) AS event_count
                FROM events
                WHERE date_added IS NOT NULL
                GROUP BY timestamp
                ORDER BY timestamp ASC;
            """
            df_buckets = store.query(sql)
            gate = DataReadinessGate(min_intervals=min_intervals)
            return gate.evaluate(df_buckets, time_col="timestamp")
        finally:
            store.close()

    def get_reporting_time_series(
        self,
        interval_minutes: int = 15,
        country: Optional[str] = None,
        quad_class: Optional[int] = None,
    ) -> pd.DataFrame:
        """
        Extract regularized reporting time series from events table.
        """
        store = self.get_read_only_store()
        try:
            where_clauses = ["date_added IS NOT NULL"]
            params: List[Any] = []

            if country:
                where_clauses.append("action_country = ?")
                params.append(country)
            if quad_class is not None:
                where_clauses.append("quad_class = ?")
                params.append(quad_class)

            sql = f"""
                SELECT 
                    time_bucket(INTERVAL '{interval_minutes} minutes', try_strptime(CAST(date_added AS VARCHAR), '%Y%m%d%H%M%S')) AS timestamp,
                    COUNT(*) AS event_count
                FROM events
                WHERE {' AND '.join(where_clauses)}
                GROUP BY timestamp
                ORDER BY timestamp ASC;
            """
            return store.query(sql, params)
        finally:
            store.close()

    def get_synthetic_benchmark_series(
        self,
        days: int = 14,
        interval_minutes: int = 60,
        seed: int = 42,
    ) -> pd.DataFrame:
        """
        Retrieve deterministic synthetic benchmark event series.
        """
        return generate_synthetic_benchmark_fixture(
            days=days,
            interval_minutes=interval_minutes,
            seed=seed,
        )

    def detect_anomalies(
        self,
        source: str = "benchmark",
        window_size: int = 24,
        min_history: int = 12,
        zscore_threshold: float = 2.5,
        iqr_multiplier: float = 1.5,
        country: Optional[str] = None,
        quad_class: Optional[int] = None,
    ) -> Tuple[pd.DataFrame, DataReadinessReport]:
        """
        Run statistical baseline anomaly detection against either live GDELT data (gated)
        or the deterministic synthetic benchmark fixture.
        """
        detector = StatisticalBaselineDetector(
            window_size=window_size,
            min_history=min_history,
            zscore_threshold=zscore_threshold,
            iqr_multiplier=iqr_multiplier,
        )

        if source == "live":
            report = self.check_data_readiness(min_intervals=28)
            df_series = self.get_reporting_time_series(country=country, quad_class=quad_class)
            if not report.can_score_live:
                return df_series, report

            scored = detector.fit_detect(df_series, time_col="timestamp", count_col="event_count")
            return scored, report
        else:
            df_benchmark = self.get_synthetic_benchmark_series()
            gate = DataReadinessGate(min_intervals=28)
            report = gate.evaluate(df_benchmark, time_col="timestamp")
            scored = detector.fit_detect(df_benchmark, time_col="timestamp", count_col="event_count")
            return scored, report

    def get_available_reporting_intervals(self, limit: int = 100) -> List[Dict[str, Any]]:
        """
        Retrieve distinct reporting time intervals (from date_added) available in DuckDB.
        """
        store = self.get_read_only_store()
        try:
            sql = """
                SELECT 
                    date_added,
                    strftime(try_strptime(CAST(date_added AS VARCHAR), '%Y%m%d%H%M%S'), '%Y-%m-%d %H:%M') AS formatted_time,
                    COUNT(*) AS event_count
                FROM events
                WHERE date_added IS NOT NULL
                GROUP BY date_added
                ORDER BY date_added DESC
                LIMIT ?;
            """
            df = store.query(sql, [limit])
            if df.empty:
                return []
            return df.to_dict(orient="records")
        finally:
            store.close()

    def query_investigation_events(
        self,
        interval_date_added: Optional[int] = None,
        date_start: Optional[str] = None,
        date_end: Optional[str] = None,
        country: Optional[str] = None,
        quad_classes: Optional[List[int]] = None,
        search_text: Optional[str] = None,
        goldstein_min: Optional[float] = None,
        goldstein_max: Optional[float] = None,
        use_reporting_time: bool = True,
        page: int = 1,
        page_size: int = 50,
        max_rows: int = 5000,
    ) -> Tuple[pd.DataFrame, int]:
        """
        Execute bounded, parameterized queries specifically tailored for event drill-down investigation.
        """
        store = self.get_read_only_store()
        try:
            where_clauses = ["1=1"]
            params: List[Any] = []

            # Exact interval match (date_added) if specified
            if interval_date_added is not None:
                where_clauses.append("date_added = ?")
                params.append(interval_date_added)

            # Date boundaries
            date_field = (
                "CAST(try_strptime(CAST(date_added AS VARCHAR), '%Y%m%d%H%M%S') AS DATE)"
                if use_reporting_time
                else "event_date"
            )

            if date_start:
                where_clauses.append(f"{date_field} >= ?")
                params.append(date_start)
            if date_end:
                where_clauses.append(f"{date_field} <= ?")
                params.append(date_end)

            if country and country != "ALL":
                where_clauses.append("action_country = ?")
                params.append(country)

            if quad_classes:
                placeholders = ", ".join(["?"] * len(quad_classes))
                where_clauses.append(f"quad_class IN ({placeholders})")
                params.extend(quad_classes)

            if goldstein_min is not None:
                where_clauses.append("goldstein_scale >= ?")
                params.append(float(goldstein_min))

            if goldstein_max is not None:
                where_clauses.append("goldstein_scale <= ?")
                params.append(float(goldstein_max))

            if search_text and search_text.strip():
                term = f"%{search_text.strip().lower()}%"
                where_clauses.append("""(
                    LOWER(COALESCE(actor1_name, '')) LIKE ? OR
                    LOWER(COALESCE(actor2_name, '')) LIKE ? OR
                    LOWER(COALESCE(action_geo_name, '')) LIKE ? OR
                    LOWER(COALESCE(source_url, '')) LIKE ?
                )""")
                params.extend([term, term, term, term])

            where_sql = " AND ".join(where_clauses)

            # 1. Total count
            count_sql = f"SELECT COUNT(*) AS total FROM events WHERE {where_sql};"
            count_df = store.query(count_sql, list(params))
            total_count = int(count_df["total"].iloc[0]) if not count_df.empty else 0

            if total_count == 0:
                return pd.DataFrame(), 0

            # 2. Paginated rows
            offset = max(0, (page - 1) * page_size)
            page_sql = f"""
                SELECT 
                    event_id,
                    event_date,
                    strftime(try_strptime(CAST(date_added AS VARCHAR), '%Y%m%d%H%M%S'), '%Y-%m-%d %H:%M') AS reporting_time,
                    actor1_name,
                    actor2_name,
                    event_code,
                    quad_class,
                    goldstein_scale,
                    num_mentions,
                    action_country,
                    action_geo_name,
                    source_url,
                    date_added
                FROM events
                WHERE {where_sql}
                ORDER BY num_mentions DESC, event_id ASC
                LIMIT ? OFFSET ?;
            """
            query_params = list(params) + [min(page_size, max_rows), offset]
            df = store.query(page_sql, query_params)

            # Enrich with friendly country and QuadClass names
            iso_map = self._load_fips_to_iso_map()
            df["country_name"] = df["action_country"].apply(lambda c: iso_map.get(str(c).upper(), {}).get("name", c))

            quad_map = {
                1: "Verbal Cooperation",
                2: "Material Cooperation",
                3: "Verbal Conflict",
                4: "Material Conflict",
            }
            df["quad_class_name"] = df["quad_class"].map(quad_map)
            return df, total_count
        finally:
            store.close()

    def get_investigation_interval_stats(
        self,
        interval_date_added: Optional[int] = None,
        date_start: Optional[str] = None,
        date_end: Optional[str] = None,
        country: Optional[str] = None,
        use_reporting_time: bool = True,
    ) -> Dict[str, Any]:
        """
        Aggregate analytical breakdown metrics for an investigated interval.
        """
        store = self.get_read_only_store()
        try:
            where_clauses = ["1=1"]
            params: List[Any] = []

            if interval_date_added is not None:
                where_clauses.append("date_added = ?")
                params.append(interval_date_added)

            date_field = (
                "CAST(try_strptime(CAST(date_added AS VARCHAR), '%Y%m%d%H%M%S') AS DATE)"
                if use_reporting_time
                else "event_date"
            )

            if date_start:
                where_clauses.append(f"{date_field} >= ?")
                params.append(date_start)
            if date_end:
                where_clauses.append(f"{date_field} <= ?")
                params.append(date_end)

            if country and country != "ALL":
                where_clauses.append("action_country = ?")
                params.append(country)

            where_sql = " AND ".join(where_clauses)

            # High-level KPIs
            kpi_sql = f"""
                SELECT 
                    COUNT(*) AS total_events,
                    COUNT(DISTINCT NULLIF(action_country, '')) AS distinct_countries,
                    COUNT(CASE WHEN quad_class IN (3, 4) THEN 1 END) AS conflict_events,
                    AVG(goldstein_scale) AS avg_goldstein,
                    AVG(avg_tone) AS avg_tone
                FROM events
                WHERE {where_sql};
            """
            kpi_df = store.query(kpi_sql, list(params))
            if kpi_df.empty or kpi_df["total_events"].iloc[0] == 0:
                return {
                    "total_events": 0,
                    "distinct_countries": 0,
                    "conflict_events": 0,
                    "conflict_ratio_pct": 0.0,
                    "avg_goldstein": 0.0,
                    "avg_tone": 0.0,
                    "top_actors": [],
                    "top_cameo_roots": [],
                    "top_countries": [],
                }

            total = int(kpi_df["total_events"].iloc[0])
            conflict = int(kpi_df["conflict_events"].iloc[0])
            conflict_pct = round((conflict / total * 100.0), 1) if total > 0 else 0.0
            avg_gold = round(float(kpi_df["avg_goldstein"].iloc[0] or 0.0), 2)
            avg_tone = round(float(kpi_df["avg_tone"].iloc[0] or 0.0), 2)
            dist_countries = int(kpi_df["distinct_countries"].iloc[0])

            # Top Actors
            actor_sql = f"""
                SELECT actor1_name, COUNT(*) AS cnt
                FROM events
                WHERE {where_sql} AND actor1_name IS NOT NULL AND TRIM(actor1_name) != ''
                GROUP BY actor1_name
                ORDER BY cnt DESC
                LIMIT 5;
            """
            top_actors = store.query(actor_sql, list(params)).to_dict(orient="records")

            # Top CAMEO Root Codes
            cameo_sql = f"""
                SELECT event_root_code, COUNT(*) AS cnt
                FROM events
                WHERE {where_sql} AND event_root_code IS NOT NULL AND TRIM(event_root_code) != ''
                GROUP BY event_root_code
                ORDER BY cnt DESC
                LIMIT 5;
            """
            cameo_df = store.query(cameo_sql, list(params))
            cameo_map = self._load_cameo_lookup()
            top_cameo = []
            for _, r in cameo_df.iterrows():
                root_c = str(r["event_root_code"]).strip()
                root_name = cameo_map.get(root_c, {}).get("root_name", f"CAMEO {root_c}")
                top_cameo.append({"root_code": root_c, "root_name": root_name, "count": int(r["cnt"])})

            # Top Countries
            country_sql = f"""
                SELECT action_country, COUNT(*) AS cnt
                FROM events
                WHERE {where_sql} AND action_country IS NOT NULL AND TRIM(action_country) != ''
                GROUP BY action_country
                ORDER BY cnt DESC
                LIMIT 5;
            """
            country_df = store.query(country_sql, list(params))
            iso_map = self._load_fips_to_iso_map()
            top_countries = []
            for _, r in country_df.iterrows():
                c_code = str(r["action_country"]).strip().upper()
                c_name = iso_map.get(c_code, {}).get("name", c_code)
                top_countries.append({"country_code": c_code, "country_name": c_name, "count": int(r["cnt"])})

            return {
                "total_events": total,
                "distinct_countries": dist_countries,
                "conflict_events": conflict,
                "conflict_ratio_pct": conflict_pct,
                "avg_goldstein": avg_gold,
                "avg_tone": avg_tone,
                "top_actors": top_actors,
                "top_cameo_roots": top_cameo,
                "top_countries": top_countries,
            }
        finally:
            store.close()


