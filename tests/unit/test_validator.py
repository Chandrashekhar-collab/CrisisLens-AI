"""
Unit tests for GDELT Validator module.
Validates structural TSV checking, column count checks, and semantic field constraints.
"""

from pathlib import Path
import pytest

from crisislens.ingestion.validator import (
    validate_raw_file_structure,
    validate_row_fields,
    ValidationError,
)


def create_synthetic_tsv(file_path: Path, num_rows: int = 5, num_cols: int = 61, is_headerless: bool = True):
    """Helper creating synthetic TSV file for validation tests."""
    lines = []
    if not is_headerless:
        # Prepend a text header
        lines.append("\t".join([f"Col_{i}" for i in range(num_cols)]))

    for i in range(num_rows):
        row = ["" for _ in range(num_cols)]
        row[0] = str(1000000000 + i)  # GLOBALEVENTID
        row[1] = "20261029"           # SQLDATE
        row[26] = "010"               # EventCode
        lines.append("\t".join(row))

    file_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def test_validate_raw_file_structure_valid(tmp_path: Path):
    """Verify validation passes on standard 61-column headerless TSV."""
    valid_file = tmp_path / "valid.export.CSV"
    create_synthetic_tsv(valid_file, num_rows=10, num_cols=61, is_headerless=True)

    report = validate_raw_file_structure(valid_file)
    assert report.is_valid is True
    assert report.column_count_matched is True
    assert report.is_headerless is True
    assert report.total_lines_sampled == 10


def test_validate_raw_file_structure_wrong_columns(tmp_path: Path):
    """Verify validation fails when column count is 60 instead of 61."""
    bad_cols_file = tmp_path / "bad_cols.export.CSV"
    create_synthetic_tsv(bad_cols_file, num_rows=5, num_cols=60, is_headerless=True)

    with pytest.raises(ValidationError, match="expected 61 columns, found 60"):
        validate_raw_file_structure(bad_cols_file)


def test_validate_raw_file_structure_header_detected(tmp_path: Path):
    """Verify validation detects and fails when file has a text header row."""
    header_file = tmp_path / "header.export.CSV"
    create_synthetic_tsv(header_file, num_rows=5, num_cols=61, is_headerless=False)

    with pytest.raises(ValidationError, match="First row does not appear to be data"):
        validate_raw_file_structure(header_file)


def test_validate_raw_file_empty(tmp_path: Path):
    """Verify validation fails on 0-byte file."""
    empty_file = tmp_path / "empty.export.CSV"
    empty_file.write_text("", encoding="utf-8")

    with pytest.raises(ValidationError, match="File is empty"):
        validate_raw_file_structure(empty_file)


def test_validate_row_fields_semantic_rules():
    """Verify record-level semantic validation rules."""
    valid_record = {
        "GLOBALEVENTID": "12345678",
        "SQLDATE": "20261029",
        "EventCode": "010",
        "QuadClass": "1",
        "ActionGeo_Lat": "38.8951",
        "ActionGeo_Long": "-77.0364",
    }
    is_valid, reason = validate_row_fields(valid_record)
    assert is_valid is True
    assert reason is None

    # Invalid GLOBALEVENTID
    bad_id = dict(valid_record, GLOBALEVENTID="abc")
    is_valid, reason = validate_row_fields(bad_id)
    assert is_valid is False
    assert "GLOBALEVENTID" in reason

    # Invalid SQLDATE format
    bad_date = dict(valid_record, SQLDATE="20261399")  # Month 13
    is_valid, reason = validate_row_fields(bad_date)
    assert is_valid is False
    assert "SQLDATE" in reason

    # Invalid QuadClass
    bad_quad = dict(valid_record, QuadClass="9")
    is_valid, reason = validate_row_fields(bad_quad)
    assert is_valid is False
    assert "QuadClass" in reason

    # Out of bounds coordinates
    bad_lat = dict(valid_record, ActionGeo_Lat="195.0")
    is_valid, reason = validate_row_fields(bad_lat)
    assert is_valid is False
    assert "ActionGeo_Lat" in reason
