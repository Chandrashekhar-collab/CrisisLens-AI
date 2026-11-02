"""
End-to-end Integration Tests for CrisisLens AI Ingestion Pipeline.
Tests the entire lifecycle from raw archive to Parquet shards and DuckDB queries
using synthetic fixtures without external network dependencies.
"""

from pathlib import Path
import zipfile
import io
import pytest

from crisislens.ingestion.pipeline import IngestionPipeline
from crisislens.storage.parquet_store import ParquetStore
from crisislens.storage.event_store import EventStore


def build_synthetic_export_archive(archive_path: Path) -> int:
    """
    Generate a realistic synthetic GDELT 2.0 .export.CSV.zip archive.
    Returns the count of raw rows written (50 total).
    Composition:
    - 40 valid unique rows (dates: 2026-10-28, 2026-10-29)
    - 5 duplicate IDs (updating earlier IDs)
    - 5 malformed rows (bad ID or bad date)
    """
    lines = []

    # 1. 40 valid unique events
    for i in range(1, 41):
        row = ["" for _ in range(61)]
        row[0] = str(5000 + i)                 # GLOBALEVENTID
        row[1] = "20261028" if i <= 20 else "20261029"  # SQLDATE
        row[2] = "202610"                      # MonthYear
        row[3] = "2026"                        # Year
        row[4] = "2026.82"                     # FractionDate
        row[5] = "GOV"                         # Actor1Code
        row[6] = "GOVERNMENT"                  # Actor1Name
        row[7] = "USA"                         # Actor1CountryCode
        row[25] = "1"                          # IsRootEvent
        row[26] = f"0{i % 5}0"                 # EventCode ('010', '020', etc.)
        row[27] = f"0{i % 5}"                  # EventBaseCode
        row[28] = f"0{i % 5}"                  # EventRootCode
        row[29] = str((i % 4) + 1)             # QuadClass 1..4
        row[30] = str(round((i % 10) - 5.0, 1)) # GoldsteinScale
        row[31] = "5"                          # NumMentions
        row[32] = "1"                          # NumSources
        row[33] = "3"                          # NumArticles
        row[34] = "2.5"                        # AvgTone
        row[51] = "Sample Location"            # ActionGeo_FullName
        row[52] = "US" if i % 2 == 0 else "CA" # ActionGeo_CountryCode (FIPS)
        row[56] = "38.89"                      # ActionGeo_Lat
        row[57] = "-77.03"                     # ActionGeo_Long
        row[59] = "20261029153000"             # DATEADDED
        row[60] = f"https://example.com/news/{i}"  # SOURCEURL
        lines.append("\t".join(row))

    # 2. 5 duplicate IDs (re-issuing IDs 5001-5005 with higher mentions)
    for i in range(1, 6):
        row = ["" for _ in range(61)]
        row[0] = str(5000 + i)                 # Duplicate GLOBALEVENTID
        row[1] = "20261029"
        row[2] = "202610"
        row[3] = "2026"
        row[4] = "2026.82"
        row[25] = "1"
        row[26] = "010"
        row[27] = "01"
        row[28] = "01"
        row[29] = "1"
        row[30] = "8.0"
        row[31] = "99"                         # Updated NumMentions
        row[32] = "10"
        row[33] = "50"
        row[34] = "5.0"
        row[51] = "Updated Location"
        row[52] = "US"
        row[56] = "40.71"
        row[57] = "-74.00"
        row[59] = "20261029160000"
        row[60] = f"https://example.com/updated/{i}"
        lines.append("\t".join(row))

    # 3. 5 malformed records (e.g., non-digit ID or bad dates)
    for i in range(1, 6):
        row = ["" for _ in range(61)]
        row[0] = f"corrupt_{i}"                # Non-numeric ID
        row[1] = "bad_date"                    # Non-date
        row[26] = "010"
        lines.append("\t".join(row))

    tsv_data = "\n".join(lines) + "\n"

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr(archive_path.name.replace(".zip", ""), tsv_data)

    archive_path.parent.mkdir(parents=True, exist_ok=True)
    archive_path.write_bytes(buf.getvalue())
    return len(lines)


