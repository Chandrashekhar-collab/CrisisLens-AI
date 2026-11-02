"""
GDELT 2.0 Ingestion Fetcher.

Handles retrieving metadata from GDELT update feeds, robust file downloading
with retries and timeouts, and safe archive extraction.
"""

from pathlib import Path
import hashlib
import zipfile
import time
import logging
from typing import Dict, Any, Optional
import requests

logger = logging.getLogger(__name__)

DEFAULT_LAST_UPDATE_URL = "http://data.gdeltproject.org/gdeltv2/lastupdate.txt"
DEFAULT_USER_AGENT = "CrisisLensAI/1.0 (Data Science Research Project)"


class FetchError(Exception):
    """Raised when metadata or file download fails."""
    pass


class ChecksumError(Exception):
    """Raised when the downloaded file's MD5 checksum does not match expected value."""
    pass


class ArchiveError(Exception):
    """Raised when extracting the downloaded archive fails or is unsafe."""
    pass


def fetch_last_update_info(
    url: str = DEFAULT_LAST_UPDATE_URL,
    timeout: int = 15,
    max_retries: int = 3,
    backoff_factor: float = 1.0,
) -> Dict[str, Any]:
    """
    Fetch and parse the GDELT 2.0 lastupdate.txt file.

    Format of lastupdate.txt (3 space-delimited columns per line):
    <size_bytes> <md5_hash> <file_url>
    The three files correspond to: .export.CSV.zip (Events), .mentions.CSV.zip, .gkg.csv.zip.

    Returns:
        Dict containing keys: 'url', 'size', 'md5', 'filename', 'timestamp'
    """
    headers = {"User-Agent": DEFAULT_USER_AGENT}
    last_err: Optional[Exception] = None

    for attempt in range(1, max_retries + 1):
        try:
            resp = requests.get(url, headers=headers, timeout=timeout)
            resp.raise_for_status()
            text = resp.text.strip()
            lines = text.splitlines()

            # Find the line corresponding to the Events export file (.export.CSV.zip)
            for line in lines:
                parts = line.strip().split()
                if len(parts) >= 3 and ".export.CSV.zip" in parts[2]:
                    file_size = int(parts[0])
                    file_md5 = parts[1].lower()
                    file_url = parts[2]
                    filename = Path(file_url).name
                    # Filename format: YYYYMMDDHHMMSS.export.CSV.zip
                    timestamp = filename.split(".")[0]
                    return {
                        "url": file_url,
                        "size": file_size,
                        "md5": file_md5,
                        "filename": filename,
                        "timestamp": timestamp,
                    }

            raise FetchError(
                f"No '.export.CSV.zip' entry found in lastupdate feed: {text[:200]}"
            )

        except (requests.RequestException, ValueError) as e:
            last_err = e
            logger.warning(
                "Attempt %d/%d to fetch lastupdate failed: %s",
                attempt,
                max_retries,
                e,
            )
            if attempt < max_retries:
                time.sleep(backoff_factor * (2 ** (attempt - 1)))

    raise FetchError(f"Failed to fetch GDELT lastupdate after {max_retries} attempts: {last_err}")


def download_file(
    url: str,
    dest_path: Path,
    expected_md5: Optional[str] = None,
    timeout: int = 20,
    max_retries: int = 3,
    chunk_size: int = 65536,
    backoff_factor: float = 1.0,
) -> Path:
    """
    Download a file from a URL to dest_path using streaming and atomic file replacement.

    Safeguards:
    - Downloads to a temporary file ({dest_path}.tmp) first.
    - Computes MD5 hash on the fly during streaming.
    - Validates MD5 against expected_md5 if provided.
    - Atomically replaces dest_path only upon complete and verified download.
    - Cleans up .tmp file on failure.
    """
    dest_path = Path(dest_path)
    dest_path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = dest_path.with_name(f"{dest_path.name}.tmp")

    headers = {"User-Agent": DEFAULT_USER_AGENT}
    last_err: Optional[Exception] = None

    for attempt in range(1, max_retries + 1):
        hasher = hashlib.md5()
        try:
            with requests.get(url, headers=headers, stream=True, timeout=timeout) as resp:
                resp.raise_for_status()
                with open(temp_path, "wb") as f:
                    for chunk in resp.iter_content(chunk_size=chunk_size):
                        if chunk:
                            f.write(chunk)
                            hasher.update(chunk)

            downloaded_md5 = hasher.hexdigest().lower()
            if expected_md5 and downloaded_md5 != expected_md5.lower():
                temp_path.unlink(missing_ok=True)
                raise ChecksumError(
                    f"MD5 mismatch for {url}: expected {expected_md5}, got {downloaded_md5}"
                )

            # Atomic rename / replace
            temp_path.replace(dest_path)
            logger.info("Successfully downloaded %s (MD5: %s)", dest_path.name, downloaded_md5)
            return dest_path

        except (requests.RequestException, ChecksumError, OSError) as e:
            last_err = e
            temp_path.unlink(missing_ok=True)
            logger.warning("Download attempt %d/%d failed: %s", attempt, max_retries, e)
            if attempt < max_retries:
                time.sleep(backoff_factor * (2 ** (attempt - 1)))

    raise FetchError(f"Failed to download {url} after {max_retries} attempts: {last_err}")


