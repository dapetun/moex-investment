"""Тесты drawdown analysis модуля."""

import numpy as np
import pandas as pd

from moex_portfolio.drawdown_analysis import (
    analyze_drawdowns,
    drawdown_summary_table,
)


def test_analyze_drawdowns_basic():
    values = [1.0, 1.1, 1.05, 0.9, 0.95, 1.2]
    result = analyze_drawdowns(values, min_drawdown_pct=0.01)
    assert result.max_drawdown < 0
    assert result.n_drawdowns >= 1


def test_analyze_drawdowns_series():
    values = pd.Series([1.0, 1.1, 1.05, 0.9, 0.95, 1.2])
    result = analyze_drawdowns(values, min_drawdown_pct=0.01)
    assert len(result.underwater_series) == 6


def test_analyze_drawdowns_with_dates():
    values = np.array([1.0, 1.1, 0.9, 1.0, 1.2])
    dates = pd.date_range("2024-01-01", periods=5)
    result = analyze_drawdowns(values, dates=dates)
    assert result.worst_drawdown is not None
    assert result.worst_drawdown.drawdown_pct < 0


def test_drawdown_summary_table():
    values = [1.0, 1.1, 0.95, 0.85, 0.9, 1.15, 1.1, 1.0, 1.2]
    result = analyze_drawdowns(values, min_drawdown_pct=0.01)
    table = drawdown_summary_table(result, top_n=5)
    assert len(table) <= 5
    assert "Drawdown" in table.columns


def test_no_drawdown():
    values = [1.0, 1.1, 1.2, 1.3, 1.4, 1.5]
    result = analyze_drawdowns(values, min_drawdown_pct=0.01)
    assert result.n_drawdowns == 0
    assert result.max_drawdown == 0.0


def test_monotonic_decline():
    values = [1.0, 0.9, 0.8, 0.7, 0.6, 0.5]
    result = analyze_drawdowns(values, min_drawdown_pct=0.01)
    assert result.n_drawdowns >= 1
    assert result.max_drawdown < -0.4
    assert result.worst_drawdown is not None
    assert result.worst_drawdown.recovery_date is None
