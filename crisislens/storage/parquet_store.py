"""
Parquet Columnar Storage Layer.

Manages writing and reading partitioned Parquet shards using PyArrow.
Provides atomic writes, snappy compression, column pruning, and storage metrics.
"""

from pathlib import Path
from typing import List, Optional, Dict, Any
import logging
import uuid
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

logger = logging.getLogger(__name__)


class ParquetStore:
    """
    Manages partition-based Parquet storage for GDELT events.
    Directory structure:
        {base_dir}/year={YYYY}/month={MM}/day={DD}/events_{batch_id}.parquet
    """

    def __init__(self, base_dir: Path):
        self.base_dir = Path(base_dir)
        self.base_dir.mkdir(parents=True, exist_ok=True)

    def write_events_batch(
        self,
        df: pd.DataFrame,
        batch_id: str,
        compression: str = "snappy",
    ) -> List[Path]:
        """
        Write a cleaned DataFrame of events into date-partitioned Parquet files.

        Guarantees:
        - Partitions by event_date (YYYY, MM, DD).
        - Uses atomic file creation (.tmp -> .parquet) to prevent corrupt files on interrupted writes.
        - Returns list of created partition file paths.
        """
        if df.empty:
            return []

        written_paths: List[Path] = []

        # If 'event_date' column is present, group by it; otherwise group by current date
        if "event_date" not in df.columns:
            raise ValueError("DataFrame must contain 'event_date' column (format YYYY-MM-DD)")

        # Group rows by event_date for partitioning
        for date_val, group in df.groupby("event_date"):
            date_str = str(date_val)
            parts = date_str.split("-")
            if len(parts) == 3:
                year, month, day = parts[0], parts[1], parts[2]
            else:
                year, month, day = "unknown", "unknown", "unknown"

            partition_dir = self.base_dir / f"year={year}" / f"month={month}" / f"day={day}"
            partition_dir.mkdir(parents=True, exist_ok=True)

            file_suffix = uuid.uuid4().hex[:6]
            target_file = partition_dir / f"events_{batch_id}_{date_str}_{file_suffix}.parquet"
            temp_file = target_file.with_name(f"{target_file.name}.tmp")

            try:
                table = pa.Table.from_pandas(group, preserve_index=False)
                pq.write_table(table, temp_file, compression=compression)
                temp_file.replace(target_file)
                written_paths.append(target_file)
                logger.debug("Wrote partition %s (%d rows)", target_file.name, len(group))
            except Exception as e:
                temp_file.unlink(missing_ok=True)
                raise IOError(f"Failed to write Parquet partition {target_file}: {e}") from e

        return written_paths

    def read_events(
        self,
        columns: Optional[List[str]] = None,
        filters: Optional[List[Any]] = None,
    ) -> pd.DataFrame:
        """
        Read events across all Parquet shards with optional column pruning and partition filters.
        """
        parquet_files = list(self.base_dir.rglob("*.parquet"))
        if not parquet_files:
            return pd.DataFrame()

        try:
            dataset = pq.ParquetDataset(self.base_dir, filters=filters)
            table = dataset.read(columns=columns)
            return table.to_pandas()
        except Exception as e:
            logger.warning("Could not read Parquet dataset: %s. Falling back to file scan.", e)
            dfs = []
            for pf in parquet_files:
                try:
                    df = pq.read_table(pf, columns=columns).to_pandas()
                    dfs.append(df)
                except Exception as read_err:
                    logger.error("Error reading %s: %read_err", pf, read_err)
            if dfs:
                return pd.concat(dfs, ignore_index=True)
            return pd.DataFrame()

    def get_storage_stats(self) -> Dict[str, Any]:
        """Return total file count, total size on disk, and partition count."""
        parquet_files = list(self.base_dir.rglob("*.parquet"))
        total_bytes = sum(f.stat().st_size for f in parquet_files if f.is_file())
        return {
            "total_files": len(parquet_files),
            "total_size_bytes": total_bytes,
            "total_size_mb": round(total_bytes / (1024 * 1024), 2),
            "base_dir": str(self.base_dir),
        }
