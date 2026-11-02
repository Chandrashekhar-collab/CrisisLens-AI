"""
CrisisLens AI Anomaly Intelligence Page.

Provides interactive Level 1 statistical anomaly detection (rolling Z-score + Tukey IQR fence),
data-readiness gating, and deterministic explainability inspection.
Enables switching between gated live store analysis and deterministic synthetic benchmark fixtures.
"""

from typing import Dict, Any, Optional
import streamlit as st
import pandas as pd

from crisislens.ui.data_service import DataService
from crisislens.ui.charts import create_anomaly_timeline_figure, create_anomaly_severity_donut
from crisislens.explainability.templates import generate_anomaly_explanation


def render_anomaly_page(data_service: DataService, config: Optional[Dict[str, Any]] = None):
    """
    Render the interactive Anomaly Intelligence screen.
    """
    cfg_models = (config or {}).get("models", {})
    default_z = float(cfg_models.get("zscore_threshold", 2.5))
    default_iqr = float(cfg_models.get("iqr_multiplier", 1.5))

    st.markdown(
        """
        <div style="margin-bottom: 20px;">
            <h1 style="margin: 0; font-size: 2.1rem; color: #FFFFFF;">⚡ Anomaly Intelligence</h1>
            <p style="margin: 4px 0 0 0; font-size: 0.95rem; color: #90CAF9;">
                Level 1 Statistical Baseline Engine: Dual-criterion rolling Z-score & non-parametric Tukey IQR upper fence.
            </p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    # 1. Data-Readiness Pre-Flight Check on Live Database
    live_readiness = data_service.check_data_readiness(min_intervals=28)

    # 2. Source Selector & Readiness Gate Banner
    st.markdown("### 🎛️ Analysis Configuration & Data Source")
    
    col_src, col_gate_info = st.columns([1, 2])
    with col_src:
        data_source = st.radio(
            "Select Evaluation Mode:",
            options=[
                "🔬 Synthetic Benchmark (Demo Mode)",
                "📡 Live GDELT Database Store",
            ],
            index=0 if not live_readiness.can_score_live else 1,
            help="Choose between verified synthetic benchmark fixture or live DuckDB store.",
        )
        is_synthetic = "Synthetic" in data_source

    with col_gate_info:
        if not live_readiness.can_score_live:
            st.warning(
                f"⚠️ **Live Store Gated (Insufficient History):** DuckDB currently holds "
                f"**{live_readiness.n_intervals}** reporting interval(s) spanning "
                f"**{live_readiness.span_hours:.1f}** hours. "
                f"Minimum required is **{live_readiness.min_intervals_required}** intervals "
                f"for statistical baseline stability. Live baseline scoring is safely locked to prevent false alarms."
            )
        else:
            st.success(
                f"✅ **Live Store Ready:** {live_readiness.n_intervals} reporting intervals "
                f"spanning {live_readiness.span_hours:.1f} hours available for scoring."
            )

    if is_synthetic:
        st.info(
            "ℹ️ **Placement Demonstration Fixture Active:** Demonstrating the anomaly engine on a deterministic "
            "14-day global reporting series (336 hourly intervals, seed=42). Features realistic diurnal variations, "
            "weekend activity dips, and 3 injected crisis spikes (Day 5 Protest Surge, Day 9 Border Conflict, "
            "Day 12 Natural Catastrophe).",
            icon="🧪",
        )

    # 3. Interactive Knobs Expander
    with st.expander("⚙️ Tunable Detection Hyperparameters (Central Settings)", expanded=False):
        c1, c2, c3, c4 = st.columns(4)
        with c1:
            window_size = st.slider(
                "Rolling Window (W)",
                min_value=6,
                max_value=72,
                value=24,
                step=2,
                help="Lookback intervals H_t = {Y_{t-W} ... Y_{t-1}} strictly preceding observation.",
            )
        with c2:
            min_history = st.slider(
                "Min History (W_min)",
                min_value=4,
                max_value=min(window_size, 24),
                value=min(12, window_size),
                step=2,
                help="Minimum historical intervals required before computing baseline.",
            )
        with c3:
            zscore_thresh = st.slider(
                "Z-Score Threshold (k_z)",
                min_value=1.5,
                max_value=5.0,
                value=default_z,
                step=0.1,
                help="Standard deviations above rolling mean required to flag an anomaly.",
            )
        with c4:
            iqr_mult = st.slider(
                "Tukey IQR Multiplier (m)",
                min_value=1.0,
                max_value=3.0,
                value=default_iqr,
                step=0.1,
                help="Multiplier for Tukey fence: Q3 + m * IQR.",
            )

    # 4. Execute Detection
    source_key = "benchmark" if is_synthetic else "live"
    df_scored, readiness = data_service.detect_anomalies(
        source=source_key,
        window_size=window_size,
        min_history=min_history,
        zscore_threshold=zscore_thresh,
        iqr_multiplier=iqr_mult,
    )

    if not is_synthetic and not readiness.can_score_live:
        st.error(
            f"🚫 Scoring Halted on Live Store: {readiness.reason}\n\n"
            "Please switch to **🔬 Synthetic Benchmark (Demo Mode)** above to inspect the algorithm and explainability engine."
        )
        return

    if df_scored.empty:
        st.info("No time-series data available for the selected configuration.")
        return

    # 5. Top Metric KPI Row
    st.markdown("---")
    kpi_col1, kpi_col2, kpi_col3, kpi_col4 = st.columns(4)

    total_intervals = len(df_scored)
    valid_means = df_scored["baseline_mean"].dropna()
    avg_baseline = round(valid_means.mean(), 1) if not valid_means.empty else 0.0
    anomalies_count = int(df_scored["is_anomaly"].sum()) if "is_anomaly" in df_scored.columns else 0
    valid_zs = df_scored["z_score"].dropna()
    peak_z = round(valid_zs.max(), 2) if not valid_zs.empty else 0.0

    with kpi_col1:
        st.metric(
            label="Total Intervals Analyzed",
            value=f"{total_intervals:,}",
            delta=f"Window: {window_size} intervals",
            delta_color="off",
        )
    with kpi_col2:
        st.metric(
            label="Historical Baseline Mean (μ)",
            value=f"{avg_baseline:,.1f}",
            delta="Rolling window average",
            delta_color="off",
        )
    with kpi_col3:
        st.metric(
            label="Flagged Anomalies",
            value=f"{anomalies_count}",
            delta=f"{round(anomalies_count / max(total_intervals, 1) * 100, 1)}% of series",
            delta_color="inverse",
        )
    with kpi_col4:
        st.metric(
            label="Peak Anomaly Z-Score",
            value=f"+{peak_z}σ",
            delta=f"Cutoff: {zscore_thresh}σ",
            delta_color="normal" if peak_z >= zscore_thresh else "off",
        )

    # 6. Charts Section
    st.markdown("---")
    chart_col1, chart_col2 = st.columns([3, 1])

    with chart_col1:
        timeline_fig = create_anomaly_timeline_figure(
            df_scored,
            title=(
                "Synthetic Benchmark Activity & Anomaly Thresholds"
                if is_synthetic
                else "Live GDELT Activity & Statistical Anomaly Thresholds"
            ),
        )
        st.plotly_chart(timeline_fig, use_container_width=True)

    with chart_col2:
        donut_fig = create_anomaly_severity_donut(df_scored)
        st.plotly_chart(donut_fig, use_container_width=True)

    # 7. Flagged Anomalies Table
    st.markdown("### 📋 Flagged Anomaly Events")
    
    anomalies_df = df_scored[df_scored["is_anomaly"] == True].copy()
    if anomalies_df.empty:
        st.success("No anomalies detected at the current threshold settings.")
    else:
        # Format display table
        display_df = pd.DataFrame({
            "Timestamp": anomalies_df["timestamp"].dt.strftime("%Y-%m-%d %H:%M"),
            "Observed Events": anomalies_df["observed_count"].astype(int),
            "Expected Baseline (μ)": anomalies_df["baseline_mean"].round(1),
            "Std Dev (σ)": anomalies_df["baseline_std"].round(1),
            "Z-Score": anomalies_df["z_score"].apply(lambda v: f"+{v:.2f}σ"),
            "Upper Fence": anomalies_df["upper_fence"].round(1),
            "Severity": anomalies_df["severity"],
            "Ground Truth (Demo)": (
                anomalies_df["ground_truth_category"]
                if "ground_truth_category" in anomalies_df.columns
                else "Real Observation"
            ),
        })

        st.dataframe(
            display_df,
            use_container_width=True,
            hide_index=True,
        )

    # 8. Detailed Explainability Inspector
    st.markdown("---")
    st.markdown("### 🕵️ Deterministic Explainability & Math Inspector")

    if not anomalies_df.empty:
        ts_options = anomalies_df["timestamp"].dt.strftime("%Y-%m-%d %H:%M").tolist()
        selected_ts_str = st.selectbox(
            "Select an anomaly interval to inspect mathematical proof and rationale:",
            options=ts_options,
            index=0,
        )

        # Retrieve selected record
        sel_row = anomalies_df[anomalies_df["timestamp"].dt.strftime("%Y-%m-%d %H:%M") == selected_ts_str].iloc[0]
        explanation = generate_anomaly_explanation(
            sel_row.to_dict(),
            zscore_threshold=zscore_thresh,
            iqr_multiplier=iqr_mult,
        )

        st.markdown(
            f"""
            <div style="background: rgba(30, 136, 229, 0.08); border-left: 4px solid #1E88E5; padding: 16px; border-radius: 4px; margin-bottom: 16px;">
                <h4 style="margin: 0 0 8px 0; color: #90CAF9;">Rationale Narrative</h4>
                <p style="margin: 0; font-size: 0.95rem; line-height: 1.5; color: #E0E0E0;">
                    {explanation['narrative']}
                </p>
            </div>
            """,
            unsafe_allow_html=True,
        )

        m1, m2 = st.columns(2)
        with m1:
            st.markdown("##### 📐 Mathematical Formulation")
            st.latex(explanation["formula_latex"])
            st.caption(
                f"**Trigger Rule:** {explanation['rule_triggered']}<br>"
                f"**Deviation:** {explanation['deviation_pct']:+}% over historical rolling mean.",
                unsafe_allow_html=True,
            )

        with m2:
            st.markdown("##### ⚠️ Statistical & Operational Caveats")
            st.caption(explanation["caveats"])
            if is_synthetic and "ground_truth_category" in sel_row:
                st.caption(f"**Injected Benchmark Scenario:** {sel_row['ground_truth_category']}")

        # Drill-down link to investigation page
        st.markdown("<div style='margin-top: 10px;'></div>", unsafe_allow_html=True)
        if st.button(f"🔬 Drill Down into Event Investigation ({selected_ts_str})", key="btn_drilldown"):
            st.session_state.investigate_target_time = selected_ts_str
            st.success(
                f"Interval **{selected_ts_str}** selected! Navigate to **🕵️ Event Investigation** in the sidebar to examine underlying GDELT records.",
                icon="🕵️",
            )
    else:
        st.info("Select or adjust thresholds above to view detailed mathematical explainability for flagged intervals.")

