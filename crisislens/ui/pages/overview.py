"""
CrisisLens AI — Overview Dashboard Screen.

Displays key operational metrics, activity trends, geographic distributions,
and latest event streams with strict separation of Date Semantics.
"""

from typing import Dict, Any, Optional
from datetime import datetime, date, timedelta
import streamlit as st
import pandas as pd

from crisislens.ui.data_service import DataService
from crisislens.ui.charts import (
    create_activity_trend_figure,
    create_quad_class_donut,
    create_country_bar_chart,
)
from crisislens.ui.components import (
    render_metric_card,
    render_freshness_banner,
    render_empty_state,
)


def render_overview_page(data_service: DataService):
    """Render the Overview dashboard screen."""
    st.markdown("## 🌐 Global Crisis & Event Overview")
    st.markdown(
        "<p style='color: #BDBDBD; margin-top: -10px; font-size: 0.95rem;'>"
        "Real-time monitoring of global event streams, conflict dynamics, and spatial distribution."
        "</p>",
        unsafe_allow_html=True,
    )

    # 1. Pipeline Status & Data Freshness
    freshness_info = data_service.get_data_freshness_info()
    render_freshness_banner(freshness_info)

    if not freshness_info.get("has_data", False):
        render_empty_state(
            title="Database Empty",
            message="No events found in DuckDB. Run the ingestion pipeline via CLI: <code>python -m crisislens.ingestion.cli --latest</code>",
        )
        return

    # 2. Date Semantics & Filtering Controls
    with st.expander("⚙️ Filter & Date Semantic Controls", expanded=True):
        col_ctrl1, col_ctrl2 = st.columns([1, 1])

        with col_ctrl1:
            date_semantic = st.radio(
                "📅 Date Interpretation Mode:",
                options=["Event Context Date (SQLDATE)", "Reporting Activity Time (DATEADDED)"],
                help=(
                    "• Event Context Date: When the political/social event occurred in history.\n"
                    "• Reporting Activity Time: When the article was ingested and recorded by GDELT."
                ),
            )
            use_reporting_time = (date_semantic == "Reporting Activity Time (DATEADDED)")

        with col_ctrl2:
            # Determine default bounds
            if use_reporting_time:
                max_d_str = freshness_info.get("max_reporting_time", "")[:10]
                min_d_str = freshness_info.get("min_reporting_time", "")[:10]
            else:
                max_d_str = freshness_info.get("max_event_date", "")
                min_d_str = freshness_info.get("min_event_date", "")

            try:
                max_date = datetime.strptime(max_d_str, "%Y-%m-%d").date()
                min_date = datetime.strptime(min_d_str, "%Y-%m-%d").date()
            except (ValueError, TypeError):
                max_date = date.today()
                min_date = max_date - timedelta(days=30)

            # Limit default span to 30 days if range is huge
            default_start = max(min_date, max_date - timedelta(days=30))

            date_range = st.date_input(
                "Select Date Range:",
                value=(default_start, max_date),
                min_value=min_date,
                max_value=max_date,
            )

    start_date_str = None
    end_date_str = None
    if isinstance(date_range, tuple) and len(date_range) == 2:
        start_date_str = str(date_range[0])
        end_date_str = str(date_range[1])
    elif isinstance(date_range, (list, tuple)) and len(date_range) == 1:
        start_date_str = str(date_range[0])
        end_date_str = str(date_range[0])

    # 3. KPI Metrics Row
    metrics = data_service.get_overview_summary_metrics(
        date_start=start_date_str,
        date_end=end_date_str,
        use_reporting_time=use_reporting_time,
    )

    kpi1, kpi2, kpi3, kpi4 = st.columns(4)
    with kpi1:
        render_metric_card(
            label="Total Events",
            value=metrics["total_events"],
            subtext="In selected time window",
            accent_color="#2196F3",
        )
    with kpi2:
        render_metric_card(
            label="Active Geographies",
            value=metrics["distinct_countries"],
            subtext="Distinct sovereign territories",
            accent_color="#4CAF50",
        )
    with kpi3:
        render_metric_card(
            label="Conflict Ratio",
            value=f"{metrics['conflict_ratio_pct']}%",
            subtext=f"{metrics['conflict_events']:,} Conflict events",
            accent_color="#FF9800" if metrics["conflict_ratio_pct"] < 50 else "#F44336",
        )
    with kpi4:
        render_metric_card(
            label="Avg Goldstein Score",
            value=f"{metrics['avg_goldstein']:.2f}",
            subtext=f"Tone: {metrics['avg_tone']:.2f} | Top: {metrics['top_actor'][:12]}",
            accent_color="#9C27B0",
        )

    # 4. Interactive Visualizations
    st.markdown("### 📊 Activity Dynamics & Geography")

    trend_df = data_service.get_activity_trend(
        date_start=start_date_str,
        date_end=end_date_str,
        use_reporting_time=use_reporting_time,
    )

    col_chart_left, col_chart_right = st.columns([1.6, 1.0])

    with col_chart_left:
        axis_title = "Reporting Date (DATEADDED)" if use_reporting_time else "Event Context Date (SQLDATE)"
        fig_trend = create_activity_trend_figure(trend_df, date_axis_title=axis_title)
        st.plotly_chart(fig_trend, use_container_width=True)

    with col_chart_right:
        quad_df = data_service.get_quad_class_distribution(
            date_start=start_date_str,
            date_end=end_date_str,
            use_reporting_time=use_reporting_time,
        )
        fig_quad = create_quad_class_donut(quad_df)
        st.plotly_chart(fig_quad, use_container_width=True)

    # Top Countries Distribution
    country_df = data_service.get_country_distribution(
        date_start=start_date_str,
        date_end=end_date_str,
        use_reporting_time=use_reporting_time,
        limit=12,
    )
    if not country_df.empty:
        fig_country = create_country_bar_chart(country_df)
        st.plotly_chart(fig_country, use_container_width=True)

    # 5. Recent Event Ingestion Feed
    st.markdown("### ⚡ Live Ingestion Stream (Latest Events)")
    recent_df = data_service.get_recent_events_feed(limit=15)
    if not recent_df.empty:
        # Format table for display
        display_df = recent_df.copy()
        display_df = display_df.rename(columns={
            "event_id": "Event ID",
            "reporting_time": "Ingestion Time (UTC)",
            "event_date": "Event Date",
            "actor1_name": "Actor 1",
            "actor2_name": "Actor 2",
            "event_code": "CAMEO Code",
            "quad_class": "Class",
            "goldstein_scale": "Goldstein",
            "action_geo_name": "Location",
            "action_country": "Country",
            "source_url": "Source Article",
        })


        st.dataframe(
            display_df,
            use_container_width=True,
            hide_index=True,
            column_config={
                "Source Article": st.column_config.LinkColumn("Source Article", display_text="Open News Link"),
                "Goldstein": st.column_config.NumberColumn("Goldstein", format="%.1f"),
            },
        )
    else:
        st.info("No recent events to display.")
