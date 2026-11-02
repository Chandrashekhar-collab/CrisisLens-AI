"""
CrisisLens AI UI Presentation Components.

Provides styled HTML card wrappers, data freshness indicators,
and structured event detail inspector cards.
"""

from typing import Dict, Any, Optional
import streamlit as st
import pandas as pd



def render_metric_card(
    label: str,
    value: str | int | float,
    subtext: Optional[str] = None,
    accent_color: str = "#2196F3",
):
    """Render a modern, responsive metric card with accent border."""
    val_str = f"{value:,}" if isinstance(value, (int, float)) and not isinstance(value, bool) else str(value)
    subtext_html = f'<div style="font-size: 0.8rem; color: #9E9E9E; margin-top: 4px;">{subtext}</div>' if subtext else ""

    st.markdown(
        f"""
        <div style="
            background: rgba(255, 255, 255, 0.04);
            border-left: 4px solid {accent_color};
            border-radius: 6px;
            padding: 14px 18px;
            margin-bottom: 12px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.15);
        ">
            <div style="font-size: 0.82rem; text-transform: uppercase; letter-spacing: 0.05em; color: #BDBDBD; font-weight: 500;">
                {label}
            </div>
            <div style="font-size: 1.8rem; font-weight: 700; color: #FFFFFF; margin-top: 4px; line-height: 1.2;">
                {val_str}
            </div>
            {subtext_html}
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_freshness_banner(info: Dict[str, Any]):
    """Render a data freshness and pipeline status banner."""
    if not info.get("has_data", False):
        st.warning(
            "⚠️ **No Ingested Data Detected.** Run the ingestion CLI (`python -m crisislens.ingestion.cli --latest`) to populate the database.",
            icon="⚠️",
        )
        return

    latest_ingested = info.get("latest_ingested_at", "Unknown")
    total_events = info.get("total_events", 0)
    rep_min = info.get("min_reporting_time", "N/A")
    rep_max = info.get("max_reporting_time", "N/A")
    evt_min = info.get("min_event_date", "N/A")
    evt_max = info.get("max_event_date", "N/A")

    st.markdown(
        f"""
        <div style="
            background: rgba(33, 150, 243, 0.08);
            border: 1px solid rgba(33, 150, 243, 0.25);
            border-radius: 8px;
            padding: 12px 18px;
            margin-bottom: 20px;
            display: flex;
            flex-wrap: wrap;
            gap: 24px;
            align-items: center;
        ">
            <div>
                <span style="color: #64B5F6; font-weight: 600;">● Live Store</span>
                <span style="color: #E0E0E0; margin-left: 6px; font-weight: 600;">{total_events:,}</span> records
            </div>
            <div>
                <span style="color: #9E9E9E;">Latest Ingestion:</span>
                <span style="color: #E0E0E0; font-family: monospace; margin-left: 4px;">{latest_ingested[:19] if latest_ingested else 'N/A'}</span>
            </div>
            <div>
                <span style="color: #9E9E9E;">Reporting Activity:</span>
                <span style="color: #E0E0E0; font-family: monospace; margin-left: 4px;">{rep_min[:10]} to {rep_max[:10]}</span>
            </div>
            <div>
                <span style="color: #9E9E9E;">Event Occurrence Range:</span>
                <span style="color: #E0E0E0; font-family: monospace; margin-left: 4px;">{evt_min} to {evt_max}</span>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_empty_state(title: str, message: str):
    """Render an informative empty state card."""
    st.markdown(
        f"""
        <div style="
            background: rgba(255, 255, 255, 0.02);
            border: 1px dashed rgba(255, 255, 255, 0.2);
            border-radius: 8px;
            padding: 36px 20px;
            text-align: center;
            margin: 20px 0;
        ">
            <div style="font-size: 1.2rem; font-weight: 600; color: #E0E0E0;">{title}</div>
            <div style="font-size: 0.9rem; color: #9E9E9E; margin-top: 8px; max-width: 500px; margin-left: auto; margin-right: auto;">
                {message}
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_event_detail_card(event: Dict[str, Any]):
    """Render an expanded inspection card for a single event record."""
    event_id = event.get("event_id")
    event_date = event.get("event_date")
    rep_time = event.get("date_added")
    # Format date_added if present
    rep_time_str = str(rep_time)
    if len(rep_time_str) >= 14:
        rep_time_formatted = f"{rep_time_str[:4]}-{rep_time_str[4:6]}-{rep_time_str[6:8]} {rep_time_str[8:10]}:{rep_time_str[10:12]} UTC"
    else:
        rep_time_formatted = "N/A"

    quad_name = event.get("quad_class_name", "Unknown")
    cameo_code = event.get("event_code", "N/A")
    cameo_desc = event.get("cameo_description", "Unknown CAMEO event")
    cameo_root = event.get("cameo_root_name", "Unknown Root")

    act1_name = event.get("actor1_name") or "Unspecified Actor"
    act1_code = event.get("actor1_code") or "N/A"
    act1_country = event.get("actor1_country") or "N/A"

    act2_name = event.get("actor2_name") or "Unspecified Actor"
    act2_code = event.get("actor2_code") or "N/A"
    act2_country = event.get("actor2_country") or "N/A"

    geo_name = event.get("action_geo_name") or "Unspecified Location"
    country_name = event.get("country_full_name", event.get("action_country", "Unknown"))
    lat = event.get("action_lat")
    lon = event.get("action_lon")
    coords_str = f"{lat:.4f}, {lon:.4f}" if lat is not None and lon is not None and not (pd.isna(lat) or pd.isna(lon)) else "Coordinates Not Available"

    goldstein = event.get("goldstein_scale", 0.0)
    mentions = event.get("num_mentions", 0)
    sources = event.get("num_sources", 0)
    articles = event.get("num_articles", 0)
    tone = event.get("avg_tone", 0.0)
    source_url = event.get("source_url", "")

    st.markdown(
        f"""
        <div style="
            background: rgba(255, 255, 255, 0.05);
            border: 1px solid rgba(255, 255, 255, 0.15);
            border-radius: 8px;
            padding: 20px;
            margin-top: 16px;
        ">
            <div style="display: flex; justify-content: space-between; align-items: baseline; border-bottom: 1px solid rgba(255,255,255,0.1); padding-bottom: 10px;">
                <div>
                    <span style="font-size: 1.2rem; font-weight: 700; color: #FFFFFF;">Event Record #{event_id}</span>
                    <span style="background: rgba(33, 150, 243, 0.2); color: #64B5F6; padding: 2px 8px; border-radius: 4px; font-size: 0.8rem; margin-left: 10px;">
                        {quad_name}
                    </span>
                </div>
                <div style="font-size: 0.85rem; color: #BDBDBD;">
                    <b>Event Context:</b> {event_date} | <b>Reported:</b> {rep_time_formatted}
                </div>
            </div>

            <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 20px; margin-top: 15px;">
                <div>
                    <div style="color: #90CAF9; font-weight: 600; font-size: 0.9rem; margin-bottom: 6px;">👥 Involved Actors</div>
                    <div style="font-size: 0.85rem; color: #E0E0E0; line-height: 1.6;">
                        <b>Actor 1:</b> {act1_name} (Code: <code>{act1_code}</code>, Country: {act1_country})<br>
                        <b>Actor 2:</b> {act2_name} (Code: <code>{act2_code}</code>, Country: {act2_country})
                    </div>
                </div>

                <div>
                    <div style="color: #90CAF9; font-weight: 600; font-size: 0.9rem; margin-bottom: 6px;">📍 Action Geography</div>
                    <div style="font-size: 0.85rem; color: #E0E0E0; line-height: 1.6;">
                        <b>Location:</b> {geo_name}<br>
                        <b>Country:</b> {country_name} (FIPS: <code>{event.get('action_country', 'N/A')}</code>)<br>
                        <b>Coordinates:</b> {coords_str}
                    </div>
                </div>
            </div>

            <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 20px; margin-top: 15px;">
                <div>
                    <div style="color: #90CAF9; font-weight: 600; font-size: 0.9rem; margin-bottom: 6px;">🏷️ CAMEO Taxonomy</div>
                    <div style="font-size: 0.85rem; color: #E0E0E0; line-height: 1.6;">
                        <b>Code:</b> <code>{cameo_code}</code> — {cameo_desc}<br>
                        <b>Root Category:</b> {cameo_root}
                    </div>
                </div>

                <div>
                    <div style="color: #90CAF9; font-weight: 600; font-size: 0.9rem; margin-bottom: 6px;">📊 Stability & Media Metrics</div>
                    <div style="font-size: 0.85rem; color: #E0E0E0; line-height: 1.6;">
                        <b>Goldstein Scale:</b> {goldstein:.1f} (-10 max conflict to +10 max coop)<br>
                        <b>Average Tone:</b> {tone:.2f} | <b>Mentions:</b> {mentions:,} across {sources} sources ({articles} articles)
                    </div>
                </div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    if source_url and source_url.startswith("http"):
        st.markdown(
            f"""
            <div style="margin-top: 10px; font-size: 0.85rem;">
                🔗 <b>Primary Source Article:</b> <a href="{source_url}" target="_blank" rel="noopener noreferrer" style="color: #64B5F6; word-break: break-all;">{source_url}</a>
            </div>
            """,
            unsafe_allow_html=True,
        )
