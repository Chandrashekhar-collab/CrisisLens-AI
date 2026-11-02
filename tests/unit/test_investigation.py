"""
Unit and Integration Tests for Phase 4:
Event Investigation Drill-Down, Bounded Parameterized Queries,
Date Semantics, Interval Statistics, and Export Integrity.
"""

from pathlib import Path
import pytest
import pandas as pd
import numpy as np

from crisislens.storage.event_store import EventStore
from crisislens.ui.data_service import DataService
from streamlit.testing.v1 import AppTest


@pytest.fixture
def test_investigation_service(tmp_path: Path) -> DataService:
    """Create an isolated test DuckDB store with diverse records for investigation."""
    db_path = tmp_path / "investigation_test.duckdb"
    store = EventStore(db_path, read_only=False)

    df = pd.DataFrame({
        "GLOBALEVENTID": [1001, 1002, 1003, 1004, 1005],
        # Event context dates (SQLDATE) spanning multiple months
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
        "QuadClass": [1, 4, 3, 1, 4],  # 1, 1 (Cooperation) and 3, 4, 4 (Conflict)
        "GoldsteinScale": [4.0, -9.0, -3.0, 3.0, -10.0],
        "NumMentions": [10, 25, 5, 2, 50],
        "NumSources": [2, 5, 1, 1, 8],
        "NumArticles": [10, 25, 5, 2, 50],
        "AvgTone": [2.5, -7.0, -2.0, 1.0, -9.5],
        "ActionGeo_Lat": [38.89, 51.50, 45.42, 38.89, 33.51],
        "ActionGeo_Long": [-77.03, -0.12, -75.69, -77.03, 36.27],
        "ActionGeo_CountryCode": ["US", "UK", "CA", "US", "SY"],
        "ActionGeo_FullName": ["Washington, DC", "London", "Ottawa", "Washington, DC", "Damascus"],
        # Distinct DATEADDED batches: 3 in batch 1, 2 in batch 2
        "DATEADDED": [20261029153000, 20261029153000, 20261029153000, 20261029154500, 20261029154500],
        "SOURCEURL": [
            "https://reuters.com/news/1001",
            "https://bbc.com/news/1002",
            "https://cbc.ca/news/1003",
            "https://apnews.com/news/1004",
            "https://aljazeera.com/news/1005",
        ],
    })
    store.upsert_events(df)
    store.close()
    return DataService(db_path=db_path)


def test_get_available_reporting_intervals(test_investigation_service: DataService):
    intervals = test_investigation_service.get_available_reporting_intervals()
    assert len(intervals) == 2
    # Verify descending sort
    assert intervals[0]["date_added"] == 20261029154500
    assert intervals[0]["event_count"] == 2
    assert intervals[1]["date_added"] == 20261029153000
    assert intervals[1]["event_count"] == 3


def test_query_investigation_events_exact_interval(test_investigation_service: DataService):
    df_batch1, count1 = test_investigation_service.query_investigation_events(
        interval_date_added=20261029153000
    )
    assert count1 == 3
    assert len(df_batch1) == 3
    assert set(df_batch1["event_id"]) == {1001, 1002, 1003}

    df_batch2, count2 = test_investigation_service.query_investigation_events(
        interval_date_added=20261029154500
    )
    assert count2 == 2
    assert len(df_batch2) == 2
    assert set(df_batch2["event_id"]) == {1004, 1005}


def test_query_investigation_events_faceted_filters(test_investigation_service: DataService):
    # Filter by conflict classes (QuadClass 3 and 4) in batch 1
    df, count = test_investigation_service.query_investigation_events(
        interval_date_added=20261029153000,
        quad_classes=[3, 4],
    )
    assert count == 2
    assert set(df["event_id"]) == {1002, 1003}

    # Filter by Country US
    df_us, count_us = test_investigation_service.query_investigation_events(
        interval_date_added=20261029153000,
        country="US",
    )
    assert count_us == 1
    assert df_us.iloc[0]["event_id"] == 1001


def test_query_investigation_events_goldstein_bounds(test_investigation_service: DataService):
    # Only extreme negative stability (<= -5.0)
    df, count = test_investigation_service.query_investigation_events(
        goldstein_min=-10.0,
        goldstein_max=-5.0,
    )
    assert count == 2  # MIL (-9.0) and REB (-10.0)
    assert set(df["event_id"]) == {1002, 1005}


def test_query_investigation_events_text_search(test_investigation_service: DataService):
    df, count = test_investigation_service.query_investigation_events(
        search_text="Reuters",
    )
    assert count == 1
    assert df.iloc[0]["event_id"] == 1001

    df_act, count_act = test_investigation_service.query_investigation_events(
        search_text="Police",
    )
    assert count_act == 1
    assert df_act.iloc[0]["event_id"] == 1003


def test_get_investigation_interval_stats(test_investigation_service: DataService):
    stats = test_investigation_service.get_investigation_interval_stats(
        interval_date_added=20261029153000
    )
    assert stats["total_events"] == 3
    assert stats["distinct_countries"] == 3
    # 2 out of 3 are conflict (1002, 1003) -> 66.7%
    assert stats["conflict_ratio_pct"] == 66.7
    assert len(stats["top_actors"]) <= 5
    assert len(stats["top_countries"]) <= 5


def test_query_investigation_events_empty_state(test_investigation_service: DataService):
    # Non-existent date_added
    df, count = test_investigation_service.query_investigation_events(
        interval_date_added=19990101000000
    )
    assert count == 0
    assert df.empty


def test_date_semantics_reporting_vs_event_context(test_investigation_service: DataService):
    # SQLDATE event_date has record 1001 on '2025-10-20'
    df_context, count_ctx = test_investigation_service.query_investigation_events(
        date_start="2025-10-01",
        date_end="2025-10-31",
        use_reporting_time=False,
    )
    assert count_ctx == 1
    assert df_context.iloc[0]["event_id"] == 1001

    # Reporting time (DATEADDED) for 1001 is 2026-10-29
    df_rep, count_rep = test_investigation_service.query_investigation_events(
        date_start="2026-10-01",
        date_end="2026-10-31",
        use_reporting_time=True,
    )
    assert count_rep == 5  # All were reported in 2026


def test_investigation_page_headless_apptest():
    """Verify that the Event Investigation screen renders headlessly without exceptions."""
    app_path = Path(__file__).resolve().parent.parent.parent / "app.py"
    at = AppTest.from_file(str(app_path), default_timeout=30).run()
    # Navigate to 🕵️ Event Investigation
    at.sidebar.radio[0].set_value("🕵️ Event Investigation").run()
    assert len(at.exception) == 0, f"AppTest threw exceptions: {at.exception}"

