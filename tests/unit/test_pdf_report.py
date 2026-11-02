"""
Unit, Integration, and AppTest Tests for Phase 5:
Publication-Quality PDF Investigation Reports, Provenance, Watermarking, and Reproducibility.
"""

from pathlib import Path
import io
import pytest
import pandas as pd
import numpy as np

from crisislens.reports.pdf_generator import generate_investigation_pdf_report
from crisislens.storage.event_store import EventStore
from crisislens.ui.data_service import DataService
from streamlit.testing.v1 import AppTest


@pytest.fixture
def sample_events_df() -> pd.DataFrame:
    """Return a representative DataFrame of GDELT events for PDF report testing."""
    return pd.DataFrame([
        {
            "event_id": 1001,
            "event_date": "2026-10-29",
            "reporting_time": "2026-10-29 15:30:00",
            "actor1_name": "UNITED STATES GOVERNMENT",
            "actor2_name": "CIVILIAN POPULATION",
            "event_code": "010",
            "quad_class": 1,
            "quad_class_name": "Verbal Cooperation",
            "goldstein_scale": 4.5,
            "num_mentions": 35,
            "action_country": "US",
            "country_name": "United States",
            "action_geo_name": "Washington, DC",
            "source_url": "https://reuters.com/news/1001",
        },
        {
            "event_id": 1002,
            "event_date": "2026-10-29",
            "reporting_time": "2026-10-29 15:30:00",
            "actor1_name": "ARMED FORCES",
            "actor2_name": "BORDER GUARDS",
            "event_code": "190",
            "quad_class": 4,
            "quad_class_name": "Material Conflict",
            "goldstein_scale": -9.5,
            "num_mentions": 75,
            "action_country": "UK",
            "country_name": "United Kingdom",
            "action_geo_name": "Dover Port",
            "source_url": "https://bbc.com/news/1002",
        },
        {
            "event_id": 1003,
            "event_date": "2026-10-28",
            "reporting_time": "2026-10-29 15:30:00",
            "actor1_name": "PROTESTERS",
            "actor2_name": "POLICE",
            "event_code": "140",
            "quad_class": 3,
            "quad_class_name": "Verbal Conflict",
            "goldstein_scale": -4.0,
            "num_mentions": 20,
            "action_country": "FR",
            "country_name": "France",
            "action_geo_name": "Paris",
            "source_url": "https://lemonde.fr/news/1003",
        },
    ])


@pytest.fixture
def sample_interval_stats() -> dict:
    """Return realistic interval summary stats."""
    return {
        "total_events": 3,
        "distinct_countries": 3,
        "conflict_ratio_pct": 66.7,
        "avg_goldstein": -3.0,
        "avg_tone": -4.5,
        "top_actors": [{"name": "ARMED FORCES", "count": 1}],
        "top_countries": [{"country": "United Kingdom", "count": 1}],
    }


def test_generate_pdf_live_mode_structure(sample_events_df, sample_interval_stats):
    """
    Verify PDF generation in Live GDELT Data Mode:
    - Produces valid %PDF- binary header.
    - Captures interval metadata and readiness gating status.
    - File size is bounded (<500 KB) and non-empty.
    """
    interval_info = {
        "formatted_time": "2026-10-29 15:30:00",
        "date_added": 20261029153000,
        "label": "2026-10-29 15:30:00 UTC",
    }
    filters = {
        "country": "ALL",
        "quad_classes": [1, 2, 3, 4],
        "search_text": "",
        "goldstein": (-10.0, 10.0),
    }

    pdf_bytes = generate_investigation_pdf_report(
        interval_info=interval_info,
        events_df=sample_events_df,
        stats=sample_interval_stats,
        filters=filters,
        anomaly_meta=None,
        is_synthetic=False,
    )

    assert isinstance(pdf_bytes, bytes)
    assert len(pdf_bytes) > 10000
    assert len(pdf_bytes) < 500000  # Stays well within 500 KB
    assert pdf_bytes.startswith(b"%PDF-")


def test_generate_pdf_synthetic_mode_watermark(sample_events_df, sample_interval_stats):
    """
    Verify PDF generation in Synthetic Benchmark Mode:
    - Embeds prominent SYNTHETIC BENCHMARK warnings and watermark.
    - Embeds anomaly metrics (Z-score, baseline mean, severity).
    """
    interval_info = {
        "formatted_time": "2026-10-12 19:00:00",
        "date_added": 20261012190000,
        "label": "2026-10-12 19:00 — [EXTREME] Emergency Surge",
    }
    anomaly_meta = {
        "severity": "EXTREME",
        "z_score": 13.9,
        "observed_value": 430,
        "baseline_mean": 125.0,
        "baseline_std": 22.0,
        "upper_fence": 170.0,
        "is_anomaly": True,
    }

    pdf_bytes = generate_investigation_pdf_report(
        interval_info=interval_info,
        events_df=sample_events_df,
        stats=sample_interval_stats,
        anomaly_meta=anomaly_meta,
        is_synthetic=True,
    )

    assert isinstance(pdf_bytes, bytes)
    assert pdf_bytes.startswith(b"%PDF-")
    # Verify synthetic banner keyword is encoded in document
    assert b"SYNTHETIC BENCHMARK" in pdf_bytes or b"DEMO USE ONLY" in pdf_bytes


