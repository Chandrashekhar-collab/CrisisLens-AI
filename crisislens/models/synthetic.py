"""
CrisisLens AI Synthetic Benchmark Fixture Generator.

Produces a deterministic, realistic synthetic global event time-series benchmark
with known injected anomalies.
Used for verification, testing, and placement demonstrations when live database
reporting history is insufficient to satisfy the statistical baseline requirements.

Every generated record is explicitly labeled as synthetic to prevent any
misrepresentation of synthetic spikes as real live crisis events.
"""

from typing import Optional
import numpy as np
import pandas as pd


def generate_synthetic_benchmark_fixture(
    days: int = 14,
    interval_minutes: int = 60,
    seed: int = 42,
    base_mean: float = 120.0,
    start_date: str = "2026-10-01 00:00:00",
) -> pd.DataFrame:
    """
    Generate a deterministic synthetic reporting time series with 3 injected spikes.

    Args:
        days: Duration in days (default 14 days = 336 hourly intervals).
        interval_minutes: Bucket size in minutes (default 60 = 1 hour).
        seed: Random seed for deterministic reproducibility.
        base_mean: Typical baseline event volume.
        start_date: Time-series start anchor.

    Returns:
        DataFrame with columns:
        - timestamp: pd.Timestamp
        - event_count: int
        - is_synthetic: bool (always True)
        - dataset_label: str
        - ground_truth_label: str ('BASELINE' or 'INJECTED_SPIKE')
        - ground_truth_category: str (simulated event description)
    """
    rng = np.random.default_rng(seed)
    
    total_minutes = days * 24 * 60
    n_points = total_minutes // interval_minutes
    timestamps = pd.date_range(start=start_date, periods=n_points, freq=f"{interval_minutes}min")

    counts = np.zeros(n_points, dtype=float)
    gt_labels = ["BASELINE"] * n_points
    gt_categories = ["Normal reporting cycle"] * n_points

    for i, ts in enumerate(timestamps):
        hour = ts.hour
        day_of_week = ts.day_of_week  # 5=Sat, 6=Sun

        # Diurnal pattern: peak in afternoon (14:00 UTC), trough at night (03:00 UTC)
        diurnal_factor = 28.0 * np.sin((hour - 8.0) * np.pi / 12.0)

        # Weekend reduction (15% drop on Saturday/Sunday)
        weekend_factor = 0.85 if day_of_week in [5, 6] else 1.0

        # Base expectation with Gaussian stochastic variation
        expected = (base_mean + diurnal_factor) * weekend_factor
        noise = rng.normal(loc=0.0, scale=9.5)
        count = max(20.0, expected + noise)
        counts[i] = count

    # Inject 3 controlled ground-truth anomaly events:
    # 1. Moderate Spike: Day 5 at 14:00 (Index: 4 * 24 + 14 = 110)
    idx_moderate = min(110, n_points - 1)
    counts[idx_moderate] = counts[idx_moderate] + 115.0  # Approx ~245 events
    gt_labels[idx_moderate] = "INJECTED_SPIKE"
    gt_categories[idx_moderate] = "Protest & Civil Unrest Surge (Simulated)"

    # 2. High Spike: Day 9 at 08:00 (Index: 8 * 24 + 8 = 200)
    idx_high = min(200, n_points - 1)
    counts[idx_high] = counts[idx_high] + 195.0  # Approx ~320 events
    gt_labels[idx_high] = "INJECTED_SPIKE"
    gt_categories[idx_high] = "Border Escalation & Military Standoff (Simulated)"

    # 3. Extreme Spike: Day 12 at 19:00 (Index: 11 * 24 + 19 = 283)
    idx_extreme = min(283, n_points - 1)
    counts[idx_extreme] = counts[idx_extreme] + 310.0  # Approx ~430 events
    gt_labels[idx_extreme] = "INJECTED_SPIKE"
    gt_categories[idx_extreme] = "Natural Catastrophe & Emergency Response (Simulated)"

    df = pd.DataFrame({
        "timestamp": timestamps,
        "event_count": np.round(counts).astype(int),
        "is_synthetic": True,
        "dataset_label": "BENCHMARK FIXTURE (SYNTHETIC - NOT LIVE GDELT DATA)",
        "ground_truth_label": gt_labels,
        "ground_truth_category": gt_categories,
    })

    return df
