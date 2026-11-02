"""
Unit tests for the DataService analytical query layer.
Validates date semantics (Reporting Time vs Event Context Date), aggregation accuracy,
read-only enforcement, faceted filtering, pagination, and empty dataset handling.
"""

from pathlib import Path
import pandas as pd
import pytest

from crisislens.storage.event_store import EventStore
from crisislens.ui.data_service import DataService


@pytest.fixture
def test_db_service(tmp_path: Path) -> DataService:
    """Create a temporary populated DuckDB store and DataService instance."""
    db_path = tmp_path / "test_service.duckdb"
    store = EventStore(db_path, read_only=False)

    # Populate with diverse synthetic test rows
    df = pd.DataFrame({
        "GLOBALEVENTID": [1001, 1002, 1003, 1004, 1005],
        # Distinct event context dates
        "event_date": ["2025-10-20", "2026-10-25", "2026-10-29", "2026-10-29", "2026-10-30"],
        "Year": [2025, 2026, 2026, 2026, 2026],
        "MonthYear": [202510, 202610, 202610, 202610, 202610],
        "Actor1Code": ["GOV", "MIL", "COP", "CVL", "REB"],
        "Actor1Name": ["WHITE HOUSE", "ARMY", "POLICE", "CITIZENS", "REBELS"],
        "Actor1CountryCode": ["USA", "GBR", "CAN", "USA", "SYR"],
        "Actor2Code": ["", "", "", "", ""],
        "Actor2Name": ["", "", "", "", ""],
        "Actor2CountryCode": ["", "", "", "", ""],
        "IsRootEvent": [1, 1, 1, 1, 1],
        "EventCode": ["010", "190", "140", "020", "195"],
        "EventBaseCode": ["010", "190", "140", "020", "195"],
        "EventRootCode": ["01", "19", "14", "02", "19"],
        "QuadClass": [1, 4, 3, 1, 4],  # 1, 1 (Coop) and 3, 4, 4 (Conflict)
        "GoldsteinScale": [4.0, -9.0, -3.0, 3.0, -10.0],
        "NumMentions": [10, 25, 5, 2, 50],
        "NumSources": [2, 5, 1, 1, 8],
        "NumArticles": [10, 25, 5, 2, 50],
        "AvgTone": [2.5, -7.0, -2.0, 1.0, -9.5],
        "ActionGeo_Lat": [38.89, 51.50, 45.42, 38.89, 33.51],
        "ActionGeo_Long": [-77.03, -0.12, -75.69, -77.03, 36.27],
        "ActionGeo_CountryCode": ["US", "UK", "CA", "US", "SY"],
        "ActionGeo_FullName": ["Washington, DC", "London", "Ottawa", "Washington, DC", "Damascus"],
        "SOURCEURL": [
            "https://reuters.com/article/1",
            "https://bbc.com/news/2",
            "https://cbc.ca/news/3",
            "https://apnews.com/article/4",
            "https://aljazeera.com/news/5",
        ],
        # Distinct reporting timestamps: all reported in Oct 2026
        "DATEADDED": [
            20261029120000,
            20261029140000,
            20261029153000,
            20261029154500,
            20261030090000,
        ],
    })

    store.upsert_events(df)
    store.record_manifest_start("batch-test", "test.export.CSV.zip", "testmd5")
    store.record_manifest_finish(
        batch_id="batch-test",
        status="SUCCESS",
        raw_rows=5,
        valid_rows=5,
        rejected_rows=0,
        date_range_start="2025-10-20",
        date_range_end="2026-10-30",
    )
    store.close()

    static_dir = Path(__file__).resolve().parent.parent.parent / "crisislens" / "data"
    return DataService(db_path=db_path, static_data_dir=static_dir)


def test_read_only_access_enforcement(test_db_service: DataService):
    """Verify DuckDB read_only=True prevents modifications."""
    store = test_db_service.get_read_only_store()
    assert store.read_only is True

    # Modifying in read-only mode must fail
    with pytest.raises(Exception):
        store.con.execute("DROP TABLE events;")

    store.close()


def test_date_semantics_reporting_vs_event_context(test_db_service: DataService):
    """
    Verify distinct filtering behavior:
    - Event Context Date (SQLDATE): 2025-10-20 is included when querying 2025
    - Reporting Activity Time (DATEADDED): All events were reported in Oct 2026
    """
    # 1. Querying 2025 using Event Context Date should find 1 event (ID 1001)
    metrics_context = test_db_service.get_overview_summary_metrics(
        date_start="2025-01-01",
        date_end="2025-12-31",
        use_reporting_time=False,
    )
    assert metrics_context["total_events"] == 1

    # 2. Querying 2025 using Reporting Activity Time should find 0 events
    metrics_reporting = test_db_service.get_overview_summary_metrics(
        date_start="2025-01-01",
        date_end="2025-12-31",
        use_reporting_time=True,
    )
    assert metrics_reporting["total_events"] == 0

    # 3. Querying 2026-10-29 using Reporting Activity Time should find 4 events
    metrics_rep_day = test_db_service.get_overview_summary_metrics(
        date_start="2026-10-29",
        date_end="2026-10-29",
        use_reporting_time=True,
    )
    assert metrics_rep_day["total_events"] == 4


