"""
DuckDB Relational & Analytical Event Store.

Provides schema initialization, high-throughput idempotent upserts,
audit trail manifest tracking, and analytical query interfaces.
"""

from pathlib import Path
from typing import Optional, List, Dict, Any
import logging
import duckdb
import pandas as pd

logger = logging.getLogger(__name__)


class EventStore:
    """
    DuckDB-backed transactional and analytical datastore for GDELT events.
    """

    def __init__(self, db_path: Path, read_only: bool = False):
        self.db_path = Path(db_path)
        self.read_only = read_only

        if not read_only:
            self.db_path.parent.mkdir(parents=True, exist_ok=True)

        self.con = duckdb.connect(str(self.db_path), read_only=read_only)
        if not read_only:
            self._initialize_schema()

    def _initialize_schema(self) -> None:
        """Create events and ingestion_manifest tables with indices if they do not exist."""
        # 1. Main events table
        self.con.execute("""
            CREATE TABLE IF NOT EXISTS events (
                event_id            BIGINT PRIMARY KEY,
                event_date          DATE NOT NULL,
                year                SMALLINT,
                month_year          INTEGER,
                actor1_code         VARCHAR,
                actor1_name         VARCHAR,
                actor1_country      VARCHAR,
                actor2_code         VARCHAR,
                actor2_name         VARCHAR,
                actor2_country      VARCHAR,
                is_root_event       TINYINT,
                event_code          VARCHAR,
                event_base_code     VARCHAR,
                event_root_code     VARCHAR,
                quad_class          TINYINT,
                goldstein_scale     FLOAT,
                num_mentions        INTEGER,
                num_sources         SMALLINT,
                num_articles        SMALLINT,
                avg_tone            FLOAT,
                action_lat          FLOAT,
                action_lon          FLOAT,
                action_country      VARCHAR,
                action_geo_name     VARCHAR,
                source_url          VARCHAR,
                date_added          BIGINT,
                parquet_path        VARCHAR,
                ingested_at         TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)

        # 2. Performance indexes
        self.con.execute("CREATE INDEX IF NOT EXISTS idx_events_date ON events(event_date);")
        self.con.execute("CREATE INDEX IF NOT EXISTS idx_events_country ON events(action_country);")
        self.con.execute("CREATE INDEX IF NOT EXISTS idx_events_quad ON events(quad_class);")
        self.con.execute("CREATE INDEX IF NOT EXISTS idx_events_root_code ON events(event_root_code);")

        # 3. Ingestion Manifest table for auditability and idempotency
        self.con.execute("""
            CREATE TABLE IF NOT EXISTS ingestion_manifest (
                batch_id            VARCHAR PRIMARY KEY,
                source_file         VARCHAR NOT NULL,
                file_md5            VARCHAR,
                started_at          TIMESTAMP NOT NULL,
                completed_at        TIMESTAMP,
                status              VARCHAR NOT NULL,
                raw_rows            BIGINT DEFAULT 0,
                valid_rows          BIGINT DEFAULT 0,
                rejected_rows       BIGINT DEFAULT 0,
                date_range_start    DATE,
                date_range_end      DATE,
                parquet_files_count INTEGER DEFAULT 0,
                error_message       VARCHAR
            );
        """)

    def is_file_ingested(self, source_file: str, file_md5: Optional[str] = None) -> bool:
        """
        Check whether this file has already been successfully ingested.
        Prevents duplicate reprocessing.
        """
        if file_md5:
            res = self.con.execute(
                "SELECT COUNT(*) FROM ingestion_manifest WHERE file_md5 = ? AND status = 'SUCCESS'",
                [file_md5.lower()],
            ).fetchall()
            if res and res[0][0] > 0:
                return True

        filename = Path(source_file).name
        res = self.con.execute(
            "SELECT COUNT(*) FROM ingestion_manifest WHERE source_file = ? AND status = 'SUCCESS'",
            [filename],
        ).fetchall()
        return bool(res and res[0][0] > 0)

    def record_manifest_start(
        self,
        batch_id: str,
        source_file: str,
        file_md5: Optional[str] = None,
    ) -> None:
        """Record the start of an ingestion run."""
        self.con.execute(
            """
            INSERT OR REPLACE INTO ingestion_manifest (
                batch_id, source_file, file_md5, started_at, status
            ) VALUES (?, ?, ?, CURRENT_TIMESTAMP, 'RUNNING')
            """,
            [batch_id, Path(source_file).name, file_md5.lower() if file_md5 else None],
        )

    def record_manifest_finish(
        self,
        batch_id: str,
        status: str,
        raw_rows: int = 0,
        valid_rows: int = 0,
        rejected_rows: int = 0,
        date_range_start: Optional[str] = None,
        date_range_end: Optional[str] = None,
        parquet_files_count: int = 0,
        error_message: Optional[str] = None,
    ) -> None:
        """Update manifest on ingestion completion or failure."""
        self.con.execute(
            """
            UPDATE ingestion_manifest SET
                completed_at = CURRENT_TIMESTAMP,
                status = ?,
                raw_rows = ?,
                valid_rows = ?,
                rejected_rows = ?,
                date_range_start = ?,
                date_range_end = ?,
                parquet_files_count = ?,
                error_message = ?
            WHERE batch_id = ?
            """,
            [
                status,
                raw_rows,
                valid_rows,
                rejected_rows,
                date_range_start,
                date_range_end,
                parquet_files_count,
                error_message,
                batch_id,
            ],
        )

    def upsert_events(self, df: pd.DataFrame, parquet_path: str = "") -> int:
        """
        Idempotently insert or update events in DuckDB from a cleaned DataFrame.
        Resolves conflicts by overwriting with newest record.
        """
        if df.empty:
            return 0

        # Prepare normalized staging representation
        staging = pd.DataFrame()
        staging["event_id"] = df["GLOBALEVENTID"].astype("int64")
        staging["event_date"] = pd.to_datetime(df["event_date"]).dt.date
        staging["year"] = df["Year"].astype("int16")
        staging["month_year"] = df["MonthYear"].astype("int32")
        staging["actor1_code"] = df["Actor1Code"].astype(str)
        staging["actor1_name"] = df["Actor1Name"].astype(str)
        staging["actor1_country"] = df["Actor1CountryCode"].astype(str)
        staging["actor2_code"] = df["Actor2Code"].astype(str)
        staging["actor2_name"] = df["Actor2Name"].astype(str)
        staging["actor2_country"] = df["Actor2CountryCode"].astype(str)
        staging["is_root_event"] = df["IsRootEvent"].astype("int8")
        staging["event_code"] = df["EventCode"].astype(str)
        staging["event_base_code"] = df["EventBaseCode"].astype(str)
        staging["event_root_code"] = df["EventRootCode"].astype(str)
        staging["quad_class"] = df["QuadClass"].astype("int8")
        staging["goldstein_scale"] = df["GoldsteinScale"].astype("float32")
        staging["num_mentions"] = df["NumMentions"].astype("int32")
        staging["num_sources"] = df["NumSources"].astype("int16")
        staging["num_articles"] = df["NumArticles"].astype("int16")
        staging["avg_tone"] = df["AvgTone"].astype("float32")
        staging["action_lat"] = df["ActionGeo_Lat"].astype("float32")
        staging["action_lon"] = df["ActionGeo_Long"].astype("float32")
        staging["action_country"] = df["ActionGeo_CountryCode"].astype(str)
        staging["action_geo_name"] = df["ActionGeo_FullName"].astype(str)
        staging["source_url"] = df["SOURCEURL"].astype(str)
        staging["date_added"] = df["DATEADDED"].astype("int64")
        staging["parquet_path"] = str(parquet_path)

        # Register staging DataFrame in DuckDB session
        self.con.register("staging_events_df", staging)

        # Execute idempotent upsert using ON CONFLICT clause
        upsert_query = """
            INSERT INTO events (
                event_id, event_date, year, month_year,
                actor1_code, actor1_name, actor1_country,
                actor2_code, actor2_name, actor2_country,
                is_root_event, event_code, event_base_code, event_root_code,
                quad_class, goldstein_scale,
                num_mentions, num_sources, num_articles, avg_tone,
                action_lat, action_lon, action_country, action_geo_name,
                source_url, date_added, parquet_path, ingested_at
            )
            SELECT
                event_id, event_date, year, month_year,
                actor1_code, actor1_name, actor1_country,
                actor2_code, actor2_name, actor2_country,
                is_root_event, event_code, event_base_code, event_root_code,
                quad_class, goldstein_scale,
                num_mentions, num_sources, num_articles, avg_tone,
                action_lat, action_lon, action_country, action_geo_name,
                source_url, date_added, parquet_path, now()
            FROM staging_events_df
            ON CONFLICT (event_id) DO UPDATE SET
                event_date = EXCLUDED.event_date,
                year = EXCLUDED.year,
                month_year = EXCLUDED.month_year,
                actor1_code = EXCLUDED.actor1_code,
                actor1_name = EXCLUDED.actor1_name,
                actor1_country = EXCLUDED.actor1_country,
                actor2_code = EXCLUDED.actor2_code,
                actor2_name = EXCLUDED.actor2_name,
                actor2_country = EXCLUDED.actor2_country,
                is_root_event = EXCLUDED.is_root_event,
                event_code = EXCLUDED.event_code,
                event_base_code = EXCLUDED.event_base_code,
                event_root_code = EXCLUDED.event_root_code,
                quad_class = EXCLUDED.quad_class,
                goldstein_scale = EXCLUDED.goldstein_scale,
                num_mentions = EXCLUDED.num_mentions,
                num_sources = EXCLUDED.num_sources,
                num_articles = EXCLUDED.num_articles,
                avg_tone = EXCLUDED.avg_tone,
                action_lat = EXCLUDED.action_lat,
                action_lon = EXCLUDED.action_lon,
                action_country = EXCLUDED.action_country,
                action_geo_name = EXCLUDED.action_geo_name,
                source_url = EXCLUDED.source_url,
                date_added = EXCLUDED.date_added,
                parquet_path = EXCLUDED.parquet_path,
                ingested_at = now();
        """
        self.con.execute(upsert_query)
        self.con.unregister("staging_events_df")

        return len(staging)

    def query(self, sql: str, params: Optional[List[Any]] = None) -> pd.DataFrame:
        """Run a query and return the result as a pandas DataFrame."""
        if params:
            return self.con.execute(sql, params).fetchdf()
        return self.con.execute(sql).fetchdf()

    def get_total_events_count(self) -> int:
        """Return total number of rows in the events table."""
        res = self.con.execute("SELECT COUNT(*) FROM events").fetchall()
        return res[0][0] if res else 0

    def get_daily_counts(
        self,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
    ) -> pd.DataFrame:
        """Return aggregated daily event counts between start_date and end_date."""
        query = "SELECT event_date, COUNT(*) AS count FROM events WHERE 1=1"
        params = []
        if start_date:
            query += " AND event_date >= ?"
            params.append(start_date)
        if end_date:
            query += " AND event_date <= ?"
            params.append(end_date)
        query += " GROUP BY event_date ORDER BY event_date ASC"
        return self.query(query, params if params else None)

    def get_manifest_history(self) -> pd.DataFrame:
        """Return full ingestion history from the manifest table."""
        return self.query("SELECT * FROM ingestion_manifest ORDER BY started_at DESC")

    def close(self) -> None:
        """Close the DuckDB connection."""
        self.con.close()
