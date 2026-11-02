"""
CrisisLens AI Level 1 Statistical Anomaly Detector.

Implements a rolling z-score and Tukey's IQR fence anomaly detector.
Features:
- Strict zero-leakage guarantee: Point Y_t is strictly excluded from historical baseline H_t.
- Minimum history enforcement: Early window points are flagged as INSUFFICIENT_HISTORY.
- Zero-variance safeguard: Division-by-zero prevention when variance collapses to zero.
- Four-tier severity classification: NORMAL, MODERATE, HIGH, EXTREME.
"""

from typing import Dict, Any, Optional, Tuple, List
import numpy as np
import pandas as pd

from crisislens.explainability.templates import generate_anomaly_explanation


class StatisticalBaselineDetector:
    """
    Level 1 Statistical Baseline Anomaly Detector.

    Combines rolling parametric Z-score with non-parametric Tukey IQR upper fence.
    An interval is flagged as an anomaly if EITHER criterion triggers.
    """

    def __init__(
        self,
        window_size: int = 24,
        min_history: int = 12,
        zscore_threshold: float = 2.5,
        iqr_multiplier: float = 1.5,
    ):
        """
        Args:
            window_size: Lookback window size W (default: 24 intervals).
            min_history: Minimum lookback periods required before calculating stats (default: 12).
            zscore_threshold: Standard deviations above rolling mean to flag (default: 2.5).
            iqr_multiplier: Multiplier for Tukey fence Q3 + m * IQR (default: 1.5).
        """
        if window_size < 3:
            raise ValueError("window_size must be at least 3 intervals.")
        if min_history < 2 or min_history > window_size:
            raise ValueError(f"min_history must be between 2 and {window_size}.")
        if zscore_threshold <= 0:
            raise ValueError("zscore_threshold must be positive.")
        if iqr_multiplier <= 0:
            raise ValueError("iqr_multiplier must be positive.")

        self.window_size = window_size
        self.min_history = min_history
        self.zscore_threshold = float(zscore_threshold)
        self.iqr_multiplier = float(iqr_multiplier)

    def fit_detect(
        self,
        df: pd.DataFrame,
        time_col: str = "timestamp",
        count_col: str = "event_count",
    ) -> pd.DataFrame:
        """
        Execute statistical anomaly detection over a time-series.

        Args:
            df: Input DataFrame containing timestamp and count columns.
            time_col: Name of time column.
            count_col: Name of observed count column.

        Returns:
            DataFrame enriched with baseline statistics, z-score, fences, flags, and severities.
        """
        if df.empty:
            return pd.DataFrame(
                columns=[
                    time_col,
                    "observed_count",
                    "baseline_mean",
                    "baseline_std",
                    "z_score",
                    "q1",
                    "q3",
                    "iqr",
                    "upper_fence",
                    "is_zscore_anomaly",
                    "is_iqr_anomaly",
                    "is_anomaly",
                    "severity",
                    "status",
                ]
            )

        df_out = df.copy()
        df_out[time_col] = pd.to_datetime(df_out[time_col])
        df_out = df_out.sort_values(time_col).reset_index(drop=True)

        series = df_out[count_col].astype(float)

        # STRICT ZERO-LEAKAGE: Shift by 1 so window H_t strictly includes Y_{t-W} ... Y_{t-1}
        # Y_t and future observations are NEVER included in baseline statistics.
        shifted = series.shift(1)
        rolling = shifted.rolling(window=self.window_size, min_periods=self.min_history)

        rolling_mean = rolling.mean()
        rolling_std = rolling.std(ddof=1)
        rolling_q1 = rolling.quantile(0.25)
        rolling_q3 = rolling.quantile(0.75)
        rolling_iqr = rolling_q3 - rolling_q1

        # POISSON COUNT DISPERSION SAFEGUARD:
        # In event count processes, minimum theoretical variance is Poisson variance: Var >= Mean.
        # Clamping std to max(1.0, sqrt(mean)) prevents small fluctuations on high-count flat
        # baselines from falsely producing extreme Z-scores.
        rolling_mean_pos = np.maximum(rolling_mean.fillna(0.0), 0.0)
        poisson_std_floor = np.sqrt(rolling_mean_pos)
        effective_std_floor = np.maximum(1.0, poisson_std_floor)
        safe_std = np.maximum(rolling_std.fillna(1.0), effective_std_floor)

        # For IQR, normal/Poisson equivalence gives IQR ≈ 1.349 * sigma
        effective_iqr_floor = np.maximum(1.0, 1.349 * effective_std_floor)
        safe_iqr = np.maximum(rolling_iqr.fillna(1.0), effective_iqr_floor)

        # Compute Z-score and Tukey upper fence
        z_scores = (series - rolling_mean) / safe_std
        upper_fences = rolling_q3 + (self.iqr_multiplier * safe_iqr)

        # Flags
        z_anomalies = (z_scores >= self.zscore_threshold) & (~rolling_mean.isna())
        iqr_anomalies = (series > upper_fences) & (~rolling_mean.isna())
        is_anomalies = z_anomalies | iqr_anomalies

        # Status and Severity Classification
        statuses = np.where(rolling_mean.isna(), "INSUFFICIENT_HISTORY", "SCORED")

        severities = []
        for i in range(len(df_out)):
            if statuses[i] == "INSUFFICIENT_HISTORY":
                severities.append("NORMAL")
            elif not is_anomalies[i]:
                severities.append("NORMAL")
            else:
                z_val = float(z_scores.iloc[i]) if not pd.isna(z_scores.iloc[i]) else 0.0
                obs_val = float(series.iloc[i])
                q3_val = float(rolling_q3.iloc[i]) if not pd.isna(rolling_q3.iloc[i]) else 0.0
                iqr_val = float(safe_iqr.iloc[i]) if hasattr(safe_iqr, "iloc") else float(safe_iqr[i])

                # Severity relative to baseline thresholds:
                # Extreme: Z >= max(kz + 2.0, 4.5) OR Observed > Q3 + (m + 2.2)*IQR
                # High: Z >= max(kz + 0.8, 3.2) OR Observed > Q3 + (m + 1.0)*IQR
                # Moderate: Anomaly flagged at or above detection baseline
                thresh_z_high = max(self.zscore_threshold + 0.8, 3.2)
                thresh_z_extreme = max(self.zscore_threshold + 2.0, 4.5)
                thresh_iqr_high = q3_val + (self.iqr_multiplier + 1.0) * iqr_val
                thresh_iqr_extreme = q3_val + (self.iqr_multiplier + 2.2) * iqr_val

                if z_val >= thresh_z_extreme or obs_val > thresh_iqr_extreme:
                    severities.append("EXTREME")
                elif z_val >= thresh_z_high or obs_val > thresh_iqr_high:
                    severities.append("HIGH")
                else:
                    severities.append("MODERATE")


        df_out["observed_count"] = series
        df_out["baseline_mean"] = rolling_mean
        df_out["baseline_std"] = rolling_std
        df_out["z_score"] = z_scores
        df_out["q1"] = rolling_q1
        df_out["q3"] = rolling_q3
        df_out["iqr"] = rolling_iqr
        df_out["upper_fence"] = upper_fences
        df_out["is_zscore_anomaly"] = z_anomalies
        df_out["is_iqr_anomaly"] = iqr_anomalies
        df_out["is_anomaly"] = is_anomalies
        df_out["severity"] = severities
        df_out["status"] = statuses

        return df_out

    def explain_interval(
        self,
        df_scored: pd.DataFrame,
        target_timestamp: Any,
        time_col: str = "timestamp",
    ) -> Dict[str, Any]:
        """
        Generate an explainability dict for a specific interval.
        """
        match = df_scored[df_scored[time_col] == pd.to_datetime(target_timestamp)]
        if match.empty:
            return {
                "timestamp": str(target_timestamp),
                "status": "NOT_FOUND",
                "narrative": f"Timestamp {target_timestamp} not found in scored dataset.",
            }
        record = match.iloc[0].to_dict()
        return generate_anomaly_explanation(
            record,
            zscore_threshold=self.zscore_threshold,
            iqr_multiplier=self.iqr_multiplier,
        )
