"""
GDELT 2.0 Ingestion Parser.

Stream-parses raw tab-delimited GDELT 2.0 event files in bounded chunks,
enforces type conversions without integer-coercion loss on code fields (preserving leading zeros),
sanitizes numerical values, and tracks rejected rows.
"""

from pathlib import Path
from typing import Iterator, Tuple, Dict, Any, List
import logging
import pandas as pd
import numpy as np

from crisislens.ingestion.gdelt_schema import GDELT_EVENT_COLUMNS, GDELT_DTYPES_INITIAL

logger = logging.getLogger(__name__)


def clean_events_chunk(raw_chunk: pd.DataFrame) -> Tuple[pd.DataFrame, int]:
    """
    Clean, validate, and cast a raw string DataFrame chunk from a GDELT 2.0 TSV file.

    Guarantees:
    - Retains leading zeros for CAMEO codes (e.g. '010', '02').
    - Discards corrupted rows (e.g. non-numeric GLOBALEVENTID, non-date SQLDATE).
    - Safely coerces floating point metrics (GoldsteinScale, AvgTone, Lat/Long).
    - Formats SQLDATE into standard ISO 'YYYY-MM-DD'.
    - Returns (cleaned_dataframe, count_of_rejected_rows).
    """
    initial_rows = len(raw_chunk)
    if initial_rows == 0:
        return pd.DataFrame(), 0

    df = raw_chunk.copy()

    # 1. Clean and validate GLOBALEVENTID
    # Must be non-empty and purely digits
    id_series = df["GLOBALEVENTID"].astype(str).str.strip()
    valid_id_mask = id_series.str.isdigit() & (id_series != "")

    # 2. Clean and validate SQLDATE
    # Must be 8 digits (YYYYMMDD)
    date_series = df["SQLDATE"].astype(str).str.strip()
    valid_date_mask = date_series.str.match(r"^\d{8}$")

    # Combine essential validity mask
    valid_mask = valid_id_mask & valid_date_mask
    rejected_count = int((~valid_mask).sum())

    if rejected_count > 0:
        logger.debug("Filtered %d malformed rows in chunk", rejected_count)

    df = df[valid_mask].copy()
    if df.empty:
        return pd.DataFrame(), rejected_count

    # Cast GLOBALEVENTID to int64
    df["GLOBALEVENTID"] = df["GLOBALEVENTID"].astype("int64")

    # Parse SQLDATE to formatted date string YYYY-MM-DD
    # Parsing string slice is significantly faster than pd.to_datetime on large chunks
    sqldate_str = df["SQLDATE"].astype(str)
    df["event_date"] = (
        sqldate_str.str.slice(0, 4) + "-" +
        sqldate_str.str.slice(4, 6) + "-" +
        sqldate_str.str.slice(6, 8)
    )

    # Cast integer fields safely
    df["Year"] = pd.to_numeric(df["Year"], errors="coerce").fillna(0).astype("int16")
    df["MonthYear"] = pd.to_numeric(df["MonthYear"], errors="coerce").fillna(0).astype("int32")
    df["IsRootEvent"] = pd.to_numeric(df["IsRootEvent"], errors="coerce").fillna(0).astype("int8")

    # Preserve CAMEO event code as string with leading zeros intact
    df["EventCode"] = df["EventCode"].astype(str).str.strip()
    df["EventBaseCode"] = df["EventBaseCode"].astype(str).str.strip()
    df["EventRootCode"] = df["EventRootCode"].astype(str).str.strip()

    # QuadClass (1=Verbal Coop, 2=Material Coop, 3=Verbal Conflict, 4=Material Conflict)
    quad_numeric = pd.to_numeric(df["QuadClass"], errors="coerce").fillna(0).astype("int8")
    # Clip to valid range 1..4 (or 0 for unknown)
    df["QuadClass"] = quad_numeric.where(quad_numeric.isin([1, 2, 3, 4]), 0).astype("int8")

    # Floating point fields
    df["FractionDate"] = pd.to_numeric(df["FractionDate"], errors="coerce").astype("float32")
    df["GoldsteinScale"] = pd.to_numeric(df["GoldsteinScale"], errors="coerce").clip(-10.0, 10.0).astype("float32")
    df["AvgTone"] = pd.to_numeric(df["AvgTone"], errors="coerce").astype("float32")

    # Counts
    df["NumMentions"] = pd.to_numeric(df["NumMentions"], errors="coerce").fillna(0).astype("int32")
    df["NumSources"] = pd.to_numeric(df["NumSources"], errors="coerce").fillna(0).astype("int16")
    df["NumArticles"] = pd.to_numeric(df["NumArticles"], errors="coerce").fillna(0).astype("int16")

    # Coordinates
    lat = pd.to_numeric(df["ActionGeo_Lat"], errors="coerce").astype("float32")
    lon = pd.to_numeric(df["ActionGeo_Long"], errors="coerce").astype("float32")
    # Mask out invalid coordinate ranges
    df["ActionGeo_Lat"] = lat.where(lat.between(-90.0, 90.0), np.nan)
    df["ActionGeo_Long"] = lon.where(lon.between(-180.0, 180.0), np.nan)

    # Actor & Geography string fields (strip whitespace, ensure uppercase country codes)
    df["Actor1Code"] = df["Actor1Code"].astype(str).str.strip()
    df["Actor1Name"] = df["Actor1Name"].astype(str).str.strip()
    df["Actor1CountryCode"] = df["Actor1CountryCode"].astype(str).str.strip().str.upper()
    df["Actor2Code"] = df["Actor2Code"].astype(str).str.strip()
    df["Actor2Name"] = df["Actor2Name"].astype(str).str.strip()
    df["Actor2CountryCode"] = df["Actor2CountryCode"].astype(str).str.strip().str.upper()
    df["ActionGeo_CountryCode"] = df["ActionGeo_CountryCode"].astype(str).str.strip().str.upper()
    df["ActionGeo_FullName"] = df["ActionGeo_FullName"].astype(str).str.strip()
    df["SOURCEURL"] = df["SOURCEURL"].astype(str).str.strip()

    # DATEADDED
    df["DATEADDED"] = pd.to_numeric(df["DATEADDED"], errors="coerce").fillna(0).astype("int64")

    return df, rejected_count


def stream_parse_tsv(
    file_path: Path,
    chunk_size: int = 50000,
    max_rows: int | None = None,
) -> Iterator[Tuple[pd.DataFrame, int, int]]:
    """
    Generator yielding (clean_chunk, raw_rows_count, rejected_rows_count) from a raw TSV file.

    Memory constraint:
    Never loads the entire file into memory; strictly streams in chunks of size `chunk_size`.
    """
    file_path = Path(file_path)
    if not file_path.exists():
        raise FileNotFoundError(f"TSV file not found: {file_path}")

    total_yielded = 0

    reader = pd.read_csv(
        file_path,
        sep="\t",
        header=None,
        names=GDELT_EVENT_COLUMNS,
        dtype=GDELT_DTYPES_INITIAL,
        chunksize=chunk_size,
        on_bad_lines="skip",
        keep_default_na=False,
    )

    for chunk in reader:
        raw_count = len(chunk)
        clean_df, rejected = clean_events_chunk(chunk)

        if max_rows is not None and (total_yielded + len(clean_df)) > max_rows:
            remaining = max_rows - total_yielded
            if remaining > 0:
                clean_df = clean_df.iloc[:remaining]
                yield clean_df, raw_count, rejected
            break

        total_yielded += len(clean_df)
        yield clean_df, raw_count, rejected
