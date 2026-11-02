"""
GDELT 2.0 Ingestion Pipeline Orchestrator.

Coordinates fetching, downloading, validating, stream-parsing,
writing partitioned Parquet files, and upserting into DuckDB with full audit tracking.
"""

from pathlib import Path
from dataclasses import dataclass, field
import uuid
import time
import logging
from typing import Optional, List, Dict, Any

from crisislens.ingestion.fetcher import fetch_last_update_info, download_file, extract_archive
from crisislens.ingestion.validator import validate_raw_file_structure
from crisislens.ingestion.parser import stream_parse_tsv
from crisislens.storage.parquet_store import ParquetStore
from crisislens.storage.event_store import EventStore

logger = logging.getLogger(__name__)


@dataclass
class IngestionResult:
    """Summary of an ingestion pipeline run."""
    batch_id: str
    source_file: str
    status: str  # 'SUCCESS', 'FAILED', 'SKIPPED'
    raw_rows: int = 0
    valid_rows: int = 0
    rejected_rows: int = 0
    parquet_files: List[str] = field(default_factory=list)
    date_range_start: Optional[str] = None
    date_range_end: Optional[str] = None
    duration_seconds: float = 0.0
    error_message: Optional[str] = None


class IngestionPipeline:
    """
    End-to-end ingestion pipeline executing the GDELT 2.0 ETL lifecycle.
    """

    def __init__(
        self,
        raw_dir: Path,
        parquet_dir: Path,
        duckdb_path: Path,
        chunk_size: int = 50000,
    ):
        self.raw_dir = Path(raw_dir)
        self.raw_dir.mkdir(parents=True, exist_ok=True)

        self.parquet_store = ParquetStore(parquet_dir)
        self.event_store = EventStore(duckdb_path, read_only=False)
        self.chunk_size = chunk_size

    def close(self) -> None:
        """Close storage connections."""
        self.event_store.close()

    def run_latest(self, force: bool = False, max_rows: Optional[int] = None) -> IngestionResult:
        """
        Fetch and ingest the latest 15-minute GDELT 2.0 event update.
        """
        logger.info("Fetching latest GDELT update metadata...")
        info = fetch_last_update_info()
        return self.ingest_url(
            url=info["url"],
            expected_md5=info["md5"],
            force=force,
            max_rows=max_rows,
        )

    def ingest_url(
        self,
        url: str,
        expected_md5: Optional[str] = None,
        force: bool = False,
        max_rows: Optional[int] = None,
    ) -> IngestionResult:
        """
        Download and ingest a GDELT .export.CSV.zip from a specified URL.
        """
        filename = Path(url).name
        target_zip = self.raw_dir / filename

        # Idempotency check before download
        if not force and self.event_store.is_file_ingested(filename, file_md5=expected_md5):
            logger.info("File %s already successfully ingested. Skipping (force=False).", filename)
            return IngestionResult(
                batch_id=str(uuid.uuid4())[:8],
                source_file=filename,
                status="SKIPPED",
                error_message="Already ingested (use force=True to reprocess)",
            )

        # Download archive
        logger.info("Downloading %s ...", url)
        download_file(
            url=url,
            dest_path=target_zip,
            expected_md5=expected_md5,
        )

        return self.ingest_archive(target_zip, force=force, max_rows=max_rows, file_md5=expected_md5)

    def ingest_archive(
        self,
        zip_path: Path,
        force: bool = False,
        max_rows: Optional[int] = None,
        file_md5: Optional[str] = None,
    ) -> IngestionResult:
        """
        Extract and ingest a local GDELT .export.CSV.zip archive.
        """
        zip_path = Path(zip_path)
        extracted_tsv = extract_archive(zip_path, self.raw_dir)
        try:
            return self.ingest_tsv(
                tsv_path=extracted_tsv,
                source_name=zip_path.name,
                force=force,
                max_rows=max_rows,
                file_md5=file_md5,
            )
        finally:
            # Clean up intermediate uncompressed TSV to save disk space
            extracted_tsv.unlink(missing_ok=True)

    def ingest_tsv(
        self,
        tsv_path: Path,
        source_name: Optional[str] = None,
        force: bool = False,
        max_rows: Optional[int] = None,
        file_md5: Optional[str] = None,
    ) -> IngestionResult:
        """
        Validate, parse, store Parquet, and upsert DuckDB records from a TSV file.
        """
        start_time = time.time()
        tsv_path = Path(tsv_path)
        source_name = source_name or tsv_path.name
        batch_id = str(uuid.uuid4())

        # Check idempotency
        if not force and self.event_store.is_file_ingested(source_name, file_md5=file_md5):
            logger.info("Source %s already successfully ingested. Skipping.", source_name)
            return IngestionResult(
                batch_id=batch_id[:8],
                source_file=source_name,
                status="SKIPPED",
                error_message="Already ingested",
            )

        # Initialize audit manifest
        self.event_store.record_manifest_start(
            batch_id=batch_id,
            source_file=source_name,
            file_md5=file_md5,
        )

        total_raw = 0
        total_valid = 0
        total_rejected = 0
        all_parquet_paths: List[str] = []
        min_date: Optional[str] = None
        max_date: Optional[str] = None

        try:
            # 1. Validate structure
            validation_report = validate_raw_file_structure(tsv_path)
            if not validation_report.is_valid:
                err_msg = f"Validation failed: {validation_report.sample_errors}"
                self.event_store.record_manifest_finish(
                    batch_id=batch_id,
                    status="FAILED",
                    error_message=err_msg,
                )
                return IngestionResult(
                    batch_id=batch_id,
                    source_file=source_name,
                    status="FAILED",
                    error_message=err_msg,
                )

            # 2. Stream-parse and ingest chunk by chunk
            for chunk_df, raw_count, rejected_count in stream_parse_tsv(
                tsv_path,
                chunk_size=self.chunk_size,
                max_rows=max_rows,
            ):
                total_raw += raw_count
                total_rejected += rejected_count

                if chunk_df.empty:
                    continue

                total_valid += len(chunk_df)

                # Track observed date range
                chunk_min_date = str(chunk_df["event_date"].min())
                chunk_max_date = str(chunk_df["event_date"].max())
                min_date = min(min_date, chunk_min_date) if min_date else chunk_min_date
                max_date = max(max_date, chunk_max_date) if max_date else chunk_max_date

                # 3. Write partitioned Parquet shards atomically
                written_shards = self.parquet_store.write_events_batch(
                    chunk_df,
                    batch_id=batch_id[:8],
                )
                all_parquet_paths.extend([str(p) for p in written_shards])

                # 4. Upsert into DuckDB
                primary_shard_ref = str(written_shards[0]) if written_shards else ""
                self.event_store.upsert_events(chunk_df, parquet_path=primary_shard_ref)

            duration = round(time.time() - start_time, 2)

            # 5. Record successful manifest completion
            self.event_store.record_manifest_finish(
                batch_id=batch_id,
                status="SUCCESS",
                raw_rows=total_raw,
                valid_rows=total_valid,
                rejected_rows=total_rejected,
                date_range_start=min_date,
                date_range_end=max_date,
                parquet_files_count=len(all_parquet_paths),
            )

            logger.info(
                "Ingestion SUCCESS [%s]: %d raw, %d valid, %d rejected in %.2fs",
                source_name,
                total_raw,
                total_valid,
                total_rejected,
                duration,
            )

            return IngestionResult(
                batch_id=batch_id,
                source_file=source_name,
                status="SUCCESS",
                raw_rows=total_raw,
                valid_rows=total_valid,
                rejected_rows=total_rejected,
                parquet_files=all_parquet_paths,
                date_range_start=min_date,
                date_range_end=max_date,
                duration_seconds=duration,
            )

        except Exception as e:
            duration = round(time.time() - start_time, 2)
            err_msg = str(e)
            logger.error("Ingestion FAILED [%s]: %s", source_name, err_msg)
            self.event_store.record_manifest_finish(
                batch_id=batch_id,
                status="FAILED",
                raw_rows=total_raw,
                valid_rows=total_valid,
                rejected_rows=total_rejected,
                error_message=err_msg,
            )
            return IngestionResult(
                batch_id=batch_id,
                source_file=source_name,
                status="FAILED",
                raw_rows=total_raw,
                valid_rows=total_valid,
                rejected_rows=total_rejected,
                duration_seconds=duration,
                error_message=err_msg,
            )
