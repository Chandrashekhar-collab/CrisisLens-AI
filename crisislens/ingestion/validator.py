"""
GDELT 2.0 Ingestion Validator.

Provides structural validation of raw TSV files, column count enforcement (61 columns),
and record-level semantic validation rules.
"""

from pathlib import Path
from dataclasses import dataclass, field
from typing import List, Tuple, Optional
import csv

from crisislens.ingestion.gdelt_schema import EXPECTED_COLUMN_COUNT


class ValidationError(Exception):
    """Raised when file structure, delimiter, or schema does not meet GDELT 2.0 specifications."""
    pass


@dataclass
class ValidationReport:
    """Encapsulates the outcome of a pre-parse file validation check."""
    is_valid: bool
    total_lines_sampled: int = 0
    column_count_matched: bool = False
    is_headerless: bool = False
    delimiter_detected: str = "\t"
    sample_errors: List[str] = field(default_factory=list)


def validate_raw_file_structure(
    file_path: Path,
    sample_rows: int = 20,
    expected_cols: int = EXPECTED_COLUMN_COUNT,
) -> ValidationReport:
    """
    Inspect a raw TSV file to verify that:
    1. The file exists and is non-empty.
    2. Columns are separated by tab characters ('\\t').
    3. Every sampled line contains exactly 61 columns.
    4. The file is headerless (row 1 column 0 is a numeric GLOBALEVENTID, column 1 is an 8-digit date).
    """
    file_path = Path(file_path)
    if not file_path.exists():
        raise ValidationError(f"File does not exist: {file_path}")

    if file_path.stat().st_size == 0:
        raise ValidationError(f"File is empty (0 bytes): {file_path}")

    report = ValidationReport(is_valid=False)

    try:
        with open(file_path, "r", encoding="utf-8", errors="replace") as f:
            lines = [f.readline() for _ in range(sample_rows)]
            lines = [line.rstrip("\r\n") for line in lines if line.strip()]

        if not lines:
            raise ValidationError(f"File contains no non-empty lines: {file_path}")

        report.total_lines_sampled = len(lines)

        # Check delimiter and column count on sampled lines
        all_cols_match = True
        for idx, line in enumerate(lines, start=1):
            parts = line.split("\t")
            if len(parts) != expected_cols:
                all_cols_match = False
                report.sample_errors.append(
                    f"Line {idx}: expected {expected_cols} columns, found {len(parts)}"
                )

        report.column_count_matched = all_cols_match

        # Check headerless nature by examining first row
        first_row_cols = lines[0].split("\t")
        if len(first_row_cols) >= 2:
            first_id = first_row_cols[0].strip()
            first_date = first_row_cols[1].strip()
            # GDELT IDs are numeric integers (e.g., 1330498899)
            # SQLDATE is an 8-digit integer YYYYMMDD
            is_numeric_id = first_id.isdigit()
            is_valid_date_format = len(first_date) == 8 and first_date.isdigit()
            report.is_headerless = is_numeric_id and is_valid_date_format

            if not report.is_headerless:
                report.sample_errors.append(
                    f"First row does not appear to be data (ID='{first_id}', Date='{first_date}')"
                )

        # Overall validity
        report.is_valid = report.column_count_matched and report.is_headerless

        if not report.is_valid:
            logger_msg = "; ".join(report.sample_errors[:3])
            raise ValidationError(f"Structural validation failed for {file_path.name}: {logger_msg}")

        return report

    except (OSError, csv.Error) as e:
        raise ValidationError(f"Error reading file {file_path}: {e}") from e


def validate_row_fields(row: dict) -> Tuple[bool, Optional[str]]:
    """
    Validate semantic constraints on a single parsed row dictionary.

    Returns:
        (is_valid, rejection_reason)
    """
    # 1. GLOBALEVENTID must be non-empty and numeric
    event_id = str(row.get("GLOBALEVENTID", "")).strip()
    if not event_id or not event_id.isdigit():
        return False, "Missing or non-numeric GLOBALEVENTID"

    # 2. SQLDATE must be an 8-character string (YYYYMMDD) with valid year range (1900-2100)
    sqldate = str(row.get("SQLDATE", "")).strip()
    if len(sqldate) != 8 or not sqldate.isdigit():
        return False, f"Malformed SQLDATE: {sqldate}"
    year = int(sqldate[:4])
    month = int(sqldate[4:6])
    day = int(sqldate[6:8])
    if not (1900 <= year <= 2100 and 1 <= month <= 12 and 1 <= day <= 31):
        return False, f"SQLDATE out of valid calendar range: {sqldate}"

    # 3. EventCode must be present
    event_code = str(row.get("EventCode", "")).strip()
    if not event_code:
        return False, "Missing EventCode"

    # 4. QuadClass must be 1, 2, 3, or 4 if present
    quad = row.get("QuadClass")
    if quad is not None and str(quad).strip():
        try:
            quad_val = int(quad)
            if quad_val not in (1, 2, 3, 4):
                return False, f"Invalid QuadClass: {quad_val}"
        except ValueError:
            return False, f"Non-numeric QuadClass: {quad}"

    # 5. Latitude and Longitude range check if present
    lat = row.get("ActionGeo_Lat")
    lon = row.get("ActionGeo_Long")
    if lat is not None and str(lat).strip():
        try:
            lat_f = float(lat)
            if not (-90.0 <= lat_f <= 90.0):
                return False, f"ActionGeo_Lat out of bounds: {lat_f}"
        except ValueError:
            return False, f"Non-numeric ActionGeo_Lat: {lat}"

    if lon is not None and str(lon).strip():
        try:
            lon_f = float(lon)
            if not (-180.0 <= lon_f <= 180.0):
                return False, f"ActionGeo_Long out of bounds: {lon_f}"
        except ValueError:
            return False, f"Non-numeric ActionGeo_Long: {lon}"

    return True, None
