"""Тесты модуля optimizer."""

import numpy as np
import pandas as pd

from moex_portfolio.optimizer import (
    efficient_frontier,
    max_sharpe_portfolio,
    min_variance_portfolio,
)


def _sample_data():
    """Генерация тестовых данных."""
    np.random.seed(42)
    mean_returns = pd.Series([0.0004, 0.0002, 0.0003])
    cov = pd.DataFrame(
        [[0.04, 0.01, 0.02], [0.01, 0.09, 0.03], [0.02, 0.03, 0.06]],
        index=["A", "B", "C"],
        columns=["A", "B", "C"],
    )
    return mean_returns, cov


def test_max_sharpe_portfolio():
    mean_returns, cov = _sample_data()
    result = max_sharpe_portfolio(mean_returns, cov)

    assert "weights" in result
    assert "return" in result
    assert "volatility" in result
    assert "sharpe" in result
    assert abs(sum(result["weights"]) - 1.0) < 1e-6
    assert all(w >= 0 for w in result["weights"])
    # With 3 assets and max_weight=0.3, auto-normalized to 1/3
    assert all(w <= 1.0 / 3 + 1e-6 for w in result["weights"])
    assert result["sharpe"] > 0


def test_min_variance_portfolio():
    mean_returns, cov = _sample_data()
    result = min_variance_portfolio(mean_returns, cov)

    assert abs(sum(result["weights"]) - 1.0) < 1e-6
    assert all(w >= 0 for w in result["weights"])
    assert result["volatility"] > 0


def test_efficient_frontier():
    mean_returns, cov = _sample_data()
    ef = efficient_frontier(mean_returns, cov, n_points=20)

    assert len(ef) > 0
    assert "return" in ef.columns
    assert "volatility" in ef.columns
    assert "sharpe" in ef.columns

    # Волатильность должна быть положительной
    assert all(ef["volatility"] > 0)

    # Доходность должна быть в разумном диапазоне
    assert ef["return"].min() > -1.0
    assert ef["return"].max() < 10.0


def test_custom_bounds():
    mean_returns, cov = _sample_data()
    result = max_sharpe_portfolio(mean_returns, cov, min_weight=0.1, max_weight=0.5)

    assert all(w >= 0.1 - 1e-6 for w in result["weights"])
    assert all(w <= 0.5 + 1e-6 for w in result["weights"])
