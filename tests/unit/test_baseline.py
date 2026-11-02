"""
Unit and Integration Tests for Phase 3:
Data Readiness Gate, Statistical Baseline Detector, Explainability Engine,
Synthetic Benchmark Fixtures, and Visualizations.
"""

from pathlib import Path
import pytest
import pandas as pd
import numpy as np

from crisislens.features.baseline import DataReadinessGate, DataReadinessReport, regularize_time_series
from crisislens.models.baseline import StatisticalBaselineDetector
from crisislens.models.synthetic import generate_synthetic_benchmark_fixture
from crisislens.explainability.templates import generate_anomaly_explanation
from crisislens.ui.charts import create_anomaly_timeline_figure, create_anomaly_severity_donut
from crisislens.ui.data_service import DataService
from crisislens.storage.event_store import EventStore


# -----------------------------------------------------------------------------
# 1. Data Readiness Gate Tests
# -----------------------------------------------------------------------------

def test_data_readiness_empty_dataframe():
    gate = DataReadinessGate(min_intervals=28, min_span_hours=7.0)
    report = gate.evaluate(pd.DataFrame(), time_col="timestamp")
    assert report.status == "INSUFFICIENT"
    assert report.can_score_live is False
    assert report.n_intervals == 0
    assert "No reporting data found" in report.reason


def test_data_readiness_insufficient_intervals():
    # Only 2 intervals spanning 15 minutes (replicates current live DuckDB state)
    df = pd.DataFrame({
        "timestamp": ["2026-10-29 15:30:00", "2026-10-29 15:45:00"],
        "event_count": [500, 2398],
    })
    gate = DataReadinessGate(min_intervals=28, min_span_hours=7.0)
    report = gate.evaluate(df, time_col="timestamp")
    assert report.status == "INSUFFICIENT"
    assert report.can_score_live is False
    assert report.n_intervals == 2
    assert "28" in report.reason


def test_data_readiness_sufficient_and_gap_detection():
    # 35 hourly intervals with one 5-hour gap
    times = pd.date_range("2026-10-01 00:00:00", periods=20, freq="1h").tolist()
    # jump 5 hours to next day
    times.extend(pd.date_range("2026-10-02 01:00:00", periods=15, freq="1h").tolist())
    df = pd.DataFrame({"timestamp": times, "event_count": [100] * len(times)})


    gate = DataReadinessGate(min_intervals=28, min_span_hours=7.0)
    report = gate.evaluate(df, time_col="timestamp")
    assert report.status == "SUFFICIENT"
    assert report.can_score_live is True
    assert report.n_intervals == 35
    assert report.missing_gaps_count >= 1
    assert report.span_hours >= 24.0


def test_regularize_time_series_gap_filling():
    df = pd.DataFrame({
        "timestamp": ["2026-10-01 00:00:00", "2026-10-01 00:30:00"],
        "event_count": [10, 20],
    })
    reg = regularize_time_series(df, time_col="timestamp", val_col="event_count", freq="15min")
    assert len(reg) == 3
    # Middle interval (00:15:00) should be filled with 0
    assert reg.iloc[1]["event_count"] == 0


# -----------------------------------------------------------------------------
# 2. Statistical Baseline Detector Unit Tests
# -----------------------------------------------------------------------------

def test_detector_parameter_validation():
    with pytest.raises(ValueError, match="window_size must be at least 3"):
        StatisticalBaselineDetector(window_size=2)
    with pytest.raises(ValueError, match="min_history must be between"):
        StatisticalBaselineDetector(window_size=10, min_history=15)
    with pytest.raises(ValueError, match="zscore_threshold must be positive"):
        StatisticalBaselineDetector(zscore_threshold=-1.0)
    with pytest.raises(ValueError, match="iqr_multiplier must be positive"):
        StatisticalBaselineDetector(iqr_multiplier=0)


