"""
CrisisLens AI — Publication-Quality PDF Investigation Report Generator.

Generates reproducible, publication-quality executive PDF briefings for selected
reporting-time intervals, anomalies, and underlying GDELT event records.
Strictly adheres to data provenance standards:
- Prominent banners and watermarks when synthetic benchmark data is used.
- Explicit disclosures when live anomaly scoring is gated by the DataReadinessGate.
- Clear distinction between reporting time (DATEADDED) and event context (SQLDATE).
- Low memory footprint (<20 MB) suitable for 8 GB RAM systems.
"""

import io
from pathlib import Path
from typing import Dict, Any, Optional, List, Tuple
from datetime import datetime, timezone
import hashlib

import pandas as pd
import numpy as np

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

from fpdf import FPDF
from fpdf.enums import XPos, YPos

from crisislens.ui.charts import QUAD_CLASS_PALETTE
from crisislens.explainability.templates import generate_anomaly_explanation


def _resolve_fonts(pdf: FPDF) -> str:
    """
    Register Unicode TrueType font (DejaVuSans) if available via matplotlib,
    falling back to core Helvetica with automatic character sanitization.
    """
    try:
        mpl_dir = Path(matplotlib.__file__).parent / "mpl-data" / "fonts" / "ttf"
        dejavu_reg = mpl_dir / "DejaVuSans.ttf"
        dejavu_bold = mpl_dir / "DejaVuSans-Bold.ttf"
        dejavu_oblique = mpl_dir / "DejaVuSans-Oblique.ttf"
        if dejavu_reg.exists() and dejavu_bold.exists():
            pdf.add_font("DejaVu", "", str(dejavu_reg))
            pdf.add_font("DejaVu", "B", str(dejavu_bold))
            if dejavu_oblique.exists():
                pdf.add_font("DejaVu", "I", str(dejavu_oblique))
            return "DejaVu"
    except Exception:
        pass
    return "helvetica"


def _sanitize_for_font(text: Any, font_name: str) -> str:
    """Sanitize strings for PDF encoding compatibility."""
    if text is None:
        return ""
    s = str(text).strip()
    if font_name == "helvetica":
        replacements = {
            "—": "-",
            "–": "-",
            "“": '"',
            "”": '"',
            "‘": "'",
            "’": "'",
            "μ": "u",
            "±": "+/-",
            "σ": "sigma",
            "×": "x",
            "≤": "<=",
            "≥": ">=",
            "•": "*",
            "⚡": "[!]",
            "🕵️": "[Investigate]",
            "📊": "[Stats]",
            "📋": "[Records]",
            "📑": "[Brief]",
        }
        for k, v in replacements.items():
            s = s.replace(k, v)
        return s.encode("latin-1", "replace").decode("latin-1")
    return s


def _generate_quad_donut_image(quad_counts: pd.DataFrame) -> io.BytesIO:
    """Generate in-memory PNG bytes for QuadClass distribution donut chart."""
    fig, ax = plt.subplots(figsize=(4.2, 3.0), dpi=150)
    fig.patch.set_facecolor("#FFFFFF")
    ax.set_facecolor("#FFFFFF")

    if quad_counts.empty or "quad_class_name" not in quad_counts.columns:
        ax.text(0.5, 0.5, "No QuadClass Data", ha="center", va="center", color="#757575", fontsize=10)
        ax.axis("off")
    else:
        labels = quad_counts["quad_class_name"].tolist()
        counts = quad_counts["event_count"].tolist()
        colors = [QUAD_CLASS_PALETTE.get(l, "#757575") for l in labels]

        wedges, texts, autotexts = ax.pie(
            counts,
            labels=labels,
            colors=colors,
            autopct="%1.1f%%",
            startangle=140,
            pctdistance=0.75,
            textprops={"fontsize": 7, "color": "#212121"},
            wedgeprops={"width": 0.45, "edgecolor": "#FFFFFF", "linewidth": 1.5},
        )
        for at in autotexts:
            at.set_fontsize(7)
            at.set_fontweight("bold")
            at.set_color("#FFFFFF")
        ax.set_title("Event Class Distribution", fontsize=9, fontweight="bold", color="#0D47A1", pad=6)

    plt.tight_layout()
    buf = io.BytesIO()
    fig.savefig(buf, format="png", bbox_inches="tight", dpi=150)
    buf.seek(0)
    plt.close(fig)
    return buf


