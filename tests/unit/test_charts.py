"""
Unit tests for Plotly Chart Generation Factory.
Verifies figure creation, trace presence, and empty DataFrame resilience.
"""

import pandas as pd
import pytest

from crisislens.ui.charts import (
    create_activity_trend_figure,
    create_quad_class_donut,
    create_country_bar_chart,
)


def test_create_activity_trend_figure_valid():
    """Verify time series figure contains QuadClass bar traces and total trend line."""
    df = pd.DataFrame({
        "time_bucket": ["2026-10-28", "2026-10-29"],
        "verbal_coop": [10, 15],
        "material_coop": [5, 8],
        "verbal_conflict": [3, 4],
        "material_conflict": [2, 1],
        "total_events": [20, 28],
    })

    fig = create_activity_trend_figure(df, date_axis_title="Test Date")
    assert fig is not None
    assert len(fig.data) == 5  # 4 bar traces + 1 scatter trace
    assert fig.layout.barmode == "stack"


def test_create_activity_trend_figure_empty():
    """Verify graceful annotation when DataFrame is empty."""
    fig = create_activity_trend_figure(pd.DataFrame())
    assert fig is not None
    assert len(fig.data) == 0
    assert len(fig.layout.annotations) > 0


def test_create_quad_class_donut_valid():
    """Verify pie/donut figure creation with colors."""
    df = pd.DataFrame({
        "quad_class_name": ["Verbal Cooperation", "Material Conflict"],
        "event_count": [100, 50],
    })
    fig = create_quad_class_donut(df)
    assert fig is not None
    assert len(fig.data) == 1
    assert fig.data[0].hole == 0.55


def test_create_country_bar_chart_valid():
    """Verify horizontal bar chart creation for top countries."""
    df = pd.DataFrame({
        "country_name": ["United States", "Canada", "Germany"],
        "total_events": [1500, 300, 120],
    })
    fig = create_country_bar_chart(df)
    assert fig is not None
    assert len(fig.data) == 1
    assert fig.data[0].orientation == "h"
