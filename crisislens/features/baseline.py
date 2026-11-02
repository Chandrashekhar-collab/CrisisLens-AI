"""
CrisisLens AI Data Readiness Gate and Time-Series Aggregation.

Provides data-readiness verification to assess whether historical reporting
coverage is sufficient for continuous baseline modeling, and handles time-series
regularization and gap filling.
"""

from dataclasses import dataclass
from typing import Optional, Dict, Any
import pandas as pd
import numpy as np


@dataclass
class DataReadinessReport:
    """Detailed report on the historical reporting data readiness."""
    status: str  # "SUFFICIENT" or "INSUFFICIENT"
    n_intervals: int
    min_intervals_required: int
    min_timestamp: Optional[str]
    max_timestamp: Optional[str]
    span_hours: float
    missing_gaps_count: int
    reason: str
    can_score_live: bool

    def to_dict(self) -> Dict[str, Any]:
        return {
            "status": self.status,
            "n_intervals": self.n_intervals,
            "min_intervals_required": self.min_intervals_required,
            "min_timestamp": self.min_timestamp,
            "max_timestamp": self.max_timestamp,
            "span_hours": round(self.span_hours, 2),
            "missing_gaps_count": self.missing_gaps_count,
            "reason": self.reason,
            "can_score_live": self.can_score_live,
        }


class DataReadinessGate:
    """
    Evaluates whether a time-series of GDELT reporting timestamps has sufficient
    sample depth, temporal span, and continuity to support statistical baseline scoring.
    """

    def __init__(self, min_intervals: int = 28, min_span_hours: float = 7.0):
        """
        Args:
            min_intervals: Minimum distinct historical time buckets required (default 28).
            min_span_hours: Minimum hours between earliest and latest timestamp (default 7.0 hours).
        """
        self.min_intervals = min_intervals
        self.min_span_hours = min_span_hours

    def evaluate(self, df_series: pd.DataFrame, time_col: str = "timestamp") -> DataReadinessReport:
        """
        Inspect the reporting time-series and return a readiness report.

        Args:
            df_series: DataFrame with timestamps and event counts.
            time_col: Name of the timestamp column.
        """
        if df_series is None or df_series.empty:
            return DataReadinessReport(
                status="INSUFFICIENT",
                n_intervals=0,
                min_intervals_required=self.min_intervals,
                min_timestamp=None,
                max_timestamp=None,
                span_hours=0.0,
                missing_gaps_count=0,
                reason="No reporting data found in database. Ingestion must be run first.",
                can_score_live=False,
            )

        n_intervals = len(df_series)
        times = pd.to_datetime(df_series[time_col], errors="coerce").dropna().sort_values()

        if len(times) < 2:
            min_ts = str(times.iloc[0]) if len(times) == 1 else None
            return DataReadinessReport(
                status="INSUFFICIENT",
                n_intervals=n_intervals,
                min_intervals_required=self.min_intervals,
                min_timestamp=min_ts,
                max_timestamp=min_ts,
                span_hours=0.0,
                missing_gaps_count=0,
                reason=(
                    f"Only {n_intervals} reporting interval(s) available. A minimum of "
                    f"{self.min_intervals} continuous historical intervals is required for statistical baselines."
                ),
                can_score_live=False,
            )

        min_time = times.iloc[0]
        max_time = times.iloc[-1]
        span_hours = (max_time - min_time).total_seconds() / 3600.0

        # Estimate interval frequency and missing gaps
        diffs = times.diff().dropna()
        median_interval = diffs.median() if not diffs.empty else pd.Timedelta(minutes=15)
        
        # Gaps are jumps greater than 1.8x the median interval
        gap_threshold = median_interval * 1.8 if median_interval > pd.Timedelta(seconds=0) else pd.Timedelta(hours=1)
        missing_gaps = int((diffs > gap_threshold).sum())

        if n_intervals < self.min_intervals:
            reason = (
                f"Historical reporting window is insufficient: {n_intervals} intervals found "
                f"(minimum required: {self.min_intervals}). Span is {span_hours:.1f} hours. "
                "Baseline scoring is safely gated to prevent misleading false alarms."
            )
            return DataReadinessReport(
                status="INSUFFICIENT",
                n_intervals=n_intervals,
                min_intervals_required=self.min_intervals,
                min_timestamp=str(min_time),
                max_timestamp=str(max_time),
                span_hours=span_hours,
                missing_gaps_count=missing_gaps,
                reason=reason,
                can_score_live=False,
            )

        if span_hours < self.min_span_hours:
            reason = (
                f"Temporal span ({span_hours:.1f}h) is below the minimum required "
                f"({self.min_span_hours:.1f}h) for baseline stationarity."
            )
            return DataReadinessReport(
                status="INSUFFICIENT",
                n_intervals=n_intervals,
                min_intervals_required=self.min_intervals,
                min_timestamp=str(min_time),
                max_timestamp=str(max_time),
                span_hours=span_hours,
                missing_gaps_count=missing_gaps,
                reason=reason,
                can_score_live=False,
            )

        return DataReadinessReport(
            status="SUFFICIENT",
            n_intervals=n_intervals,
            min_intervals_required=self.min_intervals,
            min_timestamp=str(min_time),
            max_timestamp=str(max_time),
            span_hours=span_hours,
            missing_gaps_count=missing_gaps,
            reason=f"Data readiness verified: {n_intervals} intervals spanning {span_hours:.1f} hours ready for scoring.",
            can_score_live=True,
        )


def regularize_time_series(
    df: pd.DataFrame,
    time_col: str = "timestamp",
    val_col: str = "event_count",
    freq: str = "15min",
    fill_value: Any = 0,
) -> pd.DataFrame:
    """
    Ensure the time series is continuous and regularly spaced.
    
    Args:
        df: Input DataFrame with timestamps and event counts.
        time_col: Column name for timestamp.
        val_col: Column name for value.
        freq: Sampling interval frequency.
        fill_value: Value used to populate missing intervals. Default is 0.
                   When distinguishing missing unobserved data from observed zeros,
                   pass np.nan or inspect DataReadinessReport.missing_gaps_count.
    """
    if df.empty:
        return pd.DataFrame(columns=[time_col, val_col])

    df_work = df.copy()
    df_work[time_col] = pd.to_datetime(df_work[time_col])
    df_work = df_work.sort_values(time_col).drop_duplicates(subset=[time_col])
    
    full_idx = pd.date_range(start=df_work[time_col].min(), end=df_work[time_col].max(), freq=freq)
    df_work = df_work.set_index(time_col).reindex(full_idx, fill_value=fill_value).reset_index()
    df_work = df_work.rename(columns={"index": time_col})
    return df_work