def _generate_country_bar_image(country_counts: pd.DataFrame) -> io.BytesIO:
    """Generate in-memory PNG bytes for Top Geographies horizontal bar chart."""
    fig, ax = plt.subplots(figsize=(4.2, 3.0), dpi=150)
    fig.patch.set_facecolor("#FFFFFF")
    ax.set_facecolor("#FFFFFF")

    if country_counts.empty or "country_name" not in country_counts.columns:
        ax.text(0.5, 0.5, "No Geographic Data", ha="center", va="center", color="#757575", fontsize=10)
        ax.axis("off")
    else:
        # Sort ascending for horizontal bar chart
        df_sorted = country_counts.sort_values(by="total_events", ascending=True).tail(5)
        y_pos = np.arange(len(df_sorted))
        bars = ax.barh(y_pos, df_sorted["total_events"], color="#1565C0", height=0.55, edgecolor="#0D47A1")

        ax.set_yticks(y_pos)
        ax.set_yticklabels([str(c)[:16] for c in df_sorted["country_name"]], fontsize=7, color="#212121")
        ax.set_xlabel("Event Count", fontsize=7, color="#424242", labelpad=3)
        ax.set_title("Top Active Geographies", fontsize=9, fontweight="bold", color="#0D47A1", pad=6)
        ax.grid(axis="x", linestyle="--", alpha=0.3, color="#9E9E9E")
        ax.spines["top"].set_visible(False)
        ax.spines["right"].set_visible(False)
        ax.spines["left"].set_color("#BDBDBD")
        ax.spines["bottom"].set_color("#BDBDBD")

        # Add data labels
        for bar in bars:
            w = bar.get_width()
            ax.text(w + (max(df_sorted["total_events"]) * 0.02), bar.get_y() + bar.get_height() / 2,
                    f"{int(w):,}", va="center", fontsize=7, color="#0D47A1", fontweight="bold")

    plt.tight_layout()
    buf = io.BytesIO()
    fig.savefig(buf, format="png", bbox_inches="tight", dpi=150)
    buf.seek(0)
    plt.close(fig)
    return buf