def test_detector_zero_leakage_guarantee():
    """
    CRITICAL: Verify that an extreme spike at time t is strictly EXCLUDED
    from the baseline statistics (mean, std) calculated for time t.
    The spike must only impact baseline statistics at t+1 and later.
    """
    n = 20
    counts = [100.0] * n
    # Inject massive spike at index 10
    counts[10] = 50_000.0
    times = pd.date_range("2026-10-01", periods=n, freq="1h")
    df = pd.DataFrame({"timestamp": times, "event_count": counts})

    detector = StatisticalBaselineDetector(window_size=5, min_history=3, zscore_threshold=2.5)
    scored = detector.fit_detect(df, time_col="timestamp", count_col="event_count")

    # At index 10, the baseline mean must still reflect the prior 5 points (all 100.0)
    mean_at_spike = scored.loc[10, "baseline_mean"]
    assert pytest.approx(mean_at_spike, rel=1e-3) == 100.0, (
        f"Data leakage detected! Expected baseline 100.0 at spike, got {mean_at_spike}"
    )

    # The spike at index 10 must be flagged as an anomaly
    assert scored.loc[10, "is_anomaly"] is True or scored.loc[10, "is_anomaly"] == 1
    assert scored.loc[10, "severity"] == "EXTREME"

    # Only at index 11 should the baseline mean include the 50,000 count from index 10
    mean_at_next = scored.loc[11, "baseline_mean"]
    assert mean_at_next > 100.0


def test_detector_zero_variance_safeguard():
    """
    Verify that a constant count series (std=0) does not cause division-by-zero,
    clamping the standard deviation to 1.0 and keeping Z=0.
    """
    counts = [50] * 30
    times = pd.date_range("2026-10-01", periods=30, freq="1h")
    df = pd.DataFrame({"timestamp": times, "event_count": counts})

    detector = StatisticalBaselineDetector(window_size=10, min_history=5)
    scored = detector.fit_detect(df)

    scored_valid = scored.dropna(subset=["baseline_mean"])
    assert not scored_valid.empty
    # Z-scores should all be exactly 0.0, no NaN or Inf
    for z in scored_valid["z_score"]:
        assert pytest.approx(z, abs=1e-5) == 0.0
        assert not np.isnan(z)
        assert not np.isinf(z)
    assert not scored_valid["is_anomaly"].any()


def test_detector_min_history_enforcement():
    counts = [100] * 20
    times = pd.date_range("2026-10-01", periods=20, freq="1h")
    df = pd.DataFrame({"timestamp": times, "event_count": counts})

    detector = StatisticalBaselineDetector(window_size=10, min_history=6)
    scored = detector.fit_detect(df)

    # First 6 points must have INSUFFICIENT_HISTORY
    for i in range(6):
        assert scored.loc[i, "status"] == "INSUFFICIENT_HISTORY"
        assert np.isnan(scored.loc[i, "baseline_mean"])
        assert bool(scored.loc[i, "is_anomaly"]) is False
        assert scored.loc[i, "severity"] == "NORMAL"



    # Point 6 and onward should be SCORED
    assert scored.loc[6, "status"] == "SCORED"
    assert not np.isnan(scored.loc[6, "baseline_mean"])


def test_detector_empty_dataframe():
    detector = StatisticalBaselineDetector()
    scored = detector.fit_detect(pd.DataFrame())
    assert scored.empty
    assert "observed_count" in scored.columns
    assert "is_anomaly" in scored.columns


# -----------------------------------------------------------------------------
# 3. Synthetic Benchmark Fixture & End-to-End Detection
# -----------------------------------------------------------------------------

def test_synthetic_benchmark_fixture_properties():
    df = generate_synthetic_benchmark_fixture(days=14, interval_minutes=60, seed=42)
    assert len(df) == 336
    assert "timestamp" in df.columns
    assert "event_count" in df.columns
    assert df["is_synthetic"].all() is True or df["is_synthetic"].all() == 1
    assert "BENCHMARK FIXTURE" in df["dataset_label"].iloc[0]

    # Verify that exactly 3 ground truth injected spikes exist
    spikes = df[df["ground_truth_label"] == "INJECTED_SPIKE"]
    assert len(spikes) == 3


def test_synthetic_benchmark_detector_end_to_end():
    df = generate_synthetic_benchmark_fixture(days=14, interval_minutes=60, seed=42)
    detector = StatisticalBaselineDetector(
        window_size=24,
        min_history=12,
        zscore_threshold=2.5,
        iqr_multiplier=1.5,
    )
    scored = detector.fit_detect(df, time_col="timestamp", count_col="event_count")

    # Injected spikes must all be detected
    anomalies = scored[scored["is_anomaly"] == True]
    assert len(anomalies) >= 3

    # Check that Day 12 extreme spike is detected as EXTREME
    extreme_spikes = scored[scored["severity"] == "EXTREME"]
    assert not extreme_spikes.empty
    assert extreme_spikes["z_score"].max() > 7.0