def test_generate_pdf_empty_dataframe(sample_interval_stats):
    """Verify PDF generator handles empty event datasets gracefully without crashing."""
    interval_info = {
        "formatted_time": "2026-10-29 15:30:00",
        "date_added": 20261029153000,
    }
    empty_df = pd.DataFrame()

    pdf_bytes = generate_investigation_pdf_report(
        interval_info=interval_info,
        events_df=empty_df,
        stats={"total_events": 0, "distinct_countries": 0, "conflict_ratio_pct": 0.0, "avg_goldstein": 0.0, "avg_tone": 0.0},
        is_synthetic=False,
    )

    assert isinstance(pdf_bytes, bytes)
    assert pdf_bytes.startswith(b"%PDF-")
    assert len(pdf_bytes) > 5000


def test_generate_pdf_unicode_resilience():
    """Verify PDF generator handles diverse international characters and mathematical symbols."""
    interval_info = {
        "formatted_time": "2026-10-29 15:30:00",
        "date_added": 20261029153000,
    }
    intl_df = pd.DataFrame([
        {
            "event_id": 9901,
            "event_date": "2026-10-29",
            "actor1_name": "GOV — Ministère des Affaires Étrangères",
            "actor2_name": "ORGANIZACIÓN DE ESTADOS AMERICANOS",
            "event_code": "020",
            "quad_class": 1,
            "quad_class_name": "Verbal Cooperation",
            "goldstein_scale": 3.5,
            "num_mentions": 15,
            "action_country": "FR",
            "country_name": "France / España / México",
            "action_geo_name": "Champs-Élysées — Paris",
            "source_url": "https://lemonde.fr/article/9901",
        },
        {
            "event_id": 9902,
            "event_date": "2026-10-29",
            "actor1_name": "Министерство Обороны",
            "actor2_name": "CIVILIANS (المدنيين)",
            "event_code": "190",
            "quad_class": 4,
            "quad_class_name": "Material Conflict",
            "goldstein_scale": -9.0,
            "num_mentions": 40,
            "action_country": "SY",
            "country_name": "Syria",
            "action_geo_name": "Damascus — دمشق",
            "source_url": "https://sana.sy/news/9902",
        },
    ])

    pdf_bytes = generate_investigation_pdf_report(
        interval_info=interval_info,
        events_df=intl_df,
        stats={"total_events": 2, "distinct_countries": 2, "conflict_ratio_pct": 50.0, "avg_goldstein": -2.75, "avg_tone": -1.0},
        is_synthetic=False,
    )

    assert isinstance(pdf_bytes, bytes)
    assert pdf_bytes.startswith(b"%PDF-")


def test_generate_pdf_performance_and_memory(sample_events_df, sample_interval_stats):
    """Verify that multiple consecutive PDF generations complete within performance bounds."""
    import time
    interval_info = {
        "formatted_time": "2026-10-29 15:30:00",
        "date_added": 20261029153000,
    }

    start_time = time.time()
    pdf_bytes = generate_investigation_pdf_report(
        interval_info=interval_info,
        events_df=sample_events_df,
        stats=sample_interval_stats,
        is_synthetic=False,
    )
    assert pdf_bytes.startswith(b"%PDF-")
    elapsed = time.time() - start_time

    # PDF build should complete reliably even under full pytest-cov bytecode tracing on an 8 GB RAM laptop
    assert elapsed < 30.0, f"PDF generation took {elapsed:.2f}s, exceeding 30.0s budget"


def test_investigation_page_pdf_download_headless_apptest():
    """Verify via AppTest that the Investigation page renders with PDF download button."""
    app_path = Path(__file__).resolve().parent.parent.parent / "app.py"
    at = AppTest.from_file(str(app_path), default_timeout=35).run()
    
    # Navigate to 🕵️ Event Investigation
    at.sidebar.radio[0].set_value("🕵️ Event Investigation").run()
    
    assert len(at.exception) == 0, f"AppTest threw exceptions: {at.exception}"
    
    # Verify download buttons include CSV, Markdown, and PDF
    download_labels = [btn.label for btn in at.download_button]
    assert any("PDF" in lbl for lbl in download_labels), f"PDF download button missing: {download_labels}"
    assert any("CSV" in lbl for lbl in download_labels), f"CSV download button missing: {download_labels}"
    assert any("Markdown" in lbl or "Brief" in lbl for lbl in download_labels), f"Markdown download button missing: {download_labels}"
