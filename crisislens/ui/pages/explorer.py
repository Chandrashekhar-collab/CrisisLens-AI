"""
CrisisLens AI — Event Explorer Screen.

Provides multi-dimensional search, faceted filtering, bounded pagination,
CSV export, and deep-dive record inspection.
"""

from typing import Dict, Any, Optional, List
from datetime import datetime, date, timedelta
import streamlit as st
import pandas as pd

from crisislens.ui.data_service import DataService
from crisislens.ui.components import render_empty_state, render_event_detail_card


def render_explorer_page(data_service: DataService):
    """Render the Event Explorer search and filtering screen."""
    st.markdown("## 🔍 Global Event Explorer")
    st.markdown(
        "<p style='color: #BDBDBD; margin-top: -10px; font-size: 0.95rem;'>"
        "Search, filter, and inspect granular GDELT event records across actors, geographies, and CAMEO codes."
        "</p>",
        unsafe_allow_html=True,
    )

    freshness_info = data_service.get_data_freshness_info()
    if not freshness_info.get("has_data", False):
        render_empty_state(
            title="No Records Available",
            message="Please ingest GDELT data before searching: <code>python -m crisislens.ingestion.cli --latest</code>",
        )
        return

    filter_options = data_service.get_filter_options()
    countries_list = ["ALL"] + filter_options.get("countries", [])
    root_codes_list = ["ALL"] + filter_options.get("root_codes", [])

    # Filter Sidebar / Controls Expander
    with st.expander("🛠️ Filter & Search Criteria", expanded=True):
        # Row 1: Search text + Date Semantics
        r1_c1, r1_c2 = st.columns([2, 1])
        with r1_c1:
            search_query = st.text_input(
                "🔎 Text Search (Actor Name, Geography, or Source URL):",
                placeholder="e.g. President, United States, Police, Reuters...",
            )
        with r1_c2:
            date_mode = st.selectbox(
                "Date Filter Mode:",
                options=["Event Context Date (SQLDATE)", "Reporting Time (DATEADDED)"],
            )
            use_reporting = (date_mode == "Reporting Time (DATEADDED)")

        # Row 2: Date range + Country + CAMEO Root Code
        r2_c1, r2_c2, r2_c3 = st.columns(3)
        with r2_c1:
            if use_reporting:
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
                min_date = max_date - timedelta(days=365)

            date_filter = st.date_input(
                "Date Range:",
                value=(min_date, max_date),
                min_value=min_date,
                max_value=max_date,
            )

        with r2_c2:
            selected_country = st.selectbox(
                "Action Country (FIPS):",
                options=countries_list,
                index=0,
            )

        with r2_c3:
            selected_root_code = st.selectbox(
                "CAMEO Root Code:",
                options=root_codes_list,
                index=0,
            )

        # Row 3: QuadClass + Goldstein Scale + Min Mentions
        r3_c1, r3_c2, r3_c3 = st.columns([1.5, 1.2, 0.8])
        with r3_c1:
            quad_selection = st.multiselect(
                "Event QuadClass Categories:",
                options=[1, 2, 3, 4],
                format_func=lambda x: {
                    1: "1: Verbal Cooperation",
                    2: "2: Material Cooperation",
                    3: "3: Verbal Conflict",
                    4: "4: Material Conflict",
                }[x],
                default=[1, 2, 3, 4],
            )

        with r3_c2:
            goldstein_range = st.slider(
                "Goldstein Stability Scale:",
                min_value=-10.0,
                max_value=10.0,
                value=(-10.0, 10.0),
                step=0.5,
                help="-10: Maximum Conflict / Destabilizing | +10: Maximum Cooperation / Stabilizing",
            )

        with r3_c3:
            min_mentions = st.number_input(
                "Min Mentions:",
                min_value=0,
                value=0,
                step=1,
            )

    # Parse date filters
    date_start_str = None
    date_end_str = None
    if isinstance(date_filter, tuple) and len(date_filter) == 2:
        date_start_str = str(date_filter[0])
        date_end_str = str(date_filter[1])
    elif isinstance(date_filter, (list, tuple)) and len(date_filter) == 1:
        date_start_str = str(date_filter[0])
        date_end_str = str(date_filter[0])

    # Pagination controls state
    if "explorer_page" not in st.session_state:
        st.session_state.explorer_page = 1

    page_size_options = [25, 50, 100]
    col_pg_size, col_pg_nav, col_export = st.columns([1, 2, 1])

    with col_pg_size:
        page_size = st.selectbox("Rows per page:", options=page_size_options, index=1)

    # Execute Bounded Query
    events_page_df, total_count = data_service.query_explorer_events(
        date_start=date_start_str,
        date_end=date_end_str,
        country=selected_country if selected_country != "ALL" else None,
        quad_classes=quad_selection,
        event_root_code=selected_root_code if selected_root_code != "ALL" else None,
        search_text=search_query,
        goldstein_min=goldstein_range[0],
        goldstein_max=goldstein_range[1],
        min_mentions=int(min_mentions) if min_mentions > 0 else None,
        use_reporting_time=use_reporting,
        page=st.session_state.explorer_page,
        page_size=page_size,
    )

    total_pages = max(1, (total_count + page_size - 1) // page_size)
    if st.session_state.explorer_page > total_pages:
        st.session_state.explorer_page = 1

    with col_pg_nav:
        st.markdown(f"**Results:** {total_count:,} events found | Page {st.session_state.explorer_page} of {total_pages}")
        p_prev, p_next = st.columns(2)
        with p_prev:
            if st.button("⬅️ Previous", disabled=(st.session_state.explorer_page <= 1)):
                st.session_state.explorer_page = max(1, st.session_state.explorer_page - 1)
                st.rerun()
        with p_next:
            if st.button("Next ➡️", disabled=(st.session_state.explorer_page >= total_pages)):
                st.session_state.explorer_page = min(total_pages, st.session_state.explorer_page + 1)
                st.rerun()

    with col_export:
        if not events_page_df.empty:
            csv_bytes = events_page_df.to_csv(index=False).encode("utf-8-sig")
            st.download_button(
                label="⬇️ Download CSV (Page)",
                data=csv_bytes,
                file_name=f"crisislens_events_page_{st.session_state.explorer_page}.csv",
                mime="text/csv",
                use_container_width=True,
            )

    if events_page_df.empty:
        render_empty_state(
            title="No Matching Records",
            message="No events match your current filter and search criteria. Try broadening your date range or clearing text filters.",
        )
        return

    # Data Table View
    display_df = events_page_df.copy()
    display_df = display_df.rename(columns={
        "event_id": "Event ID",
        "event_date": "Event Date",
        "reporting_time": "Reported Time (UTC)",
        "actor1_name": "Actor 1",
        "actor2_name": "Actor 2",
        "event_code": "CAMEO",
        "quad_class": "Class",
        "goldstein_scale": "Goldstein",
        "num_mentions": "Mentions",
        "action_country": "Country",
        "action_geo_name": "Location",
        "source_url": "Source Link",
    })

    st.dataframe(
        display_df,
        use_container_width=True,
        hide_index=True,
        column_config={
            "Source Link": st.column_config.LinkColumn("Source Link", display_text="Source"),
            "Goldstein": st.column_config.NumberColumn("Goldstein", format="%.1f"),
            "Mentions": st.column_config.NumberColumn("Mentions", format="%d"),
        },
    )

    # Event Detail Inspector
    st.markdown("### 📋 Deep-Dive Record Inspector")
    st.markdown("<p style='color: #BDBDBD; font-size: 0.88rem;'>Select an Event ID from the current page to view its complete intelligence profile.</p>", unsafe_allow_html=True)

    event_ids = events_page_df["event_id"].tolist()
    selected_id = st.selectbox("Choose Event ID to inspect:", options=event_ids, index=0)

    if selected_id:
        detail_record = data_service.get_event_detail(int(selected_id))
        if detail_record:
            render_event_detail_card(detail_record)
        else:
            st.warning("Could not load details for selected event.")
