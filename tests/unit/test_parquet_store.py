"""
Unit tests for Parquet Storage Layer.
Tests partitioned writing, atomic file creation, column pruning, and storage statistics.
"""

from pathlib import Path
import pandas as pd
import pytest

from crisislens.storage.parquet_store import ParquetStore


@pytest.fixture
def sample_clean_df() -> pd.DataFrame:
    """Provide a small cleaned DataFrame for storage tests."""
    return pd.DataFrame({
        "GLOBALEVENTID": [101, 102, 103],
        "event_date": ["2026-10-28", "2026-10-29", "2026-10-29"],
        "Year": [2026, 2026, 2026],
        "MonthYear": [202610, 202610, 202610],
        "EventCode": ["010", "020", "030"],
        "QuadClass": [1, 1, 2],
        "GoldsteinScale": [3.4, 4.0, 5.0],
        "ActionGeo_CountryCode": ["US", "US", "CA"],
    })


def test_parquet_store_partitioned_write_and_read(tmp_path: Path, sample_clean_df: pd.DataFrame):
    """Verify writing partitions by date and reading back full dataset."""
    store = ParquetStore(tmp_path / "parquet_data")
    shards = store.write_events_batch(sample_clean_df, batch_id="batch1")

    # We have 2 distinct dates (2026-10-28 and 2026-10-29) -> 2 partition files
    assert len(shards) == 2
    for shard in shards:
        assert shard.exists()
        assert shard.suffix == ".parquet"
        # Atomic temp file should be removed
        assert not shard.with_name(f"{shard.name}.tmp").exists()

    # Read back all events
    df_read = store.read_events()
    assert len(df_read) == 3
    assert set(df_read["GLOBALEVENTID"]) == {101, 102, 103}


def test_parquet_store_column_pruning(tmp_path: Path, sample_clean_df: pd.DataFrame):
    """Verify reading with column pruning returns only requested subset."""
    store = ParquetStore(tmp_path / "parquet_data")
    store.write_events_batch(sample_clean_df, batch_id="batch1")

    subset = store.read_events(columns=["GLOBALEVENTID", "EventCode"])
    assert list(subset.columns) == ["GLOBALEVENTID", "EventCode"]
    assert len(subset) == 3


def test_parquet_store_stats(tmp_path: Path, sample_clean_df: pd.DataFrame):
    """Verify storage statistics reporting."""
    store = ParquetStore(tmp_path / "parquet_data")
    store.write_events_batch(sample_clean_df, batch_id="batch1")

    stats = store.get_storage_stats()
    assert stats["total_files"] == 2
    assert stats["total_size_bytes"] > 0
    assert stats["total_size_mb"] >= 0.0
