"""
GDELT 2.0 Events Database Schema Constants and Specifications.

Authoritative source: GDELT Event Database Codebook V2.0
Each GDELT 2.0 event record file (.export.CSV) is a tab-delimited, headerless file
containing exactly 61 columns.
"""

from typing import Final, Dict, Any, List

# Authoritative sequential list of 61 GDELT 2.0 Event columns
GDELT_EVENT_COLUMNS: Final[List[str]] = [
    "GLOBALEVENTID",
    "SQLDATE",
    "MonthYear",
    "Year",
    "FractionDate",
    "Actor1Code",
    "Actor1Name",
    "Actor1CountryCode",
    "Actor1KnownGroupCode",
    "Actor1EthnicCode",
    "Actor1Religion1Code",
    "Actor1Religion2Code",
    "Actor1Type1Code",
    "Actor1Type2Code",
    "Actor1Type3Code",
    "Actor2Code",
    "Actor2Name",
    "Actor2CountryCode",
    "Actor2KnownGroupCode",
    "Actor2EthnicCode",
    "Actor2Religion1Code",
    "Actor2Religion2Code",
    "Actor2Type1Code",
    "Actor2Type2Code",
    "Actor2Type3Code",
    "IsRootEvent",
    "EventCode",
    "EventBaseCode",
    "EventRootCode",
    "QuadClass",
    "GoldsteinScale",
    "NumMentions",
    "NumSources",
    "NumArticles",
    "AvgTone",
    "Actor1Geo_Type",
    "Actor1Geo_FullName",
    "Actor1Geo_CountryCode",
    "Actor1Geo_ADM1Code",
    "Actor1Geo_ADM2Code",
    "Actor1Geo_Lat",
    "Actor1Geo_Long",
    "Actor1Geo_FeatureID",
    "Actor2Geo_Type",
    "Actor2Geo_FullName",
    "Actor2Geo_CountryCode",
    "Actor2Geo_ADM1Code",
    "Actor2Geo_ADM2Code",
    "Actor2Geo_Lat",
    "Actor2Geo_Long",
    "Actor2Geo_FeatureID",
    "ActionGeo_Type",
    "ActionGeo_FullName",
    "ActionGeo_CountryCode",
    "ActionGeo_ADM1Code",
    "ActionGeo_ADM2Code",
    "ActionGeo_Lat",
    "ActionGeo_Long",
    "ActionGeo_FeatureID",
    "DATEADDED",
    "SOURCEURL",
]

EXPECTED_COLUMN_COUNT: Final[int] = 61

# QuadClass mapping
QUAD_CLASS_MAP: Final[Dict[int, str]] = {
    1: "Verbal Cooperation",
    2: "Material Cooperation",
    3: "Verbal Conflict",
    4: "Material Conflict",
}

# Initial string dtype mapping for safe ingestion without type inference corruption
GDELT_DTYPES_INITIAL: Final[Dict[str, str]] = {col: "str" for col in GDELT_EVENT_COLUMNS}

# Target typed casting mapping for post-ingestion DataFrame normalization
GDELT_DTYPES_TARGET: Final[Dict[str, str]] = {
    "GLOBALEVENTID": "int64",
    "MonthYear": "int32",
    "Year": "int16",
    "FractionDate": "float32",
    "IsRootEvent": "int8",
    "EventCode": "str",  # Preserve leading zeros e.g. "010"
    "EventBaseCode": "str",
    "EventRootCode": "str",
    "QuadClass": "int8",
    "GoldsteinScale": "float32",
    "NumMentions": "int32",
    "NumSources": "int16",
    "NumArticles": "int16",
    "AvgTone": "float32",
    "Actor1Geo_Type": "float32",  # Can have nulls
    "Actor1Geo_Lat": "float32",
    "Actor1Geo_Long": "float32",
    "Actor2Geo_Type": "float32",
    "Actor2Geo_Lat": "float32",
    "Actor2Geo_Long": "float32",
    "ActionGeo_Type": "float32",
    "ActionGeo_Lat": "float32",
    "ActionGeo_Long": "float32",
    "DATEADDED": "int64",
    "SOURCEURL": "str",
}


def validate_column_count(columns: List[str]) -> bool:
    """Validate whether an input list of columns matches the 61-column GDELT 2.0 schema."""
    return len(columns) == EXPECTED_COLUMN_COUNT and columns == GDELT_EVENT_COLUMNS
