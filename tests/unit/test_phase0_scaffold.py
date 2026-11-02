"""
Unit tests validating Phase 0 Scaffold and Configuration Artifacts.
"""

from pathlib import Path
import csv
from typing import Dict, Any, List
import pytest

from crisislens.ingestion.gdelt_schema import (
    GDELT_EVENT_COLUMNS,
    EXPECTED_COLUMN_COUNT,
    QUAD_CLASS_MAP,
    validate_column_count,
)


def test_settings_toml_structure(settings: Dict[str, Any]):
    """Verify that settings.toml contains all required sections and key parameters."""
    assert "data" in settings
    assert "models" in settings
    assert "ui" in settings
    assert "export" in settings

    # Data section
    assert settings["data"]["rolling_window_days"] == 30
    assert settings["data"]["chunk_size"] == 50000
    assert settings["data"]["parquet_compression"] in ["snappy", "gzip", "zstd"]

    # Models section
    assert settings["models"]["default_level"] == 1
    assert settings["models"]["zscore_threshold"] == 2.5
    assert settings["models"]["iqr_multiplier"] == 1.5
    assert settings["models"]["random_seed"] == 42

    # UI section
    assert settings["ui"]["map_default_zoom"] >= 1
    assert settings["ui"]["max_table_rows"] <= 10000

    # Export section
    assert settings["export"]["csv_encoding"] == "utf-8-sig"


def test_gdelt_schema_column_count_and_uniqueness():
    """Verify GDELT 2.0 schema has exactly 61 unique columns."""
    assert len(GDELT_EVENT_COLUMNS) == EXPECTED_COLUMN_COUNT == 61
    assert len(set(GDELT_EVENT_COLUMNS)) == 61, "Column names must be unique"
    assert GDELT_EVENT_COLUMNS[0] == "GLOBALEVENTID"
    assert GDELT_EVENT_COLUMNS[1] == "SQLDATE"
    assert GDELT_EVENT_COLUMNS[26] == "EventCode"
    assert GDELT_EVENT_COLUMNS[29] == "QuadClass"
    assert GDELT_EVENT_COLUMNS[30] == "GoldsteinScale"
    assert GDELT_EVENT_COLUMNS[60] == "SOURCEURL"


def test_validate_column_count_helper():
    """Verify schema column validator function."""
    assert validate_column_count(list(GDELT_EVENT_COLUMNS)) is True
    assert validate_column_count(list(GDELT_EVENT_COLUMNS[:-1])) is False
    assert validate_column_count(["wrong"] * 61) is False


def test_quad_class_mapping():
    """Verify QuadClass numeric codes match official CAMEO definitions."""
    assert QUAD_CLASS_MAP[1] == "Verbal Cooperation"
    assert QUAD_CLASS_MAP[2] == "Material Cooperation"
    assert QUAD_CLASS_MAP[3] == "Verbal Conflict"
    assert QUAD_CLASS_MAP[4] == "Material Conflict"


def test_cameo_event_codes_csv(project_root: Path):
    """Verify that cameo_event_codes.csv exists and contains all 20 CAMEO root codes."""
    csv_path = project_root / "crisislens" / "data" / "cameo_event_codes.csv"
    assert csv_path.exists(), f"Missing CAMEO lookup CSV at {csv_path}"

    with open(csv_path, mode="r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        rows = list(reader)

    assert len(rows) > 50, "CAMEO lookup should contain codes and descriptions"
    root_codes_found = {row["root_code"] for row in rows}

    # Verify all 20 CAMEO root codes are present ('01' through '20')
    expected_roots = {f"{i:02d}" for i in range(1, 21)}
    assert expected_roots.issubset(root_codes_found), (
        f"Missing root codes: {expected_roots - root_codes_found}"
    )


def test_fips_to_iso_csv(project_root: Path):
    """Verify that fips_to_iso.csv exists and properly maps critical sovereign entities."""
    csv_path = project_root / "crisislens" / "data" / "fips_to_iso.csv"
    assert csv_path.exists(), f"Missing FIPS-to-ISO lookup CSV at {csv_path}"

    with open(csv_path, mode="r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        mapping = {row["fips_code"]: row for row in reader}

    # Test critical FIPS codes known to diverge from ISO
    assert mapping["US"]["iso3_code"] == "USA"
    assert mapping["UK"]["iso3_code"] == "GBR"  # FIPS UK -> ISO GB/GBR
    assert mapping["RS"]["iso3_code"] == "RUS"  # FIPS RS -> ISO RU/RUS
    assert mapping["CH"]["iso3_code"] == "CHN"  # FIPS CH -> ISO CN/CHN
    assert mapping["GM"]["iso3_code"] == "DEU"  # FIPS GM -> ISO DE/DEU
    assert mapping["IN"]["iso3_code"] == "IND"  # India


def test_sample_gdelt_raw_record_fixture(sample_gdelt_raw_record: List[str]):
    """Verify that sample record fixture meets schema column length and primary types."""
    assert len(sample_gdelt_raw_record) == 61
    assert sample_gdelt_raw_record[0] == "1234567890"
    assert sample_gdelt_raw_record[26] == "010"  # Leading zero preserved as string
