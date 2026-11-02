"""
GDELT 2.0 Ingestion Command Line Interface.

Usage:
    python -m crisislens.ingestion.cli --latest
    python -m crisislens.ingestion.cli --file path/to/20261029153000.export.CSV.zip
    python -m crisislens.ingestion.cli --status
    python -m crisislens.ingestion.cli --query "SELECT event_date, count(*) FROM events GROUP BY 1"
"""

import argparse
import sys
import tomllib
from pathlib import Path
import logging

from crisislens.ingestion.pipeline import IngestionPipeline
from crisislens.storage.event_store import EventStore
from crisislens.storage.parquet_store import ParquetStore

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("crisislens.cli")


def get_paths_from_config(root_dir: Path) -> dict:
    """Read paths from settings.toml or default locations."""
    config_file = root_dir / "config" / "settings.toml"
    chunk_size = 50000

    if config_file.exists():
        try:
            with open(config_file, "rb") as f:
                cfg = tomllib.load(f)
                chunk_size = cfg.get("data", {}).get("chunk_size", 50000)
        except Exception as e:
            logger.warning("Could not read config file: %s", e)

    return {
        "raw_dir": root_dir / "data" / "raw",
        "parquet_dir": root_dir / "data" / "processed",
        "duckdb_path": root_dir / "crisislens.duckdb",
        "chunk_size": chunk_size,
    }


def main():
    parser = argparse.ArgumentParser(description="CrisisLens AI Ingestion & Storage CLI")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--latest", action="store_true", help="Fetch and ingest the latest 15-minute GDELT update")
    group.add_argument("--file", type=str, help="Ingest a local .export.CSV.zip or .CSV file")
    group.add_argument("--url", type=str, help="Download and ingest from a specific GDELT URL")
    group.add_argument("--status", action="store_true", help="Display DuckDB row counts, manifest audit log, and Parquet storage size")
    group.add_argument("--query", type=str, help="Execute a read-only SQL query against DuckDB")

    parser.add_argument("--force", action="store_true", help="Force reprocessing even if file already exists in manifest")
    parser.add_argument("--max-rows", type=int, default=None, help="Limit number of rows to ingest (for testing/debugging)")

    args = parser.parse_args()

    # Determine project root (2 levels up from crisislens/ingestion)
    project_root = Path(__file__).resolve().parent.parent.parent
    paths = get_paths_from_config(project_root)

    if args.status:
        store = EventStore(paths["duckdb_path"], read_only=True)
        pstore = ParquetStore(paths["parquet_dir"])
        total_events = store.get_total_events_count()
        manifest = store.get_manifest_history()
        storage_stats = pstore.get_storage_stats()

        print("\n================ CRISISLENS STORAGE STATUS ================")
        print(f"Database Path       : {paths['duckdb_path']}")
        print(f"Total Events Rows   : {total_events:,}")
        print(f"Parquet Storage     : {storage_stats['total_size_mb']} MB ({storage_stats['total_files']} files)")
        print("\nRecent Ingestion Batches:")
        if manifest.empty:
            print("  (No ingestion runs recorded yet)")
        else:
            print(manifest[["batch_id", "source_file", "status", "valid_rows", "started_at"]].to_string(index=False))
        print("===========================================================\n")
        store.close()
        return

    if args.query:
        store = EventStore(paths["duckdb_path"], read_only=True)
        try:
            df = store.query(args.query)
            print("\nQuery Results:")
            print(df.to_string(index=False))
        except Exception as e:
            print(f"Query error: {e}", file=sys.stderr)
            sys.exit(1)
        finally:
            store.close()
        return

    # Ingestion Pipeline Run
    pipeline = IngestionPipeline(
        raw_dir=paths["raw_dir"],
        parquet_dir=paths["parquet_dir"],
        duckdb_path=paths["duckdb_path"],
        chunk_size=paths["chunk_size"],
    )

    if args.latest:
        print("Starting ingestion of latest GDELT 2.0 update...")
        res = pipeline.run_latest(force=args.force, max_rows=args.max_rows)
    elif args.file:
        file_path = Path(args.file)
        if not file_path.exists():
            print(f"Error: Specified file does not exist: {file_path}", file=sys.stderr)
            sys.exit(1)
        print(f"Starting ingestion of local file {file_path.name}...")
        if file_path.suffix.lower() == ".zip":
            res = pipeline.ingest_archive(file_path, force=args.force, max_rows=args.max_rows)
        else:
            res = pipeline.ingest_tsv(file_path, force=args.force, max_rows=args.max_rows)
    elif args.url:
        print(f"Starting download and ingestion of {args.url}...")
        res = pipeline.ingest_url(args.url, force=args.force, max_rows=args.max_rows)
    else:
        parser.print_help()
        return

    print("\n================ INGESTION SUMMARY ================")
    print(f"Batch ID            : {res.batch_id}")
    print(f"Source File         : {res.source_file}")
    print(f"Status              : {res.status}")
    print(f"Raw Rows Sampled    : {res.raw_rows:,}")
    print(f"Valid Rows Ingested : {res.valid_rows:,}")
    print(f"Rejected Rows       : {res.rejected_rows:,}")
    print(f"Parquet Partitions  : {len(res.parquet_files)}")
    print(f"Date Range          : {res.date_range_start} to {res.date_range_end}")
    print(f"Execution Duration  : {res.duration_seconds}s")
    if res.error_message:
        print(f"Notes / Error       : {res.error_message}")
    print("===================================================\n")

    if res.status == "FAILED":
        sys.exit(1)


if __name__ == "__main__":
    main()