def extract_archive(
    zip_path: Path,
    extract_dir: Path,
    expected_suffix: str = ".export.CSV",
) -> Path:
    """
    Safely extract a GDELT .export.CSV.zip archive.

    Safeguards:
    - Protects against Zip-Slip path traversal vulnerability.
    - Verifies presence of the expected .export.CSV file.
    - Uses atomic replacement for extracted file.
    """
    zip_path = Path(zip_path)
    extract_dir = Path(extract_dir)
    extract_dir.mkdir(parents=True, exist_ok=True)

    if not zipfile.is_zipfile(zip_path):
        raise ArchiveError(f"File {zip_path} is not a valid zip archive")

    with zipfile.ZipFile(zip_path, "r") as zf:
        members = zf.namelist()
        matching = [m for m in members if m.endswith(expected_suffix)]
        if not matching:
            raise ArchiveError(
                f"Archive {zip_path.name} does not contain file with suffix {expected_suffix}. Contents: {members}"
            )

        target_member = matching[0]

        # Path traversal guard (prevent Zip Slip)
        target_path = (extract_dir / target_member).resolve()
        resolved_extract_dir = extract_dir.resolve()
        try:
            target_path.relative_to(resolved_extract_dir)
        except ValueError:
            raise ArchiveError(f"Security error: Archive member {target_member} attempts path traversal")

        temp_extract = target_path.with_name(f"{target_path.name}.tmp")
        try:
            with zf.open(target_member, "r") as source, open(temp_extract, "wb") as dest:
                while chunk := source.read(65536):
                    dest.write(chunk)
            temp_extract.replace(target_path)
            return target_path
        except Exception as e:
            temp_extract.unlink(missing_ok=True)
            raise ArchiveError(f"Failed to extract {target_member} from {zip_path.name}: {e}") from e


def fetch_recent_masterlist_export_urls(
    count: int = 16,
    masterlist_url: str = "http://data.gdeltproject.org/gdeltv2/masterfilelist.txt",
    timeout: int = 15,
) -> list[Dict[str, Any]]:
    """
    Retrieve the most recent N GDELT 2.0 .export.CSV.zip file descriptors
    using an HTTP Range request against the tail of masterfilelist.txt.
    Avoids downloading the full 129 MB masterfilelist.
    """
    headers = {"User-Agent": DEFAULT_USER_AGENT}
    try:
        # Determine total size with HEAD request
        head_resp = requests.head(masterlist_url, headers=headers, timeout=timeout)
        head_resp.raise_for_status()
        content_length = int(head_resp.headers.get("Content-Length", 0))
        if content_length == 0:
            raise FetchError("Unable to determine masterfilelist.txt size from headers")

        # Each 15-minute update generates ~3 lines in masterfilelist (~350 bytes total).
        # Request enough trailing bytes with safety margin.
        bytes_to_fetch = max(65536, count * 500)
        start_byte = max(0, content_length - bytes_to_fetch)

        range_headers = dict(headers)
        range_headers["Range"] = f"bytes={start_byte}-{content_length - 1}"

        range_resp = requests.get(masterlist_url, headers=range_headers, timeout=timeout)
        range_resp.raise_for_status()

        export_files: list[Dict[str, Any]] = []
        for line in range_resp.text.splitlines():
            parts = line.strip().split()
            if len(parts) >= 3 and ".export.CSV.zip" in parts[2]:
                file_url = parts[2]
                filename = Path(file_url).name
                timestamp = filename.split(".")[0]
                export_files.append({
                    "url": file_url,
                    "size": int(parts[0]),
                    "md5": parts[1].lower(),
                    "filename": filename,
                    "timestamp": timestamp,
                })

        # Return the requested number of most recent items
        return export_files[-count:]

    except Exception as e:
        logger.error("Failed to retrieve recent masterfilelist URLs: %s", e)
        raise FetchError(f"Could not fetch recent masterfilelist URLs: {e}") from e
