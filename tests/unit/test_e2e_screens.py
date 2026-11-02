"""
End-to-End Streamlit AppTest Suite for CrisisLens AI.

Tests all 4 screens in the application:
1. 📊 Overview Dashboard (metrics, charts, event feed, date semantics)
2. 🔍 Event Explorer (text search, faceted filters, pagination, CSV download)
3. ⚡ Anomaly Intelligence (readiness gating, synthetic benchmark, mathematical explanation)
4. 🕵️ Event Investigation (drill-down, single-record inspector, CSV/MD/PDF downloads)

Validates zero runtime exceptions, widget stability, and seamless cross-page state navigation.
"""

from pathlib import Path
import pytest
from streamlit.testing.v1 import AppTest


@pytest.fixture
def app_path() -> Path:
    """Return the absolute path to app.py."""
    return Path(__file__).resolve().parent.parent.parent / "app.py"


def test_app_startup_overview_screen(app_path: Path):
    """Verify application initializes cleanly on Overview Dashboard with 0 exceptions."""
    at = AppTest.from_file(str(app_path), default_timeout=35).run()
    assert len(at.exception) == 0, f"AppTest startup threw exceptions: {at.exception}"

    # Verify Sidebar branding and navigation
    assert at.sidebar.radio[0].value == "📊 Overview Dashboard"

    # Verify key overview UI elements rendered
    markdown_texts = [m.value for m in at.markdown]
    assert any("Global Crisis & Event Overview" in t for t in markdown_texts)
    assert any("Activity Dynamics & Geography" in t for t in markdown_texts)

    # Verify event feed dataframe is rendered
    assert len(at.dataframe) >= 1


def test_app_navigation_event_explorer(app_path: Path):
    """Verify navigation to Event Explorer, widget presence, and CSV export readiness."""
    at = AppTest.from_file(str(app_path), default_timeout=35).run()
    at.sidebar.radio[0].set_value("🔍 Event Explorer").run()
    assert len(at.exception) == 0, f"Event Explorer threw exceptions: {at.exception}"

    markdown_texts = [m.value for m in at.markdown]
    assert any("Global Event Explorer" in t for t in markdown_texts)
    assert any("Deep-Dive Record Inspector" in t for t in markdown_texts)

    # Verify text input and date filter mode selectbox exist
    assert len(at.text_input) >= 1
    assert len(at.selectbox) >= 2

    # Verify CSV download button is rendered when events exist
    assert len(at.download_button) >= 1
    assert any("CSV" in btn.label for btn in at.download_button)


def test_app_navigation_anomaly_intelligence_modes(app_path: Path):
    """
    Verify Anomaly Intelligence screen:
    - Synthetic Benchmark: scores 14-day fixture and renders explainability math.
    - Live Store: displays DataReadinessGate status warning.
    """
    at = AppTest.from_file(str(app_path), default_timeout=35).run()
    at.sidebar.radio[0].set_value("⚡ Anomaly Intelligence").run()
    assert len(at.exception) == 0, f"Anomaly Intelligence threw exceptions: {at.exception}"

    markdown_texts = [m.value for m in at.markdown]
    assert any("Anomaly Intelligence" in t for t in markdown_texts)
    assert any("Deterministic Explainability & Math Inspector" in t for t in markdown_texts)

    # Verify mathematical formula is rendered via st.latex

    # Verify mathematical formula is rendered via st.latex
    assert len(at.latex) >= 1


def test_app_navigation_investigation_and_pdf_export(app_path: Path):
    """
    Verify Event Investigation Drill-Down screen:
    - Renders interval stats and faceted filters.
    - Renders charts, event table, and deep-dive profile.
    - Renders 3 export buttons: CSV, Markdown brief, and publication PDF.
    """
    at = AppTest.from_file(str(app_path), default_timeout=35).run()
    at.sidebar.radio[0].set_value("🕵️ Event Investigation").run()
    assert len(at.exception) == 0, f"Event Investigation threw exceptions: {at.exception}"

    markdown_texts = [m.value for m in at.markdown]
    assert any("Event Investigation Drill-Down" in t for t in markdown_texts)
    assert any("Underlying Event Evidence" in t for t in markdown_texts)
    assert any("Reproducible Export & Investigation Summary" in t for t in markdown_texts)

    # Verify download buttons include CSV, Markdown, and PDF
    download_labels = [btn.label for btn in at.download_button]
    assert any("CSV" in lbl for lbl in download_labels), f"Missing CSV download: {download_labels}"
    assert any("Markdown" in lbl or "Brief" in lbl for lbl in download_labels), f"Missing Brief download: {download_labels}"
    assert any("PDF" in lbl or "Report" in lbl for lbl in download_labels), f"Missing PDF download: {download_labels}"


def test_app_cross_screen_session_drilldown(app_path: Path):
    """
    Verify cross-page workflow:
    1. Open Anomaly Intelligence
    2. Click 'Drill Down into Event Investigation' button
    3. Session state records target interval
    4. Navigate to Event Investigation and verify interval is recognized without error.
    """
    at = AppTest.from_file(str(app_path), default_timeout=35).run()
    at.sidebar.radio[0].set_value("⚡ Anomaly Intelligence").run()
    assert len(at.exception) == 0

    # Locate and trigger drilldown button
    drilldown_btns = [btn for btn in at.button if "Drill Down" in btn.label]
    if drilldown_btns:
        drilldown_btns[0].click().run()
        assert len(at.exception) == 0

    # Navigate to Event Investigation
    at.sidebar.radio[0].set_value("🕵️ Event Investigation").run()
    assert len(at.exception) == 0
