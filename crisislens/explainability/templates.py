"""
CrisisLens AI Explainability Engine.

Generates deterministic, human-readable narrative rationales and mathematical
formulations for detected event anomalies.
Enforces strict template-driven explainability without non-deterministic LLM hallucination risk.
"""

from typing import Dict, Any, Optional
import math


def generate_anomaly_explanation(
    record: Dict[str, Any],
    zscore_threshold: float = 2.5,
    iqr_multiplier: float = 1.5,
) -> Dict[str, Any]:
    """
    Generate a transparent, verifiable rationale for an anomaly record.

    Args:
        record: Dictionary or Series containing:
            - timestamp: formatted time string or Timestamp
            - observed_count: float or int
            - baseline_mean: float
            - baseline_std: float
            - z_score: float
            - upper_fence: float
            - severity: str ('NORMAL', 'MODERATE', 'HIGH', 'EXTREME', etc.)
            - is_anomaly: bool
        zscore_threshold: Configured Z-score cutoff (e.g. 2.5)
        iqr_multiplier: Configured Tukey multiplier (e.g. 1.5)

    Returns:
        Structured explanation dict with narrative, formula, and caveats.
    """
    ts = str(record.get("timestamp", "Unknown"))
    observed = float(record.get("observed_count", 0.0))
    mean = float(record.get("baseline_mean", 0.0)) if record.get("baseline_mean") is not None else float("nan")
    std = float(record.get("baseline_std", 0.0)) if record.get("baseline_std") is not None else float("nan")
    z = float(record.get("z_score", 0.0)) if record.get("z_score") is not None else float("nan")
    upper_fence = float(record.get("upper_fence", 0.0)) if record.get("upper_fence") is not None else float("nan")
    severity = str(record.get("severity", "NORMAL"))
    is_anomaly = bool(record.get("is_anomaly", False))

    if math.isnan(mean) or math.isnan(std):
        return {
            "timestamp": ts,
            "status": "INSUFFICIENT_HISTORY",
            "is_anomaly": False,
            "severity": "NORMAL",
            "narrative": "Insufficient historical intervals to compute a stationary baseline window.",
            "formula_latex": r"Z = \text{Undefined (insufficient history)}",
            "rule_triggered": "None",
            "deviation_pct": 0.0,
            "caveats": "Scoring begins once the minimum historical rolling window has elapsed.",
        }

    # Calculate deviation percentage
    if mean > 0:
        deviation_pct = round(((observed - mean) / mean) * 100.0, 1)
    else:
        deviation_pct = round(observed * 100.0, 1)

    # Determine which rule triggered
    z_triggered = not math.isnan(z) and z >= zscore_threshold
    iqr_triggered = not math.isnan(upper_fence) and observed > upper_fence

    if z_triggered and iqr_triggered:
        rule = "Dual Criteria (Rolling Z-Score & Tukey IQR Fence)"
    elif z_triggered:
        rule = f"Rolling Z-Score (Z >= {zscore_threshold})"
    elif iqr_triggered:
        rule = f"Tukey IQR Upper Fence (Observed > Q3 + {iqr_multiplier}*IQR)"
    else:
        rule = "Within Normal Baseline Bounds"

    # LaTeX formula string
    formula_latex = (
        rf"Z = \frac{{Y_t - \mu_t}}{{\sigma_t}} = "
        rf"\frac{{{observed:.0f} - {mean:.1f}}}{{{std:.1f}}} = {z:+.2f}"
    )

    if not is_anomaly:
        narrative = (
            f"At {ts}, event volume ({observed:.0f} events) remained within normal historical variance. "
            f"The rolling baseline average was {mean:.1f} (±{std:.1f} std dev), resulting in a "
            f"nominal Z-score of {z:+.2f}."
        )
    else:
        sign = "+" if deviation_pct >= 0 else ""
        if z_triggered and iqr_triggered:
            trigger_detail = (
                f"This surge exceeded baseline expectations on both statistical criteria: "
                f"a Z-score of {z:+.2f} (configured threshold: {zscore_threshold}) and surpassed "
                f"the Tukey upper fence ({upper_fence:.1f} events, Q3 + {iqr_multiplier}×IQR)."
            )
        elif z_triggered:
            trigger_detail = (
                f"This surge exceeded baseline expectations via the rolling Z-score with {z:+.2f} "
                f"standard deviations (configured threshold: {zscore_threshold}), while remaining "
                f"within the Tukey upper fence ({upper_fence:.1f} events)."
            )
        elif iqr_triggered:
            trigger_detail = (
                f"This surge exceeded baseline expectations via the non-parametric Tukey IQR upper "
                f"fence ({observed:.0f} > {upper_fence:.1f} events, Q3 + {iqr_multiplier}×IQR), while "
                f"the parametric Z-score remained at {z:+.2f} (configured threshold: {zscore_threshold})."
            )
        else:
            trigger_detail = (
                f"Observed volume ({observed:.0f} events) is flagged with Z-score {z:+.2f}."
            )

        narrative = (
            f"At {ts}, CrisisLens AI flagged a {severity} anomaly. "
            f"Observed event volume reached {observed:.0f} events, representing a {sign}{deviation_pct}% "
            f"deviation from the rolling historical mean ({mean:.1f} ± {std:.1f} std dev). "
            f"{trigger_detail}"
        )


    caveats = (
        "Methodology Caveat: This statistical anomaly reflects sudden spikes in public reporting volume. "
        "Elevated counts may indicate a genuine crisis escalation, or alternately an influx of syndicated wire "
        "reports, scraper batch releases, or duplicate news republishing. Cross-referencing source URLs and "
        "Actor taxonomy is recommended."
    )

    return {
        "timestamp": ts,
        "observed_value": observed,
        "baseline_mean": round(mean, 2),
        "baseline_std": round(std, 2),
        "z_score": round(z, 2),
        "upper_fence": round(upper_fence, 2),
        "deviation_pct": deviation_pct,
        "severity": severity,
        "is_anomaly": is_anomaly,
        "rule_triggered": rule,
        "narrative": narrative,
        "formula_latex": formula_latex,
        "caveats": caveats,
    }
