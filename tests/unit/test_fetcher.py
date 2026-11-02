"""
Unit tests for GDELT Fetcher module using mocked network responses.
Never requires a live network connection.
"""

from pathlib import Path
import hashlib
import zipfile
import io
import pytest
from unittest.mock import patch, MagicMock
import requests

from crisislens.ingestion.fetcher import (
    fetch_last_update_info,
    download_file,
    extract_archive,
    FetchError,
    ChecksumError,
    ArchiveError,
)


def test_fetch_last_update_info_success():
    """Verify parsing of valid lastupdate.txt feed."""
    mock_text = (
        "111316 e8563898afb153412cbec36236889e1e http://data.gdeltproject.org/gdeltv2/20261029153000.export.CSV.zip\n"
        "160759 00803645cb92baced606ed3f0c460843 http://data.gdeltproject.org/gdeltv2/20261029153000.mentions.CSV.zip\n"
        "7200971 a7d50c3405b0dab98d23713843863df0 http://data.gdeltproject.org/gdeltv2/20261029153000.gkg.csv.zip\n"
    )
    with patch("requests.get") as mock_get:
        mock_resp = MagicMock()
        mock_resp.text = mock_text
        mock_resp.raise_for_status.return_value = None
        mock_get.return_value = mock_resp

        info = fetch_last_update_info()

        assert info["size"] == 111316
        assert info["md5"] == "e8563898afb153412cbec36236889e1e"
        assert info["url"] == "http://data.gdeltproject.org/gdeltv2/20261029153000.export.CSV.zip"
        assert info["filename"] == "20261029153000.export.CSV.zip"
        assert info["timestamp"] == "20261029153000"


def test_fetch_last_update_info_missing_export_entry():
    """Verify error raised when .export.CSV.zip entry is absent."""
    mock_text = "160759 00803645cb92baced606ed3f0c460843 http://data.gdeltproject.org/gdeltv2/20261029153000.mentions.CSV.zip\n"
    with patch("requests.get") as mock_get:
        mock_resp = MagicMock()
        mock_resp.text = mock_text
        mock_resp.raise_for_status.return_value = None
        mock_get.return_value = mock_resp

        with pytest.raises(FetchError, match="No '.export.CSV.zip' entry"):
            fetch_last_update_info()


def test_fetch_last_update_info_retry_exhaustion():
    """Verify retry backoff exhaustion on persistent HTTP failure."""
    with patch("requests.get") as mock_get:
        mock_get.side_effect = requests.RequestException("Connection timed out")

        with pytest.raises(FetchError, match="Failed to fetch GDELT lastupdate after 3 attempts"):
            fetch_last_update_info(max_retries=3, backoff_factor=0.01)


def test_download_file_success_with_md5(tmp_path: Path):
    """Verify streaming download with MD5 checksum verification."""
    payload = b"col1\tcol2\nval1\tval2\n"
    expected_md5 = hashlib.md5(payload).hexdigest()
    dest = tmp_path / "test.zip"

    with patch("requests.get") as mock_get:
        mock_resp = MagicMock()
        mock_resp.raise_for_status.return_value = None
        mock_resp.iter_content.return_value = [payload]
        mock_resp.__enter__.return_value = mock_resp
        mock_resp.__exit__.return_value = None
        mock_get.return_value = mock_resp

        result = download_file("http://example.com/test.zip", dest, expected_md5=expected_md5)
        assert result.exists()
        assert result.read_bytes() == payload
        # Ensure temporary file is gone
        assert not dest.with_name("test.zip.tmp").exists()


def test_download_file_md5_mismatch(tmp_path: Path):
    """Verify download failure and temp file cleanup on checksum mismatch."""
    payload = b"corrupted payload"
    dest = tmp_path / "test_corrupt.zip"

    with patch("requests.get") as mock_get:
        mock_resp = MagicMock()
        mock_resp.raise_for_status.return_value = None
        mock_resp.iter_content.return_value = [payload]
        mock_resp.__enter__.return_value = mock_resp
        mock_resp.__exit__.return_value = None
        mock_get.return_value = mock_resp

        with pytest.raises(FetchError, match="MD5 mismatch"):
            download_file(
                "http://example.com/test.zip",
                dest,
                expected_md5="00000000000000000000000000000000",
                max_retries=1,
            )
        assert not dest.exists()
        assert not dest.with_name("test_corrupt.zip.tmp").exists()


def test_extract_archive_success(tmp_path: Path):
    """Verify safe archive extraction of .export.CSV."""
    zip_path = tmp_path / "sample.export.CSV.zip"
    extract_dir = tmp_path / "extracted"
    content = b"row1\nrow2\n"

    # Build valid zip in memory
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("sample.export.CSV", content)
    zip_path.write_bytes(buf.getvalue())

    extracted_file = extract_archive(zip_path, extract_dir)
    assert extracted_file.exists()
    assert extracted_file.name == "sample.export.CSV"
    assert extracted_file.read_bytes() == content


def test_extract_archive_invalid_zip(tmp_path: Path):
    """Verify error raised on invalid zip file."""
    fake_zip = tmp_path / "not_a_zip.zip"
    fake_zip.write_bytes(b"garbage bytes")

    with pytest.raises(ArchiveError, match="not a valid zip archive"):
        extract_archive(fake_zip, tmp_path / "out")