# -----------------------------------------------------------------------------
# 4. Explainability Engine Tests
# -----------------------------------------------------------------------------

def test_generate_anomaly_explanation_normal():
    record = {
        "timestamp": "2026-10-05 12:00:00",
        "observed_count": 125,
        "baseline_mean": 120.0,
        "baseline_std": 15.0,
        "z_score": 0.33,
        "upper_fence": 160.0,
        "severity": "NORMAL",
        "is_anomaly": False,
    }
    exp = generate_anomaly_explanation(record)
    assert exp["is_anomaly"] is False
    assert "remained within normal" in exp["narrative"]
    assert "Methodology Caveat" in exp["caveats"]
    assert r"Z = \frac{Y_t - \mu_t}{\sigma_t}" in exp["formula_latex"]


def test_generate_anomaly_explanation_extreme_anomaly():
    record = {
        "timestamp": "2026-10-12 19:00:00",
        "observed_count": 450,
        "baseline_mean": 120.0,
        "baseline_std": 20.0,
        "z_score": 16.5,
        "upper_fence": 170.0,
        "severity": "EXTREME",
        "is_anomaly": True,
    }
    exp = generate_anomaly_explanation(record, zscore_threshold=2.5, iqr_multiplier=1.5)
    assert exp["is_anomaly"] is True
    assert exp["severity"] == "EXTREME"
    assert "flagged a EXTREME anomaly" in exp["narrative"]
    assert "Dual Criteria" in exp["rule_triggered"]
    assert exp["deviation_pct"] == 275.0


def test_generate_anomaly_explanation_insufficient_history():
    record = {
        "timestamp": "2026-10-01 00:00:00",
        "observed_count": 100,
        "baseline_mean": None,
        "baseline_std": None,
        "z_score": None,
    }
    exp = generate_anomaly_explanation(record)
    assert exp["status"] == "INSUFFICIENT_HISTORY"
    assert exp["is_anomaly"] is False


# -----------------------------------------------------------------------------
# 5. DataService Phase 3 Integration Tests
# -----------------------------------------------------------------------------

@pytest.fixture
def test_gated_service(tmp_path: Path) -> DataService:
    """Create an isolated DataService with only 2 intervals to test data-readiness gating."""
    db_path = tmp_path / "gated_test.duckdb"
    store = EventStore(db_path, read_only=False)
    df = pd.DataFrame({
        "GLOBALEVENTID": [101, 102],
        "event_date": ["2026-10-29", "2026-10-29"],
        "Year": [2026, 2026],
        "MonthYear": [202610, 202610],
        "Actor1Code": ["GOV", "CVL"],
        "Actor1Name": ["GOV", "CVL"],
        "Actor1CountryCode": ["USA", "USA"],
        "Actor2Code": ["", ""],
        "Actor2Name": ["", ""],
        "Actor2CountryCode": ["", ""],
        "IsRootEvent": [1, 1],
        "EventCode": ["010", "020"],
        "EventBaseCode": ["010", "020"],
        "EventRootCode": ["01", "02"],
        "QuadClass": [1, 2],
        "GoldsteinScale": [3.0, 4.0],
        "NumMentions": [5, 10],
        "NumSources": [1, 2],
        "NumArticles": [5, 10],
        "AvgTone": [1.0, 2.0],
        "ActionGeo_Lat": [38.89, 38.89],
        "ActionGeo_Long": [-77.03, -77.03],
        "ActionGeo_CountryCode": ["US", "US"],
        "ActionGeo_FullName": ["Washington", "Washington"],
        "DATEADDED": [20261029153000, 20261029154500],
        "SOURCEURL": ["http://ex.com/1", "http://ex.com/2"],
    })
    store.upsert_events(df)
    store.close()
    return DataService(db_path=db_path)



def test_data_service_check_readiness(test_gated_service: DataService):
    report = test_gated_service.check_data_readiness(min_intervals=28)
    assert isinstance(report, DataReadinessReport)
    # Database has only 2 batches (15 mins), so readiness must be INSUFFICIENT
    assert report.status == "INSUFFICIENT"
    assert report.can_score_live is False
    assert report.n_intervals == 2


def test_data_service_detect_anomalies_benchmark(test_gated_service: DataService):
    scored, report = test_gated_service.detect_anomalies(source="benchmark")
    assert report.can_score_live is True
    assert len(scored) == 336
    assert "is_anomaly" in scored.columns
    assert scored["is_anomaly"].sum() >= 3


