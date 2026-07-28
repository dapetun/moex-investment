"""Тесты модуля rebalancing."""

import numpy as np
import pandas as pd

from moex_portfolio.rebalancing import (
    RebalanceConfig,
    compare_strategies,
    simulate_buy_and_hold,
    simulate_rebalancing,
)


def _sample_returns(n_days=252, n_stocks=5):
    """Генерация тестовых доходностей."""
    np.random.seed(42)
    dates = pd.bdate_range("2023-01-01", periods=n_days)
    tickers = [f"S{i}" for i in range(n_stocks)]
    data = np.random.normal(0.0003, 0.02, (n_days, n_stocks))
    return pd.DataFrame(data, index=dates, columns=tickers)


def _equal_weights(n_stocks=5):
    """Равные веса."""
    tickers = [f"S{i}" for i in range(n_stocks)]
    return {t: 1.0 / n_stocks for t in tickers}


def test_simulate_rebalancing():
    returns = _sample_returns()
    weights = _equal_weights()
    config = RebalanceConfig(target_weights=weights, rebalance_freq_days=21)

    result = simulate_rebalancing(returns, config)

    assert len(result.dates) == len(returns)
    assert len(result.portfolio_values) == len(returns)
    assert result.portfolio_values[0] == 1_000_000.0
    assert result.annual_return != 0.0
    assert result.annual_volatility > 0
    assert result.max_drawdown <= 0


def test_simulate_buy_and_hold():
    returns = _sample_returns()
    weights = _equal_weights()

    result = simulate_buy_and_hold(returns, weights)

    assert len(result.dates) == len(returns)
    assert result.total_cost == 0.0
    assert result.n_rebalances == 0
    assert result.portfolio_values[0] == 1_000_000.0


def test_compare_strategies():
    returns = _sample_returns()
    weights = _equal_weights()
    config = RebalanceConfig(target_weights=weights, rebalance_freq_days=21)

    comparison = compare_strategies(returns, config)

    assert "Metric" in comparison.columns
    assert "Rebalancing" in comparison.columns
    assert "Buy & Hold" in comparison.columns
    assert len(comparison) == 6


def test_rebalancing_with_high_frequency():
    returns = _sample_returns(n_days=504)
    weights = _equal_weights()
    config = RebalanceConfig(
        target_weights=weights,
        rebalance_freq_days=5,  # Очень часто
        min_drift=0.01,  # Низкий порог
    )

    result = simulate_rebalancing(returns, config)
    assert result.n_rebalances > 0
    assert result.total_cost > 0