def test_pipeline_end_to_end_lifecycle(tmp_path: Path):
    """
    Test complete ingestion cycle:
    1. Parse archive
    2. Write Parquet partitions
    3. Upsert DuckDB
    4. Audit manifest
    5. Test idempotency (skip on rerun)
    6. Test force rerun (updates in place without duplicates)
    """
    raw_dir = tmp_path / "data" / "raw"
    parquet_dir = tmp_path / "data" / "processed"
    duckdb_path = tmp_path / "test_crisislens.duckdb"

    archive_name = "20261029153000.export.CSV.zip"
    archive_path = raw_dir / archive_name
    total_raw_rows = build_synthetic_export_archive(archive_path)
    assert total_raw_rows == 50

    pipeline = IngestionPipeline(
        raw_dir=raw_dir,
        parquet_dir=parquet_dir,
        duckdb_path=duckdb_path,
        chunk_size=20,  # Force multiple chunk iterations
    )

    # --- Run 1: Initial Ingestion ---
    result1 = pipeline.ingest_archive(archive_path)
    assert result1.status == "SUCCESS"
    assert result1.raw_rows == 50
    assert result1.rejected_rows == 5
    assert result1.valid_rows == 45
    assert len(result1.parquet_files) > 0
    assert result1.error_message is None

    # Check DuckDB storage directly via pipeline's store
    total_events = pipeline.event_store.get_total_events_count()
    assert total_events == 40

    # Verify updated duplicate record has updated NumMentions = 99
    res = pipeline.event_store.query("SELECT num_mentions FROM events WHERE event_id = 5001")
    assert res["num_mentions"].iloc[0] == 99

    # Check Parquet storage
    pstore = ParquetStore(parquet_dir)
    parquet_df = pstore.read_events()
    assert len(parquet_df) >= 40

    # --- Run 2: Idempotent Rerun (Should Skip) ---
    result2 = pipeline.ingest_archive(archive_path, force=False)
    assert result2.status == "SKIPPED"
    assert pipeline.event_store.get_total_events_count() == 40  # Still 40

    # --- Run 3: Forced Reprocessing ---
    result3 = pipeline.ingest_archive(archive_path, force=True)
    assert result3.status == "SUCCESS"
    assert pipeline.event_store.get_total_events_count() == 40  # Still exactly 40, no duplicates created!

    pipeline.close()


def test_pipeline_handles_malformed_file_gracefully(tmp_path: Path):
    """Verify pipeline records FAILED status in manifest when schema is invalid."""
    raw_dir = tmp_path / "raw"
    parquet_dir = tmp_path / "parquet"
    duckdb_path = tmp_path / "fail_test.duckdb"

    # Create invalid archive with only 5 columns
    bad_zip = raw_dir / "bad.export.CSV.zip"
    bad_buf = io.BytesIO()
    with zipfile.ZipFile(bad_buf, "w") as zf:
        zf.writestr("bad.export.CSV", "c1\tc2\tc3\tc4\tc5\n")
    bad_zip.parent.mkdir(parents=True, exist_ok=True)
    bad_zip.write_bytes(bad_buf.getvalue())

    pipeline = IngestionPipeline(
        raw_dir=raw_dir,
        parquet_dir=parquet_dir,
        duckdb_path=duckdb_path,
    )

    result = pipeline.ingest_archive(bad_zip)
    assert result.status == "FAILED"
    assert "validation failed" in result.error_message.lower()

    # Verify failure recorded in DuckDB manifest
    manifest = pipeline.event_store.get_manifest_history()
    assert len(manifest) == 1
    assert manifest["status"].iloc[0] == "FAILED"
    assert "validation failed" in manifest["error_message"].iloc[0].lower()

    pipeline.close()