def test_data_service_detect_anomalies_live_gated(test_gated_service: DataService):
    scored, report = test_gated_service.detect_anomalies(source="live")
    # Live store is gated
    assert report.can_score_live is False
    # Scored returns unscored time series (2 intervals)
    assert len(scored) == 2



# -----------------------------------------------------------------------------
# 6. Plotly Charts Tests
# -----------------------------------------------------------------------------

def test_create_anomaly_timeline_figure_valid():
    df = generate_synthetic_benchmark_fixture(days=3, interval_minutes=60, seed=42)
    detector = StatisticalBaselineDetector(window_size=10, min_history=5)
    scored = detector.fit_detect(df)

    fig = create_anomaly_timeline_figure(scored)
    assert fig is not None
    assert len(fig.data) >= 3  # Mean, fence, observed


def test_create_anomaly_timeline_figure_empty():
    fig = create_anomaly_timeline_figure(pd.DataFrame())
    assert fig is not None
    assert len(fig.data) == 0


def test_create_anomaly_severity_donut():
    df = pd.DataFrame({"severity": ["NORMAL", "NORMAL", "MODERATE", "EXTREME"]})
    fig = create_anomaly_severity_donut(df)
    assert fig is not None
    assert len(fig.data) == 1

    fig_empty = create_anomaly_severity_donut(pd.DataFrame())
    assert fig_empty is not None


# -----------------------------------------------------------------------------
# 7. Statistical Quality & Correctness Edge-Case Tests (Phase 3 Audit)
# -----------------------------------------------------------------------------

def test_flat_baseline_small_increase_poisson_safeguard():
    """
    AUDIT CHECK: A flat baseline (e.g. 50 events/interval) followed by a minor
    statistical fluctuation (e.g. 52 events) must NOT trigger an anomaly.
    The Poisson variance floor ensures sigma is at least sqrt(mean) ~ 7.07,
    so Z = (52 - 50) / 7.07 = 0.28 < 2.5.
    """
    counts = [50.0] * 20 + [52.0]
    times = pd.date_range("2026-10-01", periods=len(counts), freq="1h")
    df = pd.DataFrame({"timestamp": times, "event_count": counts})

    detector = StatisticalBaselineDetector(window_size=10, min_history=5, zscore_threshold=2.5)
    scored = detector.fit_detect(df)

    last_idx = len(counts) - 1
    assert bool(scored.loc[last_idx, "is_anomaly"]) is False
    assert scored.loc[last_idx, "severity"] == "NORMAL"
    assert scored.loc[last_idx, "z_score"] < 1.0


def test_flat_baseline_large_increase_is_flagged():
    """
    AUDIT CHECK: A flat baseline (50 events) followed by a substantial surge
    (100 events, 100% surge) MUST trigger an anomaly under Poisson dispersion floor.
    Z = (100 - 50) / 7.07 = 7.07 > 2.5.
    """
    counts = [50.0] * 20 + [100.0]
    times = pd.date_range("2026-10-01", periods=len(counts), freq="1h")
    df = pd.DataFrame({"timestamp": times, "event_count": counts})

    detector = StatisticalBaselineDetector(window_size=10, min_history=5, zscore_threshold=2.5)
    scored = detector.fit_detect(df)

    last_idx = len(counts) - 1
    assert bool(scored.loc[last_idx, "is_anomaly"]) is True
    assert scored.loc[last_idx, "severity"] == "EXTREME"
    assert scored.loc[last_idx, "z_score"] > 5.0


def test_observation_flagged_by_both_methods():
    """
    AUDIT CHECK: When an observation exceeds BOTH the parametric Z-score and
    the Tukey upper fence, explainability accurately identifies dual criteria.
    """
    rec = {
        "timestamp": "2026-10-05 14:00:00",
        "observed_count": 300,
        "baseline_mean": 100.0,
        "baseline_std": 15.0,
        "z_score": 13.33,
        "upper_fence": 160.0,
        "severity": "EXTREME",
        "is_anomaly": True,
    }
    exp = generate_anomaly_explanation(rec, zscore_threshold=2.5, iqr_multiplier=1.5)
    assert exp["rule_triggered"] == "Dual Criteria (Rolling Z-Score & Tukey IQR Fence)"
    assert "on both statistical criteria" in exp["narrative"]
    assert exp["is_anomaly"] is True


