"""Тесты backtesting модуля."""

import numpy as np
import pandas as pd

from moex_portfolio.backtesting import (
    BacktestResult,
    buy_and_hold_backtest,
    compare_backtests,
    walk_forward_backtest,
)


def _make_returns(n_days=504, n_stocks=5):
    np.random.seed(42)
    cols = [f"S{i}" for i in range(n_stocks)]
    data = np.random.randn(n_days, n_stocks) * 0.01 + 0.0003
    return pd.DataFrame(data, columns=cols)


def test_walk_forward_basic():
    returns = _make_returns()
    result = walk_forward_backtest(returns, lookback_days=126, rebalance_freq_days=21)
    assert isinstance(result, BacktestResult)
    assert result.total_return != 0
    assert result.annual_volatility > 0
    assert result.n_rebalances > 0


def test_walk_forward_min_variance():
    returns = _make_returns()
    result = walk_forward_backtest(returns, optimizer="min_variance")
    assert result.sharpe != 0


def test_buy_and_hold():
    returns = _make_returns()
    result = buy_and_hold_backtest(returns)
    assert isinstance(result, BacktestResult)
    assert result.total_return != 0
    assert result.n_rebalances == 0
    assert len(result.portfolio_values) == len(returns) + 1


def test_buy_and_hold_custom_weights():
    returns = _make_returns()
    weights = np.array([0.5, 0.2, 0.1, 0.1, 0.1])
    result = buy_and_hold_backtest(returns, weights)
    assert result.total_return != 0


def test_compare_backtests():
    returns = _make_returns()
    wf = walk_forward_backtest(returns, lookback_days=126)
    bh = buy_and_hold_backtest(returns)
    comp = compare_backtests([wf, bh])
    assert len(comp) == 2
    assert "Annual Return" in comp.columns
    assert "Sharpe" in comp.columns


def test_walk_forward_insufficient_data():
    returns = _make_returns(n_days=50)
    result = walk_forward_backtest(returns, lookback_days=252)
    assert len(result.portfolio_values) == 0
