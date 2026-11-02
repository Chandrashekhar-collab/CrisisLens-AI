"""
CrisisLens AI Plotly Chart Factory.

Provides consistent, responsive, publication-quality data visualizations
with unified color schemes aligned to CAMEO QuadClass taxonomies.
"""

from typing import Dict, Any, Optional
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go

# Authoritative QuadClass Palette
QUAD_CLASS_PALETTE = {
    "Verbal Cooperation": "#1E88E5",    # Vivid Blue
    "Material Cooperation": "#2E7D32",  # Forest Green
    "Verbal Conflict": "#FB8C00",       # Amber Orange
    "Material Conflict": "#D32F2F",     # Crimson Red
}

THEME_LAYOUT = {
    "paper_bgcolor": "rgba(0,0,0,0)",
    "plot_bgcolor": "rgba(0,0,0,0)",
    "font": {"family": "Inter, -apple-system, sans-serif", "color": "#E0E0E0"},
    "margin": {"l": 40, "r": 20, "t": 40, "b": 40},
}


def create_activity_trend_figure(
    df: pd.DataFrame,
    date_axis_title: str = "Date",
) -> go.Figure:
    """
    Generate an event activity time-series chart decomposed by CAMEO QuadClass.
    """
    if df.empty or "time_bucket" not in df.columns:
        fig = go.Figure()
        fig.update_layout(**THEME_LAYOUT)
        fig.add_annotation(
            text="No trend data available for selected filter",
            showarrow=False,
            font={"size": 14, "color": "#9E9E9E"},
        )
        return fig

    fig = go.Figure()

    # 1. Verbal Cooperation
    if "verbal_coop" in df.columns:
        fig.add_trace(go.Bar(
            x=df["time_bucket"],
            y=df["verbal_coop"],
            name="Verbal Cooperation",
            marker_color=QUAD_CLASS_PALETTE["Verbal Cooperation"],
            hovertemplate="%{x}<br>Verbal Coop: %{y:,}<extra></extra>",
        ))

    # 2. Material Cooperation
    if "material_coop" in df.columns:
        fig.add_trace(go.Bar(
            x=df["time_bucket"],
            y=df["material_coop"],
            name="Material Cooperation",
            marker_color=QUAD_CLASS_PALETTE["Material Cooperation"],
            hovertemplate="%{x}<br>Material Coop: %{y:,}<extra></extra>",
        ))

    # 3. Verbal Conflict
    if "verbal_conflict" in df.columns:
        fig.add_trace(go.Bar(
            x=df["time_bucket"],
            y=df["verbal_conflict"],
            name="Verbal Conflict",
            marker_color=QUAD_CLASS_PALETTE["Verbal Conflict"],
            hovertemplate="%{x}<br>Verbal Conflict: %{y:,}<extra></extra>",
        ))

    # 4. Material Conflict
    if "material_conflict" in df.columns:
        fig.add_trace(go.Bar(
            x=df["time_bucket"],
            y=df["material_conflict"],
            name="Material Conflict",
            marker_color=QUAD_CLASS_PALETTE["Material Conflict"],
            hovertemplate="%{x}<br>Material Conflict: %{y:,}<extra></extra>",
        ))

    # Total Trend Line
    if "total_events" in df.columns:
        fig.add_trace(go.Scatter(
            x=df["time_bucket"],
            y=df["total_events"],
            name="Total Activity",
            mode="lines+markers",
            line={"color": "#FFFFFF", "width": 2},
            marker={"size": 6, "color": "#FFFFFF"},
            hovertemplate="%{x}<br>Total Events: %{y:,}<extra></extra>",
        ))

    fig.update_layout(
        **THEME_LAYOUT,
        barmode="stack",
        title={"text": f"Event Activity Over Time ({date_axis_title})", "font": {"size": 16, "color": "#FFFFFF"}},
        xaxis={"title": date_axis_title, "gridcolor": "rgba(255,255,255,0.08)", "showgrid": True},
        yaxis={"title": "Event Count", "gridcolor": "rgba(255,255,255,0.08)", "showgrid": True},
        legend={"orientation": "h", "yanchor": "bottom", "y": 1.02, "xanchor": "right", "x": 1},
        hovermode="x unified",
        height=380,
    )
    return fig