def test_observation_flagged_by_zscore_only():
    """
    AUDIT CHECK: When an observation triggers Z-score only (Z >= 2.5) but remains
    within the Tukey fence, narrative reflects this without claiming Tukey was surpassed.
    """
    rec = {
        "timestamp": "2026-10-05 15:00:00",
        "observed_count": 145,
        "baseline_mean": 100.0,
        "baseline_std": 15.0,
        "z_score": 3.0,
        "upper_fence": 150.0,  # Observed 145 <= Upper fence 150
        "severity": "HIGH",
        "is_anomaly": True,
    }
    exp = generate_anomaly_explanation(rec, zscore_threshold=2.5, iqr_multiplier=1.5)
    assert "Rolling Z-Score" in exp["rule_triggered"]
    assert "while remaining within the Tukey upper fence" in exp["narrative"]


def test_observation_flagged_by_tukey_only():
    """
    AUDIT CHECK: When an observation triggers Tukey fence only but Z < cutoff (e.g. skewed variance),
    narrative reflects this accurately.
    """
    rec = {
        "timestamp": "2026-10-05 16:00:00",
        "observed_count": 160,
        "baseline_mean": 100.0,
        "baseline_std": 30.0,
        "z_score": 2.0,       # 2.0 < cutoff 2.5
        "upper_fence": 140.0,  # Observed 160 > 140
        "severity": "MODERATE",
        "is_anomaly": True,
    }
    exp = generate_anomaly_explanation(rec, zscore_threshold=2.5, iqr_multiplier=1.5)
    assert "Tukey IQR Upper Fence" in exp["rule_triggered"]
    assert "while the parametric Z-score remained at +2.00" in exp["narrative"]


def test_severity_policy_consistency():
    """
    AUDIT CHECK: Severity classification must be monotonic, consistent with detection
    thresholds, and never produce NORMAL for a flagged anomaly.
    """
    detector = StatisticalBaselineDetector(window_size=10, min_history=5, zscore_threshold=2.5)
    
    # 20 baseline points of ~100
    counts = [100.0] * 15 + [140.0, 160.0, 220.0]
    times = pd.date_range("2026-10-01", periods=len(counts), freq="1h")
    df = pd.DataFrame({"timestamp": times, "event_count": counts})
    scored = detector.fit_detect(df)

    flagged = scored[scored["is_anomaly"] == True]
    assert not flagged.empty
    for _, row in flagged.iterrows():
        assert row["severity"] in ["MODERATE", "HIGH", "EXTREME"]
        assert row["severity"] != "NORMAL"

    # Extreme spike must have EXTREME severity
    last_row = scored.iloc[-1]
    assert last_row["observed_count"] == 220.0
    assert last_row["severity"] == "EXTREME"


def test_missing_intervals_vs_observed_zeros_regularization():
    """
    AUDIT CHECK: Differentiate between observed 0 events and unobserved missing data.
    When regularizing with fill_value=np.nan, missing intervals are not masked as zeros.
    """
    df = pd.DataFrame({
        "timestamp": ["2026-10-01 00:00:00", "2026-10-01 00:30:00"],
        "event_count": [10.0, 20.0],
    })
    # Regularize with np.nan to preserve missing unobserved status
    reg = regularize_time_series(df, time_col="timestamp", val_col="event_count", freq="15min", fill_value=np.nan)
    assert len(reg) == 3
    # The unobserved gap at 00:15 must be NaN, NOT 0.0
    assert np.isnan(reg.iloc[1]["event_count"])
    assert reg.iloc[0]["event_count"] == 10.0
    assert reg.iloc[2]["event_count"] == 20.0


def test_synthetic_and_live_mode_isolation(test_gated_service: DataService):
    """
    AUDIT CHECK: Synthetic benchmark data must never be mixed with or written to
    the live DuckDB database store.
    """
    # 1. Fetch synthetic benchmark series
    bench_df = test_gated_service.get_synthetic_benchmark_series()
    assert bench_df["is_synthetic"].all() is True or bench_df["is_synthetic"].all() == 1
    assert "BENCHMARK FIXTURE" in bench_df["dataset_label"].iloc[0]

    # 2. Verify live DuckDB store row count before and after benchmark scoring
    initial_count = test_gated_service.get_data_freshness_info()["total_events"]
    test_gated_service.detect_anomalies(source="benchmark")
    post_count = test_gated_service.get_data_freshness_info()["total_events"]

    assert initial_count == post_count, "Benchmark execution must NOT write to live database!"