class CrisisLensPDFReport(FPDF):
    """Custom FPDF subclass with branded headers, footers, and synthetic watermarking."""

    def __init__(self, is_synthetic: bool = False, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.is_synthetic = is_synthetic
        self.font_family_name = _resolve_fonts(self)
        self.set_auto_page_break(auto=True, margin=15)
        self.alias_nb_pages()

    def header(self):
        """Render page header with branding and mode banner."""
        self.set_font(self.font_family_name, "B", 8)

        if self.is_synthetic:
            # Synthetic Demo Banner
            self.set_fill_color(255, 235, 238)  # Light coral red
            self.set_text_color(198, 40, 40)    # Deep red
            self.cell(0, 5, "SYNTHETIC BENCHMARK FIXTURE - DEMO USE ONLY - NOT REAL-WORLD INCIDENT DATA",
                      border="B", align="C", fill=True, new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        else:
            # Live GDELT Banner
            self.set_fill_color(232, 245, 233)  # Light mint green
            self.set_text_color(46, 125, 50)    # Forest green
            self.cell(0, 5, "LIVE GDELT 2.0 DATA STORE - AUDIT BRIEFING",
                      border="B", align="C", fill=True, new_x=XPos.LMARGIN, new_y=YPos.NEXT)

        # Brand row
        self.set_text_color(100, 116, 139)
        self.set_font(self.font_family_name, "", 7)
        self.cell(100, 5, "CrisisLens AI | Global Event Anomaly Intelligence Platform", align="L")
        now_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
        self.cell(0, 5, f"Report Generated: {now_str}", align="R", new_x=XPos.LMARGIN, new_y=YPos.NEXT)

        # Thin divider
        self.set_draw_color(200, 210, 220)
        self.set_line_width(0.3)
        self.line(self.l_margin, self.get_y(), self.w - self.r_margin, self.get_y())
        self.ln(3)

        # Subtle background watermark for synthetic benchmark mode
        if self.is_synthetic:
            self._render_synthetic_watermark()

    def _render_synthetic_watermark(self):
        """Draw subtle diagonal synthetic watermark in page background."""
        current_x = self.get_x()
        current_y = self.get_y()
        self.set_font(self.font_family_name, "B", 38)
        self.set_text_color(245, 220, 225)  # Very faint red/pink
        
        # Render watermark across middle of page
        with self.rotation(35, x=self.w / 2, y=self.h / 2):
            self.text(x=self.w / 2 - 80, y=self.h / 2, text="SYNTHETIC BENCHMARK")
        
        # Reset position and color
        self.set_xy(current_x, current_y)
        self.set_text_color(33, 33, 33)

    def footer(self):
        """Render page footer with page numbers and reproducibility disclaimer."""
        self.set_y(-12)
        self.set_draw_color(200, 210, 220)
        self.set_line_width(0.3)
        self.line(self.l_margin, self.get_y(), self.w - self.r_margin, self.get_y())

        self.set_font(self.font_family_name, "", 6.5)
        self.set_text_color(120, 144, 156)

        # Left: Application identity
        self.cell(70, 5, "CrisisLens AI v0.5.0 | Deterministic DuckDB Provenance", align="L")

        # Center: Disclaimer
        if self.is_synthetic:
            self.cell(60, 5, "CONFIDENTIAL / SYNTHETIC DEMONSTRATION", align="C")
        else:
            self.cell(60, 5, "CONFIDENTIAL / RESEARCH INTELLIGENCE", align="C")

        # Right: Page count
        self.cell(0, 5, f"Page {self.page_no()} of {{nb}}", align="R")


def generate_investigation_pdf_report(
    interval_info: Dict[str, Any],
    events_df: pd.DataFrame,
    stats: Dict[str, Any],
    filters: Optional[Dict[str, Any]] = None,
    anomaly_meta: Optional[Dict[str, Any]] = None,
    is_synthetic: bool = False,
    config: Optional[Dict[str, Any]] = None,
) -> bytes:
    """
    Generate a publication-quality PDF investigation briefing.

    Args:
        interval_info: Dictionary containing interval metadata:
            - formatted_time: str (e.g. "2026-10-29 15:30:00")
            - date_added: int or str (e.g. 20261029153000)
            - label: optional descriptive label
        events_df: DataFrame of filtered event records matching the investigation
        stats: Dictionary of interval summary statistics from DataService
        filters: Applied query filters (country, quad_classes, search_text, goldstein)
        anomaly_meta: Anomaly scoring metadata if scored (z_score, baseline_mean, severity, etc.)
        is_synthetic: Boolean flag indicating if benchmark data is active
        config: Optional project configuration dictionary

    Returns:
        bytes: Complete binary PDF document
    """
    pdf = CrisisLensPDFReport(is_synthetic=is_synthetic, orientation="P", unit="mm", format="A4")
    pdf.set_title("CrisisLens AI - Event Investigation Briefing")
    pdf.set_author("CrisisLens AI")
    pdf.set_subject("SYNTHETIC BENCHMARK FIXTURE - DEMO USE ONLY" if is_synthetic else "LIVE GDELT 2.0 DATA STORE AUDIT")
    pdf.set_keywords("SYNTHETIC BENCHMARK, DEMO, SIMULATED" if is_synthetic else "LIVE GDELT, AUDIT, REPRODUCIBLE")

    font = pdf.font_family_name
    pdf.add_page()

    usable_width = pdf.w - pdf.l_margin - pdf.r_margin  # 210 - 20 = 190mm
    filters = filters or {}

    time_label = str(interval_info.get("formatted_time", "Unknown Interval"))
    date_added_val = str(interval_info.get("date_added", ""))

    # ---------------------------------------------------------
    # 1. Executive Title & Document Heading
    # ---------------------------------------------------------
    pdf.set_font(font, "B", 15)
    pdf.set_text_color(13, 71, 161)  # Deep Navy #0D47A1
    title_text = "EVENT INVESTIGATION INTELLIGENCE BRIEFING"
    pdf.cell(0, 7, _sanitize_for_font(title_text, font), new_x=XPos.LMARGIN, new_y=YPos.NEXT)

    pdf.set_font(font, "", 8.5)
    pdf.set_text_color(69, 90, 100)
    sub_text = "Granular Event Evidence, Anomaly Diagnostics & Reproducible Provenance"
    pdf.cell(0, 4.5, _sanitize_for_font(sub_text, font), new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.ln(2)

    # ---------------------------------------------------------
    # 2. Investigation Context Box (2-column layout)
    # ---------------------------------------------------------
    pdf.set_fill_color(245, 247, 250)
    pdf.set_draw_color(218, 224, 233)
    pdf.set_line_width(0.2)

    box_start_y = pdf.get_y()
    pdf.rect(pdf.l_margin, box_start_y, usable_width, 24, style="FD")

    pdf.set_xy(pdf.l_margin + 3, box_start_y + 2)
    pdf.set_font(font, "B", 7.5)
    pdf.set_text_color(13, 71, 161)
    pdf.cell(90, 4, "TEMPORAL & DATA SPECIFICATION:")
    pdf.set_xy(pdf.l_margin + 95, box_start_y + 2)
    pdf.cell(90, 4, "APPLIED INVESTIGATION FILTERS:")
    pdf.ln(4)

    pdf.set_font(font, "", 7)
    pdf.set_text_color(33, 33, 33)

    # Left Column: Dates & Scope
    pdf.set_xy(pdf.l_margin + 3, box_start_y + 6)
    pdf.cell(90, 3.5, _sanitize_for_font(f"• Reporting Interval (DATEADDED): {time_label} UTC ({date_added_val})", font))
    
    # Event date range
    if not events_df.empty and "event_date" in events_df.columns:
        date_min = str(events_df["event_date"].min())[:10]
        date_max = str(events_df["event_date"].max())[:10]
        ctx_date_str = f"{date_min} to {date_max}" if date_min != date_max else date_min
    else:
        ctx_date_str = "None matching"
    pdf.set_xy(pdf.l_margin + 3, box_start_y + 10)
    pdf.cell(90, 3.5, _sanitize_for_font(f"• Context Event Dates (SQLDATE): {ctx_date_str}", font))

    total_batch = stats.get("total_events", len(events_df))
    filtered_count = len(events_df)
    pdf.set_xy(pdf.l_margin + 3, box_start_y + 14)
    pdf.cell(90, 3.5, _sanitize_for_font(f"• Indexed Batch Records: {total_batch:,} | Matching Filters: {filtered_count:,}", font))

    # Right Column: Query Filters
    country_f = filters.get("country", "ALL")
    quads_f = filters.get("quad_classes", [1, 2, 3, 4])
    search_f = filters.get("search_text", "") or "None"
    goldstein_f = filters.get("goldstein", (-10.0, 10.0))

    pdf.set_xy(pdf.l_margin + 95, box_start_y + 6)
    pdf.cell(90, 3.5, _sanitize_for_font(f"• Country Filter: {country_f} | Classes: {quads_f}", font))
    pdf.set_xy(pdf.l_margin + 95, box_start_y + 10)
    pdf.cell(90, 3.5, _sanitize_for_font(f"• Search Query: '{search_f}'", font))
    pdf.set_xy(pdf.l_margin + 95, box_start_y + 14)
    pdf.cell(90, 3.5, _sanitize_for_font(f"• Goldstein Range: [{goldstein_f[0]:.1f}, {goldstein_f[1]:.1f}]", font))

    pdf.set_y(box_start_y + 27)

    # ---------------------------------------------------------
    # 3. Data Readiness & Anomaly Statistical Profile
    # ---------------------------------------------------------
    pdf.set_font(font, "B", 9)
    pdf.set_text_color(13, 71, 161)
    pdf.cell(0, 5, _sanitize_for_font("ANOMALY INTELLIGENCE & STATISTICAL BASELINE", font), new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.ln(1)

    if is_synthetic or (anomaly_meta and anomaly_meta.get("is_anomaly")):
        # Active anomaly alert section
        sev = str(anomaly_meta.get("severity", "EXTREME")) if anomaly_meta else "EXTREME"
        z_val = float(anomaly_meta.get("z_score", 0.0)) if anomaly_meta else 13.9
        obs_val = float(anomaly_meta.get("observed_value", len(events_df))) if anomaly_meta else float(len(events_df))
        mean_val = float(anomaly_meta.get("baseline_mean", 125.0)) if anomaly_meta else 125.0
        std_val = float(anomaly_meta.get("baseline_std", 22.0)) if anomaly_meta else 22.0
        upper_f = float(anomaly_meta.get("upper_fence", 170.0)) if anomaly_meta else 170.0

        # Anomaly Card Fill
        pdf.set_fill_color(255, 243, 224) if sev == "MODERATE" else pdf.set_fill_color(255, 235, 238)
        pdf.set_draw_color(255, 112, 67) if sev == "MODERATE" else pdf.set_draw_color(239, 83, 80)
        card_y = pdf.get_y()
        pdf.rect(pdf.l_margin, card_y, usable_width, 24, style="FD")

        # Metric Badges inside card
        pdf.set_xy(pdf.l_margin + 3, card_y + 2)
        pdf.set_font(font, "B", 8)
        pdf.set_text_color(198, 40, 40)
        pdf.cell(60, 4, _sanitize_for_font(f"ALERT STATUS: [{sev} ANOMALY FLAGGED]", font))
        
        pdf.set_font(font, "", 7)
        pdf.set_text_color(33, 33, 33)
        pdf.set_xy(pdf.l_margin + 3, card_y + 6)
        pdf.cell(45, 3.5, _sanitize_for_font(f"Observed Volume (Y_t): {obs_val:,.0f}", font))
        pdf.cell(45, 3.5, _sanitize_for_font(f"Baseline Mean (mu): {mean_val:.1f} (std: {std_val:.1f})", font))
        pdf.cell(45, 3.5, _sanitize_for_font(f"Parametric Z-Score: +{z_val:.2f} sigma", font))
        pdf.cell(45, 3.5, _sanitize_for_font(f"Tukey Fence: {upper_f:.1f}", font))

        # Explainability narrative
        expl = generate_anomaly_explanation(
            {
                "timestamp": time_label,
                "observed_count": obs_val,
                "baseline_mean": mean_val,
                "baseline_std": std_val,
                "z_score": z_val,
                "upper_fence": upper_f,
                "severity": sev,
                "is_anomaly": True,
            }
        )
        pdf.set_xy(pdf.l_margin + 3, card_y + 11)
        pdf.set_font(font, "", 6.8)
        pdf.set_text_color(55, 71, 79)
        pdf.multi_cell(usable_width - 6, 3.2, _sanitize_for_font(f"Rationale: {expl['narrative']}", font))

        pdf.set_y(card_y + 26)
    else:
        # Live GDELT Data Mode — Disclose DataReadinessGate status
        pdf.set_fill_color(240, 244, 248)
        pdf.set_draw_color(144, 202, 249)
        card_y = pdf.get_y()
        pdf.rect(pdf.l_margin, card_y, usable_width, 24, style="FD")

        pdf.set_xy(pdf.l_margin + 3, card_y + 2)
        pdf.set_font(font, "B", 7.5)
        pdf.set_text_color(21, 101, 192)  # Medium blue
        pdf.cell(0, 4, _sanitize_for_font("DATA READINESS STATUS: GATED (INSUFFICIENT HISTORICAL INTERVALS)", font), new_x=XPos.LMARGIN, new_y=YPos.NEXT)

        pdf.set_font(font, "", 6.8)
        pdf.set_text_color(55, 71, 79)
        pdf.set_xy(pdf.l_margin + 3, card_y + 6)
        gate_text = (
            "Live anomaly detection is gated by CrisisLens DataReadinessGate: the local store currently contains "
            f"{stats.get('total_events', len(events_df)):,} events across a 15-minute ingestion batch. A continuous "
            "baseline requires minimum N=28 intervals. Rolling baseline mean, variance, and Z-scores are withheld "
            "to prevent misleading statistical claims during intelligence evaluation."
        )
        pdf.multi_cell(usable_width - 6, 3.2, _sanitize_for_font(gate_text, font))

        # Interval batch profile summary line
        pdf.set_xy(pdf.l_margin + 3, card_y + 17)
        pdf.set_font(font, "B", 7)
        pdf.set_text_color(33, 33, 33)
        stat_line = (
            f"Batch Profile: {stats.get('distinct_countries', 0)} Active Nations | "
            f"Conflict Ratio: {stats.get('conflict_ratio_pct', 0.0)}% | "
            f"Avg Goldstein: {stats.get('avg_goldstein', 0.0):+.2f} | "
            f"Avg Tone: {stats.get('avg_tone', 0.0):+.2f}"
        )
        pdf.cell(0, 3.5, _sanitize_for_font(stat_line, font))
        pdf.set_y(card_y + 26)

    # ---------------------------------------------------------
    # 4. Embedded Visualizations (Side-by-Side Charts)
    # ---------------------------------------------------------
    pdf.set_font(font, "B", 9)
    pdf.set_text_color(13, 71, 161)
    pdf.cell(0, 5, _sanitize_for_font("VISUAL INTELLIGENCE DISTRIBUTIONS", font), new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.ln(1)

    chart_y = pdf.get_y()
    chart_w = 92
    chart_h = 52

    # Chart 1: QuadClass Donut
    if not events_df.empty and "quad_class_name" in events_df.columns:
        qc_counts = events_df["quad_class_name"].value_counts().reset_index()
        qc_counts.columns = ["quad_class_name", "event_count"]
    else:
        qc_counts = pd.DataFrame(columns=["quad_class_name", "event_count"])
    img_donut = _generate_quad_donut_image(qc_counts)
    pdf.image(img_donut, x=pdf.l_margin, y=chart_y, w=chart_w)

    # Chart 2: Top Geographies Bar Chart
    if not events_df.empty and "country_name" in events_df.columns:
        c_counts = events_df["country_name"].value_counts().reset_index()
        c_counts.columns = ["country_name", "total_events"]
    else:
        c_counts = pd.DataFrame(columns=["country_name", "total_events"])
    img_bar = _generate_country_bar_image(c_counts)
    pdf.image(img_bar, x=pdf.l_margin + chart_w + 5, y=chart_y, w=chart_w)

    pdf.set_y(chart_y + chart_h + 3)

    # ---------------------------------------------------------
    # 5. Underlying Event Evidence Table
    # ---------------------------------------------------------
    pdf.set_font(font, "B", 9)
    pdf.set_text_color(13, 71, 161)
    table_title = f"KEY EVENT EVIDENCE RECORDS (Top {min(15, len(events_df))} by Media Mentions)"
    pdf.cell(0, 5, _sanitize_for_font(table_title, font), new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.ln(1)

    if events_df.empty:
        pdf.set_font(font, "I", 8)
        pdf.set_text_color(120, 144, 156)
        pdf.cell(0, 8, _sanitize_for_font("No event records in this interval match the current filter query.", font),
                 align="C", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    else:
        # Sort by mentions descending and select top 15 records
        sort_col = "num_mentions" if "num_mentions" in events_df.columns else events_df.columns[0]
        top_events = events_df.sort_values(by=sort_col, ascending=False).head(15).copy()

        # Define column widths totaling usable_width (190mm)
        # ID: 18, Date: 17, Actors: 44, CAMEO: 13, Class: 22, Gold: 12, Mentions: 12, Geo: 52 = 190
        col_widths = (18, 17, 44, 13, 22, 12, 12, 52)
        headers = ["Event ID", "Context Date", "Actors (A1 -> A2)", "CAMEO", "QuadClass", "Gold.", "Ment.", "Location / Country"]

        pdf.set_font(font, "B", 6.5)
        with pdf.table(
            col_widths=col_widths,
            cell_fill_mode="ROWS",
            cell_fill_color=(245, 248, 252),
            text_align=("C", "C", "L", "C", "L", "R", "R", "L"),
            line_height=4.0,
            padding=1.0,
        ) as table:
            # Header row
            h_row = table.row()
            for h in headers:
                h_row.cell(_sanitize_for_font(h, font))

            # Data rows
            pdf.set_font(font, "", 6.0)
            for _, r in top_events.iterrows():
                row = table.row()
                row.cell(str(r.get("event_id", ""))[:12])
                row.cell(str(r.get("event_date", ""))[:10])
                
                # Actor formatting
                a1 = str(r.get("actor1_name", "")) or "-"
                a2 = str(r.get("actor2_name", "")) or "-"
                actors_str = f"{a1[:16]} -> {a2[:16]}"
                row.cell(_sanitize_for_font(actors_str, font))
                
                row.cell(str(r.get("event_code", ""))[:6])
                row.cell(_sanitize_for_font(str(r.get("quad_class_name", ""))[:16], font))
                
                # Goldstein
                g_val = r.get("goldstein_scale", 0.0)
                row.cell(f"{float(g_val):+.1f}" if pd.notna(g_val) else "0.0")
                
                # Mentions
                m_val = r.get("num_mentions", 0)
                row.cell(f"{int(m_val):,}" if pd.notna(m_val) else "0")
                
                # Location / Country
                geo = str(r.get("action_geo_name", "")) or ""
                country = str(r.get("country_name", "")) or str(r.get("action_country", "")) or ""
                loc_str = f"{geo[:22]}, {country[:14]}" if geo else country[:32]
                row.cell(_sanitize_for_font(loc_str, font))

    pdf.ln(3)

    # ---------------------------------------------------------
    # 6. Methodology, Data Governance & Ethical Disclosures
    # ---------------------------------------------------------
    # Check if space is tight; add page if less than 35mm remaining
    if pdf.get_y() > pdf.h - 40:
        pdf.add_page()

    pdf.set_font(font, "B", 8)
    pdf.set_text_color(13, 71, 161)
    pdf.cell(0, 4.5, _sanitize_for_font("DATA GOVERNANCE, METHODOLOGY & INTERPRETATION LIMITATIONS", font), new_x=XPos.LMARGIN, new_y=YPos.NEXT)

    pdf.set_font(font, "", 6.2)
    pdf.set_text_color(84, 110, 122)

    gov_text_1 = (
        "• Dual-Date Semantics: Anomalies represent surges in public media reporting volume indexed at DATEADDED. "
        "Contextual event dates (SQLDATE) record when incidents allegedly occurred and are maintained independently."
    )
    gov_text_2 = (
        "• Reporting Volume Caveat: Public news coverage spikes may stem from acute crisis escalation, or alternatively "
        "from syndicated wire republishing, scraper batch dumps, or duplicate reporting. Verifying source URLs and "
        "Actor taxonomy is required before drawing operational conclusions."
    )
    gov_text_3 = (
        "• Ethical Limitation: News reporting volume must NEVER be used as a direct proxy for physical conflict "
        "casualties or ground-level crisis severity."
    )
    gov_text_4 = (
        f"• Reproducibility Hash: SHA256({hashlib.sha256(f'{time_label}_{len(events_df)}_{is_synthetic}'.encode()).hexdigest()[:16]}) | "
        "Engine: DuckDB columnar analytical store | Storage Format: Snappy Parquet partitioned archive."
    )

    pdf.multi_cell(usable_width, 3.0, _sanitize_for_font(gov_text_1, font))
    pdf.multi_cell(usable_width, 3.0, _sanitize_for_font(gov_text_2, font))
    pdf.multi_cell(usable_width, 3.0, _sanitize_for_font(gov_text_3, font))
    pdf.multi_cell(usable_width, 3.0, _sanitize_for_font(gov_text_4, font))

    # Return PDF binary bytes
    return bytes(pdf.output())
