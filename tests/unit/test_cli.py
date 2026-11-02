"""
Unit tests for the Ingestion CLI module.
"""

from pathlib import Path
from unittest.mock import patch, MagicMock
import pytest

from crisislens.ingestion.cli import main, get_paths_from_config


def test_get_paths_from_config(tmp_path: Path):
    """Verify paths are resolved relative to root directory."""
    paths = get_paths_from_config(tmp_path)
    assert paths["raw_dir"] == tmp_path / "data" / "raw"
    assert paths["parquet_dir"] == tmp_path / "data" / "processed"
    assert paths["duckdb_path"] == tmp_path / "crisislens.duckdb"
    assert paths["chunk_size"] == 50000


def test_cli_status_invocation(tmp_path: Path, monkeypatch):
    """Verify --status prints storage and manifest statistics."""
    with patch("sys.argv", ["cli.py", "--status"]):
        with patch("crisislens.ingestion.cli.EventStore") as mock_store_cls, \
             patch("crisislens.ingestion.cli.ParquetStore") as mock_pstore_cls:
            mock_store = MagicMock()
            mock_store.get_total_events_count.return_value = 12345
            mock_store.get_manifest_history.return_value = MagicMock(empty=True)
            mock_store_cls.return_value = mock_store

            mock_pstore = MagicMock()
            mock_pstore.get_storage_stats.return_value = {
                "total_size_mb": 12.5,
                "total_files": 4,
            }
            mock_pstore_cls.return_value = mock_pstore

            main()
            mock_store.close.assert_called_once()
