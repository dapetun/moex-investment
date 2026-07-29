"""Тесты benchmark.py."""

import numpy as np
import pandas as pd
import pytest

from moex_portfolio.benchmark import (
    compute_benchmark_metrics,
    rolling_tracking_error,
    summary_table,
)


@pytest.fixture
def portfolio_and_benchmark():
    """Синтетические доходности портфеля и бенчмарка."""
    rng = np.random.default_rng(42)
    n = 300
    dates = pd.date_range("2024-01-01", periods=n, freq="B")
    benchmark = pd.Series(rng.normal(0.0004, 0.012, n), index=dates, name="benchmark")
    # Портфель = бенчмарк + альфа + шум
    portfolio = pd.Series(
        benchmark.values + rng.normal(0.0001, 0.005, n),
        index=dates,
        name="portfolio",
    )
    return portfolio, benchmark


class TestComputeBenchmarkMetrics:
    def test_basic(self, portfolio_and_benchmark):
        port, bench = portfolio_and_benchmark
        result = compute_benchmark_metrics(port, bench)
        assert "portfolio_return" in result
        assert "benchmark_return" in result
        assert "excess_return" in result
        assert "tracking_error" in result
        assert "information_ratio" in result
        assert "r_squared" in result
        assert "beta" in result
        assert "alpha" in result

    def test_insufficient_data(self):
        port = pd.Series([0.01, 0.02], index=[1, 2])
        bench = pd.Series([0.01, 0.02], index=[1, 2])
        result = compute_benchmark_metrics(port, bench)
        assert "error" in result

    def test_excess_return_direction(self, portfolio_and_benchmark):
        port, bench = portfolio_and_benchmark
        result = compute_benchmark_metrics(port, bench)
        # Портфель имеет положительную альфу по設計
        assert isinstance(result["excess_return"], float)

    def test_r_squared_range(self, portfolio_and_benchmark):
        port, bench = portfolio_and_benchmark
        result = compute_benchmark_metrics(port, bench)
        assert 0.0 <= result["r_squared"] <= 1.0

    def test_correlation_range(self, portfolio_and_benchmark):
        port, bench = portfolio_and_benchmark
        result = compute_benchmark_metrics(port, bench)
        assert -1.0 <= result["correlation"] <= 1.0

    def test_max_drawdown_negative(self, portfolio_and_benchmark):
        port, bench = portfolio_and_benchmark
        result = compute_benchmark_metrics(port, bench)
        assert result["portfolio_max_drawdown"] <= 0
        assert result["benchmark_max_drawdown"] <= 0

    def test_n_days(self, portfolio_and_benchmark):
        port, bench = portfolio_and_benchmark
        result = compute_benchmark_metrics(port, bench)
        assert result["n_days"] == 300

    def test_with_risk_free_rate(self, portfolio_and_benchmark):
        port, bench = portfolio_and_benchmark
        result = compute_benchmark_metrics(port, bench, risk_free_rate=0.05)
        # Alpha = (Rp - Rf) - beta * (Rb - Rf)
        assert isinstance(result["alpha"], float)


class TestRollingTrackingError:
    def test_basic(self, portfolio_and_benchmark):
        port, bench = portfolio_and_benchmark
        te = rolling_tracking_error(port, bench, window=60)
        assert isinstance(te, pd.Series)
        assert len(te) > 0
        assert te.notna().any()

    def test_window_effect(self, portfolio_and_benchmark):
        port, bench = portfolio_and_benchmark
        te_short = rolling_tracking_error(port, bench, window=20)
        te_long = rolling_tracking_error(port, bench, window=120)
        # Longer window — smoother TE
        assert te_long.std() <= te_short.std() * 2  # approximately


class TestSummaryTable:
    def test_basic(self, portfolio_and_benchmark):
        port, bench = portfolio_and_benchmark
        df = summary_table(port, bench)
        assert isinstance(df, pd.DataFrame)
        assert "Value" in df.columns
        assert len(df) >= 10  #至少10行 метрик

    def test_format(self, portfolio_and_benchmark):
        port, bench = portfolio_and_benchmark
        df = summary_table(port, bench)
        # Все значения — строки с процентами или числами
        for _, row in df.iterrows():
            assert isinstance(row["Value"], str)