def create_quad_class_donut(df: pd.DataFrame) -> go.Figure:
    """
    Generate a donut chart showing QuadClass proportion.
    """
    if df.empty or "quad_class_name" not in df.columns:
        fig = go.Figure()
        fig.update_layout(**THEME_LAYOUT)
        fig.add_annotation(text="No QuadClass data", showarrow=False, font={"color": "#9E9E9E"})
        return fig

    colors = [QUAD_CLASS_PALETTE.get(name, "#757575") for name in df["quad_class_name"]]

    fig = go.Figure(data=[go.Pie(
        labels=df["quad_class_name"],
        values=df["event_count"],
        hole=0.55,
        marker={"colors": colors},
        textinfo="percent+label",
        hoverinfo="label+value+percent",
        textposition="outside",
    )])

    fig.update_layout(
        **THEME_LAYOUT,
        title={"text": "Event Class Distribution", "font": {"size": 16, "color": "#FFFFFF"}},
        showlegend=False,
        height=340,
    )
    return fig


def create_country_bar_chart(df: pd.DataFrame) -> go.Figure:
    """
    Generate a horizontal bar chart displaying top active nations.
    """
    if df.empty or "country_name" not in df.columns:
        fig = go.Figure()
        fig.update_layout(**THEME_LAYOUT)
        fig.add_annotation(text="No geographic distribution data", showarrow=False, font={"color": "#9E9E9E"})
        return fig

    # Reverse order so highest volume appears at the top
    sorted_df = df.sort_values(by="total_events", ascending=True)

    fig = go.Figure()

    fig.add_trace(go.Bar(
        y=sorted_df["country_name"],
        x=sorted_df["total_events"],
        orientation="h",
        marker_color="#3F51B5",
        text=sorted_df["total_events"].apply(lambda v: f"{v:,}"),
        textposition="auto",
        hovertemplate="<b>%{y}</b><br>Total Events: %{x:,}<extra></extra>",
    ))

    fig.update_layout(
        **THEME_LAYOUT,
        title={"text": "Top Active Geographies", "font": {"size": 16, "color": "#FFFFFF"}},
        xaxis={"title": "Total Events", "gridcolor": "rgba(255,255,255,0.08)"},
        yaxis={"title": "", "autorange": True},
        height=340,
    )
    return fig