def test_summary_metrics_calculations(test_db_service: DataService):
    """Verify KPIs: total count, countries count, conflict ratio, and averages."""
    metrics = test_db_service.get_overview_summary_metrics(use_reporting_time=False)

    assert metrics["total_events"] == 5
    # Distinct countries: US, UK, CA, SY -> 4
    assert metrics["distinct_countries"] == 4
    # Conflict events: QuadClass 3, 4, 4 -> 3 out of 5 = 60.0%
    assert metrics["conflict_events"] == 3
    assert metrics["conflict_ratio_pct"] == 60.0
    # Top actor
    assert metrics["top_actor"] in ["WHITE HOUSE", "ARMY", "POLICE", "CITIZENS", "REBELS"]


def test_country_distribution_enrichment(test_db_service: DataService):
    """Verify FIPS codes are enriched with ISO-3 and Country Names."""
    country_df = test_db_service.get_country_distribution()
    assert not country_df.empty
    assert "country_name" in country_df.columns
    assert "iso3" in country_df.columns

    us_row = country_df[country_df["action_country"] == "US"].iloc[0]
    assert us_row["total_events"] == 2
    assert us_row["iso3"] == "USA"
    assert us_row["country_name"] == "United States"

    uk_row = country_df[country_df["action_country"] == "UK"].iloc[0]
    assert uk_row["iso3"] == "GBR"
    assert uk_row["country_name"] == "United Kingdom"


def test_quad_class_distribution_mapping(test_db_service: DataService):
    """Verify QuadClass grouping and official CAMEO naming."""
    quad_df = test_db_service.get_quad_class_distribution()
    assert len(quad_df) == 3  # QuadClasses 1, 3, 4 present in sample

    counts_map = dict(zip(quad_df["quad_class"], quad_df["event_count"]))
    assert counts_map[1] == 2  # Verbal Coop
    assert counts_map[3] == 1  # Verbal Conflict
    assert counts_map[4] == 2  # Material Conflict


def test_explorer_faceted_search_and_pagination(test_db_service: DataService):
    """Verify search, filtering, and bounded pagination."""
    # 1. Text search on Actor
    df_search, count = test_db_service.query_explorer_events(search_text="White House")
    assert count == 1
    assert df_search["event_id"].iloc[0] == 1001

    # 2. Text search on Source URL domain
    df_url, count = test_db_service.query_explorer_events(search_text="bbc.com")
    assert count == 1
    assert df_url["event_id"].iloc[0] == 1002

    # 3. Filter by country
    df_country, count = test_db_service.query_explorer_events(country="US")
    assert count == 2

    # 4. Filter by Goldstein range (Conflict only: <= 0.0)
    df_conflict, count = test_db_service.query_explorer_events(goldstein_min=-10.0, goldstein_max=0.0)
    assert count == 3

    # 5. Filter by Min Mentions >= 20
    df_mentions, count = test_db_service.query_explorer_events(min_mentions=20)
    assert count == 2  # IDs 1002 (25) and 1005 (50)

    # 6. Pagination: 5 total items with page_size=2
    p1, count1 = test_db_service.query_explorer_events(page=1, page_size=2)
    assert count1 == 5
    assert len(p1) == 2

    p2, count2 = test_db_service.query_explorer_events(page=2, page_size=2)
    assert count2 == 5
    assert len(p2) == 2

    p3, count3 = test_db_service.query_explorer_events(page=3, page_size=2)
    assert len(p3) == 1


def test_event_detail_taxonomy_enrichment(test_db_service: DataService):
    """Verify single-event deep dive provides enriched CAMEO and country labels."""
    detail = test_db_service.get_event_detail(1001)
    assert detail is not None
    assert detail["event_id"] == 1001
    assert detail["event_code"] == "010"
    assert "Make statement" in detail["cameo_description"]
    assert detail["country_full_name"] == "United States"
    assert detail["quad_class_name"] == "Verbal Cooperation"

    # Non-existent event returns None
    assert test_db_service.get_event_detail(999999) is None


def test_empty_database_handling(tmp_path: Path):
    """Verify graceful handling when database has zero records."""
    empty_db = tmp_path / "empty.duckdb"
    store = EventStore(empty_db, read_only=False)
    store.close()

    static_dir = Path(__file__).resolve().parent.parent.parent / "crisislens" / "data"
    empty_service = DataService(db_path=empty_db, static_data_dir=static_dir)

    freshness = empty_service.get_data_freshness_info()
    assert freshness["has_data"] is False
    assert freshness["total_events"] == 0

    metrics = empty_service.get_overview_summary_metrics()
    assert metrics["total_events"] == 0
    assert metrics["conflict_ratio_pct"] == 0.0

    trend = empty_service.get_activity_trend()
    assert trend.empty

    countries = empty_service.get_country_distribution()
    assert countries.empty

    quad = empty_service.get_quad_class_distribution()
    assert quad.empty

    events, total = empty_service.query_explorer_events()
    assert events.empty
    assert total == 0
