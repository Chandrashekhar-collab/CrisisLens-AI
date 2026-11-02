"""
CrisisLens AI — Streamlit Application Entrypoint.

Placement-quality Data Science & AI/ML Intelligence Dashboard.
Integrates live GDELT 2.0 public event records, DuckDB columnar analytics,
and interactive Plotly data visualizations.
"""

from pathlib import Path
import tomllib
import logging
import streamlit as st

from crisislens.ui.data_service import DataService
from crisislens.ui.pages.overview import render_overview_page
from crisislens.ui.pages.explorer import render_explorer_page
from crisislens.ui.pages.anomaly import render_anomaly_page
from crisislens.ui.pages.investigation import render_investigation_page

# Configure root logger
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("crisislens.app")

# Page Configuration
st.set_page_config(
    page_title="CrisisLens AI — Global Event Intelligence",
    page_icon="🌍",
    layout="wide",
    initial_sidebar_state="expanded",
)


@st.cache_resource
def get_data_service() -> DataService:
    """Instantiate and cache the DataService instance with DuckDB connection."""
    project_root = Path(__file__).resolve().parent
    db_path = project_root / "crisislens.duckdb"
    static_data_dir = project_root / "crisislens" / "data"
    return DataService(db_path=db_path, static_data_dir=static_data_dir)


def main():
    # Load settings
    project_root = Path(__file__).resolve().parent
    config_path = project_root / "config" / "settings.toml"
    config = {}
    if config_path.exists():
        with open(config_path, "rb") as f:
            config = tomllib.load(f)

    data_service = get_data_service()

    # Sidebar Navigation & Platform Status
    with st.sidebar:
        st.markdown(
            """
            <div style="display: flex; align-items: center; gap: 10px; margin-bottom: 8px;">
                <span style="font-size: 2rem;">🌍</span>
                <div>
                    <h2 style="margin: 0; padding: 0; font-size: 1.35rem; color: #FFFFFF;">CrisisLens AI</h2>
                    <span style="font-size: 0.78rem; color: #64B5F6; font-weight: 600; text-transform: uppercase;">
                        Global Event Intelligence
                    </span>
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

        st.markdown("---")

        nav_selection = st.radio(
            "🧭 Navigation:",
            options=[
                "📊 Overview Dashboard",
                "🔍 Event Explorer",
                "⚡ Anomaly Intelligence",
                "🕵️ Event Investigation",
            ],
            index=0,
        )

        st.markdown("---")
        st.markdown("**Platform Modules:**")
        st.caption("• 📊 Overview & Event Dynamics *(Active)*")
        st.caption("• 🔍 Granular Event Explorer *(Active)*")
        st.caption("• ⚡ Anomaly Intelligence *(Level 1 Baseline)*")
        st.caption("• 🕵️ Event Investigation & PDF Export *(Active)*")

        st.markdown("---")
        # Sidebar System Telemetry
        st.markdown("##### 💻 System Environment")
        st.caption("• **Engine:** DuckDB 2.0 (Read-Only)")
        st.caption("• **Data Source:** GDELT 2.0 Events")
        st.caption("• **Hardware Target:** 8 GB RAM / i3 CPU")

        freshness = data_service.get_data_freshness_info()
        if freshness.get("has_data", False):
            st.caption(f"• **Active Records:** {freshness['total_events']:,}")
            st.caption(f"• **Latest Ingest:** {freshness['latest_ingested_at'][:19]}")

    # Route Page
    if nav_selection == "📊 Overview Dashboard":
        render_overview_page(data_service)
    elif nav_selection == "🔍 Event Explorer":
        render_explorer_page(data_service)
    elif nav_selection == "⚡ Anomaly Intelligence":
        render_anomaly_page(data_service, config)
    elif nav_selection == "🕵️ Event Investigation":
        render_investigation_page(data_service, config)



if __name__ == "__main__":
    main()
