"""
Unit tests for DuckDB Event Store.
Tests schema initialization, idempotent upserts, duplicate key handling,
manifest auditing, and analytical query execution.
"""

from pathlib import Path
import pandas as pd
import pytest

from crisislens.storage.event_store import EventStore


@pytest.fixture
def sample_events_df() -> pd.DataFrame:
    """Provide a standardized mock DataFrame matching schema requirements."""
    return pd.DataFrame({
        "GLOBALEVENTID": [201, 202, 203],
        "event_date": ["2026-10-29", "2026-10-29", "2026-10-30"],
        "Year": [2026, 2026, 2026],
        "MonthYear": [202610, 202610, 202610],
        "Actor1Code": ["GOV", "MIL", "CVL"],
        "Actor1Name": ["GOVERNMENT", "ARMY", "CITIZENS"],
        "Actor1CountryCode": ["USA", "GBR", "CAN"],
        "Actor2Code": ["", "", ""],
        "Actor2Name": ["", "", ""],
        "Actor2CountryCode": ["", "", ""],
        "IsRootEvent": [1, 1, 0],
        "EventCode": ["010", "190", "020"],
        "EventBaseCode": ["010", "190", "020"],
        "EventRootCode": ["01", "19", "02"],
        "QuadClass": [1, 4, 1],
        "GoldsteinScale": [3.4, -9.0, 2.0],
        "NumMentions": [5, 10, 2],
        "NumSources": [1, 2, 1],
        "NumArticles": [5, 10, 2],
        "AvgTone": [1.2, -6.5, 3.1],
        "ActionGeo_Lat": [38.89, 51.50, 45.42],
        "ActionGeo_Long": [-77.03, -0.12, -75.69],
        "ActionGeo_CountryCode": ["US", "UK", "CA"],
        "ActionGeo_FullName": ["Washington", "London", "Ottawa"],
        "SOURCEURL": ["http://news.com/1", "http://news.com/2", "http://news.com/3"],
        "DATEADDED": [20261029153000, 20261029153000, 20261030100000],
    })


def test_event_store_initialization_and_schema(tmp_path: Path):
    """Verify DuckDB creates events and manifest tables with correct schema."""
    db_path = tmp_path / "test_store.duckdb"
    store = EventStore(db_path, read_only=False)

    tables = store.query("SHOW TABLES")["name"].tolist()
    assert "events" in tables
    assert "ingestion_manifest" in tables
    store.close()


def test_event_store_upsert_and_query(tmp_path: Path, sample_events_df: pd.DataFrame):
    """Verify inserting rows and querying aggregated counts."""
    db_path = tmp_path / "test_store.duckdb"
    store = EventStore(db_path, read_only=False)

    inserted = store.upsert_events(sample_events_df, parquet_path="test.parquet")
    assert inserted == 3
    assert store.get_total_events_count() == 3

    # Query daily aggregates
    daily = store.get_daily_counts()
    assert len(daily) == 2
    # 2 events on 2026-10-29, 1 on 2026-10-30
    counts_map = dict(zip(daily["event_date"].astype(str), daily["count"]))
    assert counts_map["2026-10-29"] == 2
    assert counts_map["2026-10-30"] == 1
    store.close()


def test_event_store_idempotent_upsert_no_duplicates(tmp_path: Path, sample_events_df: pd.DataFrame):
    """
    Verify re-upserting records with the same primary key updates existing rows
    and does NOT create duplicate records.
    """
    db_path = tmp_path / "test_store.duckdb"
    store = EventStore(db_path, read_only=False)

    store.upsert_events(sample_events_df)
    assert store.get_total_events_count() == 3

    # Modify tone of record 201 and upsert again
    updated_df = sample_events_df.copy()
    updated_df.loc[updated_df["GLOBALEVENTID"] == 201, "AvgTone"] = 9.99

    store.upsert_events(updated_df)
    # Total count must strictly remain 3
    assert store.get_total_events_count() == 3

    # Check that value was updated
    res = store.query("SELECT avg_tone FROM events WHERE event_id = 201")
    assert round(float(res["avg_tone"].iloc[0]), 2) == 9.99
    store.close()


def test_event_store_manifest_lifecycle(tmp_path: Path):
    """Verify manifest auditing from START to FINISH and idempotency checks."""
    db_path = tmp_path / "test_store.duckdb"
    store = EventStore(db_path, read_only=False)

    source_file = "20261029153000.export.CSV.zip"
    md5_hash = "abcdef1234567890"

    assert store.is_file_ingested(source_file, md5_hash) is False

    batch_id = "batch-001"
    store.record_manifest_start(batch_id, source_file, md5_hash)

    # While RUNNING, is_file_ingested is still False (must be SUCCESS)
    assert store.is_file_ingested(source_file, md5_hash) is False

    store.record_manifest_finish(
        batch_id=batch_id,
        status="SUCCESS",
        raw_rows=100,
        valid_rows=95,
        rejected_rows=5,
        date_range_start="2026-10-29",
        date_range_end="2026-10-29",
    )

    # After SUCCESS, is_file_ingested must be True
    assert store.is_file_ingested(source_file, md5_hash) is True
    assert store.is_file_ingested(source_file) is True

    history = store.get_manifest_history()
    assert len(history) == 1
    assert history["status"].iloc[0] == "SUCCESS"
    assert history["valid_rows"].iloc[0] == 95
    store.close()
