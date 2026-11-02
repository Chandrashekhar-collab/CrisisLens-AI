"""
CrisisLens AI — Event Investigation Drill-Down Screen.

Enables deep-dive event investigation for specific anomaly intervals or reporting-time
windows. Dissects underlying GDELT event records, actor networks, CAMEO taxonomies,
and source URLs with bounded parameterized queries and reproducible export briefs.
"""

from typing import Dict, Any, Optional, List
from datetime import datetime, date, timezone
import streamlit as st

import pandas as pd

from crisislens.ui.data_service import DataService
from crisislens.ui.components import (
    render_metric_card,
    render_empty_state,
    render_event_detail_card,
)
from crisislens.ui.charts import (
    create_quad_class_donut,
    create_country_bar_chart,
)
from crisislens.explainability.templates import generate_anomaly_explanation
from crisislens.reports.pdf_generator import generate_investigation_pdf_report


def render_investigation_page(data_service: DataService, config: Optional[Dict[str, Any]] = None):
    """
    Render the Event Investigation Drill-Down screen.
    """
    st.markdown(
        """
        <div style="margin-bottom: 20px;">
            <h1 style="margin: 0; font-size: 2.1rem; color: #FFFFFF;">🕵️ Event Investigation Drill-Down</h1>
            <p style="margin: 4px 0 0 0; font-size: 0.95rem; color: #90CAF9;">
                Granular evidence exploration, underlying GDELT event records, and reproducible intelligence briefing.
            </p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    # 1. Mode Selection & Available Intervals
    col_mode, col_int = st.columns([1, 2])

    with col_mode:
        data_mode = st.radio(
            "Investigation Data Mode:",
            options=["📡 Live GDELT Database Store", "🔬 Synthetic Benchmark Dataset"],
            index=0,
            help="Select live DuckDB store or deterministic synthetic benchmark fixture.",
        )
        is_synthetic = "Synthetic" in data_mode

    # 2. Interval Selection
    selected_date_added: Optional[int] = None
    selected_time_label: str = ""
    target_stats: Dict[str, Any] = {}

    if not is_synthetic:
        available_intervals = data_service.get_available_reporting_intervals(limit=50)
        if not available_intervals:
            render_empty_state(
                title="No Ingested Events in Store",
                message="No reporting intervals found in DuckDB. Run the ingestion pipeline to populate records.",
            )
            return

        interval_options = [
            f"{inv['formatted_time']} UTC — ({inv['event_count']:,} events)"
            for inv in available_intervals
        ]
        
        # Check if pre-selected via session state navigation
        pre_idx = 0
        if "investigate_target_time" in st.session_state:
            target_ts = st.session_state.investigate_target_time
            for idx, inv in enumerate(available_intervals):
                if target_ts in inv["formatted_time"]:
                    pre_idx = idx
                    break

        with col_int:
            chosen_option = st.selectbox(
                "Select Reporting Interval to Investigate:",
                options=interval_options,
                index=pre_idx,
                help="GDELT 15-minute indexing intervals available in local storage.",
            )
            sel_idx = interval_options.index(chosen_option)
            selected_date_added = int(available_intervals[sel_idx]["date_added"])
            selected_time_label = available_intervals[sel_idx]["formatted_time"]
    else:
        # Synthetic benchmark ground-truth scenarios
        synthetic_scenarios = [
            {"label": "2026-10-12 19:00 — [EXTREME] Natural Catastrophe Emergency Surge", "ts": "2026-10-12 19:00:00", "count": 430, "sev": "EXTREME", "z": 13.9},
            {"label": "2026-10-09 08:00 — [HIGH] Border Escalation & Military Confrontation", "ts": "2026-10-09 08:00:00", "count": 320, "sev": "HIGH", "z": 6.8},
            {"label": "2026-10-05 14:00 — [MODERATE] Protest & Civil Unrest Surge", "ts": "2026-10-05 14:00:00", "count": 245, "sev": "MODERATE", "z": 3.8},
            {"label": "2026-10-03 12:00 — [NORMAL] Routine Reporting Cycle Baseline", "ts": "2026-10-03 12:00:00", "count": 122, "sev": "NORMAL", "z": 0.2},
        ]
        with col_int:
            chosen_scen = st.selectbox(
                "Select Synthetic Benchmark Scenario to Investigate:",
                options=[s["label"] for s in synthetic_scenarios],
                index=0,
            )
            scen_meta = next(s for s in synthetic_scenarios if s["label"] == chosen_scen)
            selected_time_label = scen_meta["ts"][:16]

    # 3. Alert Evidence & Statistical Profile Card
    st.markdown("### 📊 Alert Evidence & Statistical Baseline")
    
    if not is_synthetic:
        # Retrieve interval breakdown stats from DuckDB
        interval_stats = data_service.get_investigation_interval_stats(
            interval_date_added=selected_date_added,
            use_reporting_time=True,
        )

        st.markdown(
            f"""
            <div style="background: rgba(30, 136, 229, 0.08); border-left: 4px solid #1E88E5; padding: 14px 18px; border-radius: 6px; margin-bottom: 16px;">
                <div style="display: flex; justify-content: space-between; align-items: baseline;">
                    <div>
                        <span style="font-size: 1.15rem; font-weight: 700; color: #FFFFFF;">
                            Reporting Interval: {selected_time_label} UTC
                        </span>
                        <span style="background: rgba(255, 152, 0, 0.2); color: #FFA726; padding: 2px 8px; border-radius: 4px; font-size: 0.8rem; margin-left: 10px;">
                            Live GDELT Batch
                        </span>
                    </div>
                    <div style="font-size: 0.85rem; color: #BDBDBD;">
                        <b>Total Indexed Events:</b> {interval_stats['total_events']:,}
                    </div>
                </div>
                <div style="font-size: 0.88rem; color: #E0E0E0; margin-top: 8px; line-height: 1.5;">
                    This batch contains <b>{interval_stats['total_events']:,}</b> event records across <b>{interval_stats['distinct_countries']}</b> active nations.
                    <b>{interval_stats['conflict_ratio_pct']}%</b> of records represent conflict categories (QuadClass 3 & 4),
                    with an average Goldstein stability scale of <b>{interval_stats['avg_goldstein']:+.2f}</b> and tone of <b>{interval_stats['avg_tone']:+.2f}</b>.
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )
    else:
        # Synthetic benchmark simulated card
        st.markdown(
            f"""
            <div style="background: rgba(255, 112, 67, 0.08); border-left: 4px solid #FF7043; padding: 14px 18px; border-radius: 6px; margin-bottom: 16px;">
                <div style="display: flex; justify-content: space-between; align-items: baseline;">
                    <div>
                        <span style="font-size: 1.15rem; font-weight: 700; color: #FFFFFF;">
                            Simulated Scenario: {chosen_scen}
                        </span>
                        <span style="background: rgba(239, 83, 80, 0.2); color: #EF5350; padding: 2px 8px; border-radius: 4px; font-size: 0.8rem; margin-left: 10px;">
                            {scen_meta['sev']} ANOMALY (+{scen_meta['z']}σ)
                        </span>
                    </div>
                    <div style="font-size: 0.85rem; color: #BDBDBD;">
                        <b>Simulated Volume:</b> {scen_meta['count']:,} events
                    </div>
                </div>
                <div style="font-size: 0.88rem; color: #E0E0E0; margin-top: 8px; line-height: 1.5;">
                    <b>Benchmark Ground Truth:</b> Deterministic synthetic surge modeled with diurnal variation and weekend baseline dips.
                    Demonstrates drill-down filtering, actor analysis, and export briefing during placement presentations.
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    # 4. Filter & Search Controls
    with st.expander("🛠️ Investigation Query Filters", expanded=True):
        f_col1, f_col2, f_col3 = st.columns([1.5, 1.2, 1.3])
        
        filter_options = data_service.get_filter_options()
        countries_list = ["ALL"] + filter_options.get("countries", [])
        
        with f_col1:
            inv_country = st.selectbox("Filter Country (FIPS):", options=countries_list, index=0)
        with f_col2:
            inv_quads = st.multiselect(
                "Event Categories:",
                options=[1, 2, 3, 4],
                format_func=lambda x: {
                    1: "1: Verbal Cooperation",
                    2: "2: Material Cooperation",
                    3: "3: Verbal Conflict",
                    4: "4: Material Conflict",
                }[x],
                default=[1, 2, 3, 4],
            )
        with f_col3:
            inv_search = st.text_input("Search Text (Actor / Location / URL):", placeholder="e.g. Police, Reuters, Army...")

        inv_goldstein = st.slider(
            "Goldstein Scale Range:",
            min_value=-10.0,
            max_value=10.0,
            value=(-10.0, 10.0),
            step=0.5,
        )

    # 5. Execute Bounded Investigation Query
    if not is_synthetic:
        page_size = 50
        inv_events_df, total_inv_count = data_service.query_investigation_events(
            interval_date_added=selected_date_added,
            country=inv_country if inv_country != "ALL" else None,
            quad_classes=inv_quads,
            search_text=inv_search,
            goldstein_min=inv_goldstein[0],
            goldstein_max=inv_goldstein[1],
            use_reporting_time=True,
            page=1,
            page_size=page_size,
        )
    else:
        # In synthetic mode, generate synthetic demonstration records matching the selected scenario
        total_inv_count = scen_meta["count"]
        # Generate simulated events matching the scenario
        records = []
        for i in range(min(50, total_inv_count)):
            records.append({
                "event_id": 90000000 + i,
                "event_date": selected_time_label[:10],
                "reporting_time": selected_time_label,
                "actor1_name": "SIMULATED CITIZENS / PROTESTERS" if "Protest" in chosen_scen else ("MILITARY FORCES" if "Border" in chosen_scen else "EMERGENCY RESPONDERS"),
                "actor2_name": "GOVERNMENT / POLICE" if "Protest" in chosen_scen else ("OPPOSING BORDER GUARDS" if "Border" in chosen_scen else "AFFECTED POPULATION"),
                "event_code": "140" if "Protest" in chosen_scen else ("190" if "Border" in chosen_scen else "020"),
                "quad_class": 3 if "Protest" in chosen_scen else (4 if "Border" in chosen_scen else 1),
                "goldstein_scale": -5.0 if "Protest" in chosen_scen else (-9.5 if "Border" in chosen_scen else 4.0),
                "num_mentions": 10 + (i % 5) * 4,
                "action_country": "US" if "Protest" in chosen_scen else "UK",
                "action_geo_name": "Demonstration Plaza" if "Protest" in chosen_scen else "Border Checkpoint",
                "source_url": f"https://example.com/demo-report/{i+1}",
                "date_added": 20261001000000,
                "country_name": "United States" if "Protest" in chosen_scen else "United Kingdom",
                "quad_class_name": "Verbal Conflict" if "Protest" in chosen_scen else ("Material Conflict" if "Border" in chosen_scen else "Verbal Cooperation"),
            })
        inv_events_df = pd.DataFrame(records)

    # 6. Results Breakdown & Evidence Analytics
    st.markdown("---")
    st.markdown(f"### 📋 Underlying Event Evidence ({total_inv_count:,} records found)")

    if inv_events_df.empty:
        render_empty_state(
            title="No Events Found",
            message="No event records in this interval match your current filter settings. Try adjusting the search query or category filters.",
        )
        return

    # Aggregate summaries for charts
    c_chart1, c_chart2 = st.columns([1, 1])
    with c_chart1:
        # QuadClass Donut
        quad_counts = inv_events_df["quad_class_name"].value_counts().reset_index()
        quad_counts.columns = ["quad_class_name", "event_count"]
        st.plotly_chart(create_quad_class_donut(quad_counts), use_container_width=True)

    with c_chart2:
        # Top Countries
        country_counts = inv_events_df["country_name"].value_counts().head(5).reset_index()
        country_counts.columns = ["country_name", "total_events"]
        st.plotly_chart(create_country_bar_chart(country_counts), use_container_width=True)

    # 7. Formatted Events Table
    display_table = inv_events_df.copy()
    display_table = display_table.rename(columns={
        "event_id": "Event ID",
        "event_date": "Event Date (Context)",
        "reporting_time": "Reported (UTC)",
        "actor1_name": "Actor 1",
        "actor2_name": "Actor 2",
        "event_code": "CAMEO",
        "quad_class": "Class",
        "goldstein_scale": "Goldstein",
        "num_mentions": "Mentions",
        "country_name": "Country",
        "action_geo_name": "Location",
        "source_url": "Source Article",
    })


    st.dataframe(
        display_table[[
            "Event ID", "Event Date (Context)", "Reported (UTC)",
            "Actor 1", "Actor 2", "CAMEO", "Class",
            "Goldstein", "Mentions", "Country", "Location", "Source Article"
        ]],
        use_container_width=True,
        hide_index=True,
        column_config={
            "Source Article": st.column_config.LinkColumn("Source Article", display_text="Source"),
            "Goldstein": st.column_config.NumberColumn("Goldstein", format="%.1f"),
            "Mentions": st.column_config.NumberColumn("Mentions", format="%d"),
        },
    )

    # 8. Single Record Deep-Dive Inspector
    st.markdown("### 🔍 Record Intelligence Profile")
    avail_ids = inv_events_df["event_id"].tolist()
    chosen_event_id = st.selectbox("Select Event ID to view full intelligence taxonomy:", options=avail_ids, index=0)
    
    if chosen_event_id:
        if not is_synthetic:
            rec_detail = data_service.get_event_detail(int(chosen_event_id))
            if rec_detail:
                render_event_detail_card(rec_detail)
        else:
            # Synthetic detail
            synth_row = inv_events_df[inv_events_df["event_id"] == chosen_event_id].iloc[0].to_dict()
            synth_row["cameo_description"] = "Simulated Event Action Code"
            synth_row["cameo_root_name"] = "Simulated CAMEO Root"
            synth_row["num_sources"] = 3
            synth_row["num_articles"] = 5
            synth_row["avg_tone"] = -2.5
            render_event_detail_card(synth_row)

    # 9. Reproducible Export Briefing Section
    st.markdown("---")
    st.markdown("### 📑 Reproducible Export & Investigation Summary")

    col_exp_csv, col_exp_brief, col_exp_pdf = st.columns(3)

    with col_exp_csv:
        csv_bytes = inv_events_df.to_csv(index=False).encode("utf-8-sig")
        st.download_button(
            label="⬇️ Download Events (CSV)",
            data=csv_bytes,
            file_name=f"crisislens_investigation_{selected_time_label.replace(':', '').replace(' ', '_')}.csv",
            mime="text/csv",
            use_container_width=True,
        )

    with col_exp_brief:
        brief_text = (
            f"# CrisisLens AI — Investigation Briefing\n\n"
            f"- **Target Interval:** {selected_time_label} UTC\n"
            f"- **Data Mode:** {'Synthetic Benchmark Fixture' if is_synthetic else 'Live GDELT 2.0 Ingested Store'}\n"
            f"- **Records Found:** {total_inv_count:,} events\n"
            f"- **Country Filter:** {inv_country}\n"
            f"- **Categories Filter:** {inv_quads}\n"
            f"- **Generated At:** {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')} UTC\n\n"
            f"## Analytical Findings\n"
            f"- Records analyzed: {len(inv_events_df)} samples\n"
            f"- Prominent Actors: {', '.join(inv_events_df['actor1_name'].dropna().unique()[:5])}\n"
            f"- Primary Geographies: {', '.join(inv_events_df['country_name'].dropna().unique()[:5])}\n\n"
            f"## Methodology & Data Governance\n"
            f"- Time-series anomalies represent surges in public reporting activity (GDELT DATEADDED).\n"
            f"- Contextual event dates (SQLDATE) are maintained independently for historical reference.\n"
            f"- All outputs derived deterministically via DuckDB columnar queries.\n"
        )
        st.download_button(
            label="📄 Download Brief (Markdown)",
            data=brief_text.encode("utf-8"),
            file_name=f"crisislens_brief_{selected_time_label.replace(':', '').replace(' ', '_')}.md",
            mime="text/markdown",
            use_container_width=True,
        )

    with col_exp_pdf:
        try:
            int_info = {
                "formatted_time": selected_time_label,
                "date_added": selected_date_added if selected_date_added else 0,
                "label": chosen_option if not is_synthetic else chosen_scen,
            }
            filter_dict = {
                "country": inv_country,
                "quad_classes": inv_quads,
                "search_text": inv_search,
                "goldstein": inv_goldstein,
            }
            anomaly_dict = None
            if is_synthetic:
                anomaly_dict = {
                    "severity": scen_meta.get("sev", "NORMAL"),
                    "z_score": scen_meta.get("z", 0.0),
                    "observed_value": scen_meta.get("count", len(inv_events_df)),
                    "baseline_mean": 125.0,
                    "baseline_std": 22.0,
                    "upper_fence": 170.0,
                    "is_anomaly": scen_meta.get("sev") != "NORMAL",
                }

            pdf_bytes = generate_investigation_pdf_report(
                interval_info=int_info,
                events_df=inv_events_df,
                stats=interval_stats if not is_synthetic else {
                    "total_events": scen_meta["count"],
                    "distinct_countries": inv_events_df["country_name"].nunique() if not inv_events_df.empty else 1,
                    "conflict_ratio_pct": 50.0,
                    "avg_goldstein": -5.0 if "Conflict" in chosen_scen else 0.0,
                    "avg_tone": -2.0,
                },
                filters=filter_dict,
                anomaly_meta=anomaly_dict,
                is_synthetic=is_synthetic,
                config=config,
            )
            st.download_button(
                label="📕 Download Report (PDF)",
                data=pdf_bytes,
                file_name=f"crisislens_report_{selected_time_label.replace(':', '').replace(' ', '_')}.pdf",
                mime="application/pdf",
                use_container_width=True,
            )
        except Exception as e:
            st.error(f"PDF generation error: {e}")
