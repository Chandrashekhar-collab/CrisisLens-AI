"""
Pytest configuration and common shared fixtures for CrisisLens AI.
"""

from pathlib import Path
import tomllib
from typing import Dict, Any, List
import pytest

from crisislens.ingestion.gdelt_schema import GDELT_EVENT_COLUMNS


@pytest.fixture(scope="session")
def project_root() -> Path:
    """Return the absolute path to the project root directory."""
    return Path(__file__).resolve().parent.parent


@pytest.fixture(scope="session")
def config_path(project_root: Path) -> Path:
    """Return the path to settings.toml."""
    return project_root / "config" / "settings.toml"


@pytest.fixture(scope="session")
def settings(config_path: Path) -> Dict[str, Any]:
    """Parse and return the settings.toml dictionary."""
    assert config_path.exists(), f"Configuration file not found at {config_path}"
    with open(config_path, "rb") as f:
        return tomllib.load(f)


@pytest.fixture
def sample_gdelt_raw_record() -> List[str]:
    """
    Return a mock GDELT 2.0 raw event record with exactly 61 tab-delimited columns.
    Matches schema specifications without pulling real web resources during unit tests.
    """
    record = ["" for _ in range(61)]
    # Populate primary index & key fields
    record[0] = "1234567890"        # GLOBALEVENTID
    record[1] = "20261029"          # SQLDATE
    record[2] = "202610"            # MonthYear
    record[3] = "2026"              # Year
    record[4] = "2026.8274"         # FractionDate
    record[5] = "GOV"               # Actor1Code
    record[6] = "PRESIDENT"         # Actor1Name
    record[7] = "USA"               # Actor1CountryCode
    record[15] = "CVL"              # Actor2Code
    record[16] = "CITIZENS"         # Actor2Name
    record[17] = "USA"              # Actor2CountryCode
    record[25] = "1"                # IsRootEvent
    record[26] = "010"              # EventCode (preserve leading zero!)
    record[27] = "01"               # EventBaseCode
    record[28] = "01"               # EventRootCode
    record[29] = "1"                # QuadClass (Verbal Cooperation)
    record[30] = "3.4"              # GoldsteinScale
    record[31] = "10"               # NumMentions
    record[32] = "2"                # NumSources
    record[33] = "5"                # NumArticles
    record[34] = "1.25"             # AvgTone
    record[51] = "Washington, DC"   # ActionGeo_FullName
    record[52] = "US"               # ActionGeo_CountryCode (FIPS)
    record[56] = "38.8951"          # ActionGeo_Lat
    record[57] = "-77.0364"         # ActionGeo_Long
    record[59] = "20261029150000"   # DATEADDED
    record[60] = "https://example.com/news/123"  # SOURCEURL
    return record
