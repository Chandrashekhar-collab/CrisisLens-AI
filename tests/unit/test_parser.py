"""
Unit tests for GDELT Parser module.
Tests chunk cleaning, leading zero preservation, type conversions, and stream parsing.
"""

from pathlib import Path
import pandas as pd
import pytest

from crisislens.ingestion.gdelt_schema import GDELT_EVENT_COLUMNS
from crisislens.ingestion.parser import clean_events_chunk, stream_parse_tsv


def test_clean_events_chunk_preserves_leading_zeros():
    """Verify that EventCode leading zeros ('010', '02') are never truncated."""
    raw_data = {col: [""] for col in GDELT_EVENT_COLUMNS}
    raw_data["GLOBALEVENTID"] = ["10001"]
    raw_data["SQLDATE"] = ["20261029"]
    raw_data["EventCode"] = ["010"]
    raw_data["EventBaseCode"] = ["01"]
    raw_data["EventRootCode"] = ["01"]
    raw_data["QuadClass"] = ["1"]
    raw_data["GoldsteinScale"] = ["4.5"]

    raw_df = pd.DataFrame(raw_data)
    clean_df, rejected = clean_events_chunk(raw_df)

    assert rejected == 0
    assert len(clean_df) == 1
    assert clean_df["EventCode"].iloc[0] == "010"
    assert clean_df["EventBaseCode"].iloc[0] == "01"
    assert clean_df["EventRootCode"].iloc[0] == "01"
    assert clean_df["event_date"].iloc[0] == "2026-10-29"
    assert clean_df["QuadClass"].iloc[0] == 1


def test_clean_events_chunk_rejects_malformed_records():
    """Verify corrupted rows (non-digit ID or bad SQLDATE) are dropped and tracked."""
    row_valid = {col: "" for col in GDELT_EVENT_COLUMNS}
    row_valid.update({"GLOBALEVENTID": "1001", "SQLDATE": "20261029", "EventCode": "020"})

    row_bad_id = {col: "" for col in GDELT_EVENT_COLUMNS}
    row_bad_id.update({"GLOBALEVENTID": "not_an_id", "SQLDATE": "20261029", "EventCode": "020"})

    row_bad_date = {col: "" for col in GDELT_EVENT_COLUMNS}
    row_bad_date.update({"GLOBALEVENTID": "1002", "SQLDATE": "2026", "EventCode": "020"})

    raw_df = pd.DataFrame([row_valid, row_bad_id, row_bad_date])
    clean_df, rejected = clean_events_chunk(raw_df)

    assert rejected == 2
    assert len(clean_df) == 1
    assert clean_df["GLOBALEVENTID"].iloc[0] == 1001


def test_clean_events_chunk_numeric_coercion_and_clipping():
    """Verify Goldstein scale is clipped to [-10, 10] and coordinates bounded."""
    row = {col: "" for col in GDELT_EVENT_COLUMNS}
    row.update({
        "GLOBALEVENTID": "999",
        "SQLDATE": "20261029",
        "EventCode": "190",
        "GoldsteinScale": "15.0",  # Out of range -> should clip to 10.0
        "ActionGeo_Lat": "45.0",
        "ActionGeo_Long": "250.0",  # Invalid longitude -> should become NaN
    })
    raw_df = pd.DataFrame([row])
    clean_df, rejected = clean_events_chunk(raw_df)

    assert rejected == 0
    assert clean_df["GoldsteinScale"].iloc[0] == 10.0
    assert clean_df["ActionGeo_Lat"].iloc[0] == 45.0
    assert pd.isna(clean_df["ActionGeo_Long"].iloc[0])


def test_stream_parse_tsv_chunking(tmp_path: Path):
    """Verify streaming chunked parsing yields expected records without memory surge."""
    tsv_file = tmp_path / "stream_test.export.CSV"
    lines = []
    for i in range(25):
        row = ["" for _ in range(61)]
        row[0] = str(1000 + i)
        row[1] = "20261029"
        row[26] = f"0{i % 10}0"
        lines.append("\t".join(row))
    tsv_file.write_text("\n".join(lines) + "\n", encoding="utf-8")

    # Parse in chunks of 10
    chunks = list(stream_parse_tsv(tsv_file, chunk_size=10))

    # 25 rows with chunk_size 10 -> 3 chunks (10, 10, 5)
    assert len(chunks) == 3
    total_yielded = sum(len(c[0]) for c in chunks)
    assert total_yielded == 25