def create_anomaly_timeline_figure(
    df: pd.DataFrame,
    title: str = "Reporting Activity & Statistical Anomaly Thresholds",
) -> go.Figure:
    """
    Generate an interactive anomaly timeline chart showing observed counts,
    rolling baseline mean, upper threshold envelope, and flagged anomaly points.
    """
    if df.empty or "timestamp" not in df.columns:
        fig = go.Figure()
        fig.update_layout(**THEME_LAYOUT)
        fig.add_annotation(text="No time-series data available for anomaly scoring", showarrow=False, font={"color": "#9E9E9E"})
        return fig

    fig = go.Figure()

    # 1. Baseline Mean Line
    if "baseline_mean" in df.columns and not df["baseline_mean"].dropna().empty:
        fig.add_trace(go.Scatter(
            x=df["timestamp"],
            y=df["baseline_mean"],
            name="Baseline Mean (μ)",
            mode="lines",
            line={"color": "#64B5F6", "width": 1.5, "dash": "dash"},
            hovertemplate="%{x}<br>Baseline Mean: %{y:.1f}<extra></extra>",
        ))

    # 2. Upper Threshold Fence Band
    if "upper_fence" in df.columns and not df["upper_fence"].dropna().empty:
        fig.add_trace(go.Scatter(
            x=df["timestamp"],
            y=df["upper_fence"],
            name="Upper Threshold Fence",
            mode="lines",
            line={"color": "rgba(255, 152, 0, 0.4)", "width": 1, "dash": "dot"},
            fill="tonexty" if "baseline_mean" in df.columns else "none",
            fillcolor="rgba(33, 150, 243, 0.06)",
            hovertemplate="%{x}<br>Upper Fence: %{y:.1f}<extra></extra>",
        ))

    # 3. Observed Activity Line
    count_col = "observed_count" if "observed_count" in df.columns else "event_count"
    fig.add_trace(go.Scatter(
        x=df["timestamp"],
        y=df[count_col],
        name="Observed Activity",
        mode="lines+markers",
        line={"color": "#FFFFFF", "width": 1.8},
        marker={"size": 4, "color": "#FFFFFF"},
        hovertemplate="%{x}<br>Observed Events: %{y:,}<extra></extra>",
    ))

    # 4. Highlighted Anomaly Scatter Points by Severity
    if "is_anomaly" in df.columns:
        anomalies = df[df["is_anomaly"] == True]
        if not anomalies.empty:
            severity_colors = {
                "MODERATE": "#FFA726",  # Amber
                "HIGH": "#FF7043",      # Dark Orange
                "EXTREME": "#EF5350",   # Crimson
            }

            for sev in ["MODERATE", "HIGH", "EXTREME"]:
                sev_df = anomalies[anomalies["severity"] == sev]
                if not sev_df.empty:
                    fig.add_trace(go.Scatter(
                        x=sev_df["timestamp"],
                        y=sev_df[count_col],
                        name=f"Anomaly: {sev}",
                        mode="markers",
                        marker={
                            "size": 11 if sev == "EXTREME" else 9,
                            "color": severity_colors.get(sev, "#E91E63"),
                            "symbol": "diamond" if sev == "EXTREME" else "circle",
                            "line": {"width": 1.5, "color": "#FFFFFF"},
                        },
                        customdata=sev_df[["z_score", "baseline_mean"]],
                        hovertemplate=(
                            "<b>ANOMALY [%{fullData.name}]</b><br>"
                            "Time: %{x}<br>"
                            "Observed: %{y:,}<br>"
                            "Baseline Mean: %{customdata[1]:.1f}<br>"
                            "Z-Score: +%{customdata[0]:.2f}σ<extra></extra>"
                        ),
                    ))

    fig.update_layout(
        **THEME_LAYOUT,
        title={"text": title, "font": {"size": 16, "color": "#FFFFFF"}},
        xaxis={"title": "Timestamp", "gridcolor": "rgba(255,255,255,0.08)", "showgrid": True},
        yaxis={"title": "Event Count", "gridcolor": "rgba(255,255,255,0.08)", "showgrid": True},
        legend={"orientation": "h", "yanchor": "bottom", "y": 1.02, "xanchor": "right", "x": 1},
        hovermode="x unified",
        height=420,
    )
    return fig


def create_anomaly_severity_donut(df: pd.DataFrame) -> go.Figure:
    """
    Generate a donut chart showing the distribution of anomaly severities.
    """
    if df.empty or "severity" not in df.columns:
        fig = go.Figure()
        fig.update_layout(**THEME_LAYOUT)
        fig.add_annotation(text="No severity data", showarrow=False, font={"color": "#9E9E9E"})
        return fig

    sev_counts = df["severity"].value_counts().reset_index()
    sev_counts.columns = ["severity", "count"]

    palette = {
        "NORMAL": "#546E7A",
        "MODERATE": "#FFA726",
        "HIGH": "#FF7043",
        "EXTREME": "#EF5350",
    }
    colors = [palette.get(s, "#9E9E9E") for s in sev_counts["severity"]]

    fig = go.Figure(data=[go.Pie(
        labels=sev_counts["severity"],
        values=sev_counts["count"],
        hole=0.6,
        marker={"colors": colors},
        textinfo="label+value",
        hoverinfo="label+value+percent",
        textposition="outside",
    )])

    fig.update_layout(
        **THEME_LAYOUT,
        title={"text": "Severity Classification", "font": {"size": 16, "color": "#FFFFFF"}},
        showlegend=False,
        height=320,
    )
    return fig

