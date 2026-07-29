"""Walk-forward backtesting engine.

Re-optimizes portfolio periodically on expanding/rolling window
and evaluates out-of-sample performance.
"""

import logging
from dataclasses import dataclass

import numpy as np
import pandas as pd

from .optimizer import max_sharpe_portfolio, min_variance_portfolio

logger = logging.getLogger(__name__)


@dataclass
class BacktestResult:
    """Результаты бэктестинга."""

    strategy_name: str
    dates: list
    portfolio_values: list[float]
    daily_returns: list[float]
    weights_history: list[dict[str, float]]
    rebalance_dates: list[str]
    total_return: float = 0.0
    annual_return: float = 0.0
    annual_volatility: float = 0.0
    sharpe: float = 0.0
    max_drawdown_val: float = 0.0
    n_rebalances: int = 0
    turnover_per_rebal: float = 0.0


def walk_forward_backtest(
    returns: pd.DataFrame,
    lookback_days: int = 252,
    rebalance_freq_days: int = 21,
    optimizer: str = "max_sharpe",
    max_weight: float = 0.3,
    risk_free_rate: float = 0.0,
) -> BacktestResult:
    """Walk-forward backtest: пересчитываем оптимальный портфель по расписанию.

    На каждом шаге:
    1. Смотрим на lookback_days назад
    2. Оптимизируем портфель на этих данных (in-sample)
    3. Применяем веса к следующим rebalance_freq_days (out-of-sample)
    4. Повторяем

    Args:
        returns: DataFrame с дневными доходностями.
        lookback_days: Окно истории для оптимизации.
        rebalance_freq_days: Как часто пересчитываем веса.
        optimizer: "max_sharpe" или "min_variance".
        max_weight: Максимальный вес одной акции.
        risk_free_rate: Безрисковая ставка.

    Returns:
        BacktestResult с результатами.
    """
    n_days = len(returns)
    if n_days < lookback_days + rebalance_freq_days:
        logger.warning("Not enough data for backtest: %d days", n_days)
        return _empty_result(optimizer)

    tickers = returns.columns.tolist()
    portfolio_values = [1.0]
    all_daily_returns = []
    weights_history = []
    rebalance_dates = []
    current_weights = np.array([1.0 / len(tickers)] * len(tickers))

    total_turnover = 0.0
    n_rebalances = 0

    i = lookback_days
    while i < n_days:
        in_sample = returns.iloc[i - lookback_days : i]
        mean_ret = in_sample.mean()
        cov = in_sample.cov()

        try:
            if optimizer == "min_variance":
                result = min_variance_portfolio(mean_ret, cov, max_weight=max_weight)
            else:
                result = max_sharpe_portfolio(
                    mean_ret, cov,
                    risk_free_rate=risk_free_rate,
                    max_weight=max_weight,
                )
            new_weights = result["weights"]
        except (np.linalg.LinAlgError, ValueError) as e:
            logger.warning("Optimization failed at step %d: %s, keeping current weights", i, e)
            new_weights = current_weights

        turnover = float(np.sum(np.abs(new_weights - current_weights)))
        total_turnover += turnover
        n_rebalances += 1
        current_weights = new_weights

        rebalance_dates.append(str(returns.index[i])[:10])
        weights_history.append(dict(zip(tickers, current_weights)))

        end = min(i + rebalance_freq_days, n_days)
        out_sample = returns.iloc[i:end]

        for _, row in out_sample.iterrows():
            daily_ret = float(np.dot(current_weights, row.values))
            all_daily_returns.append(daily_ret)
            new_value = portfolio_values[-1] * (1 + daily_ret)
            portfolio_values.append(new_value)

        i = end

    ret_series = pd.Series(all_daily_returns)
    total_ret = portfolio_values[-1] / portfolio_values[0] - 1
    n_years = len(all_daily_returns) / 252
    ann_ret = (1 + total_ret) ** (1 / max(n_years, 0.01)) - 1
    ann_vol = ret_series.std() * np.sqrt(252)
    sharpe_val = (ann_ret - risk_free_rate) / ann_vol if ann_vol > 0 else 0.0
    dd = _compute_max_drawdown_from_values(portfolio_values)

    logger.info(
        "Backtest (%s): return=%.2f%%, vol=%.2f%%, sharpe=%.3f, rebalances=%d",
        optimizer, ann_ret * 100, ann_vol * 100, sharpe_val, n_rebalances,
    )

    return BacktestResult(
        strategy_name=f"Walk-Forward {optimizer.replace('_', ' ').title()}",
        dates=list(range(len(portfolio_values))),
        portfolio_values=portfolio_values,
        daily_returns=all_daily_returns,
        weights_history=weights_history,
        rebalance_dates=rebalance_dates,
        total_return=total_ret,
        annual_return=ann_ret,
        annual_volatility=ann_vol,
        sharpe=sharpe_val,
        max_drawdown_val=dd,
        n_rebalances=n_rebalances,
        turnover_per_rebal=total_turnover / max(n_rebalances, 1),
    )


def buy_and_hold_backtest(
    returns: pd.DataFrame,
    weights: np.ndarray | list[float] | None = None,
) -> BacktestResult:
    """Buy-and-Hold бэктест: фиксируем веса один раз и держим.

    Args:
        returns: DataFrame с дневными доходностями.
        weights: Веса акций. Если None — равные.

    Returns:
        BacktestResult.
    """
    tickers = returns.columns.tolist()
    n = len(tickers)

    if weights is None:
        weights = np.array([1.0 / n] * n)
    weights = np.asarray(weights, dtype=float)

    portfolio_values = [1.0]
    all_daily_returns = []

    for _, row in returns.iterrows():
        daily_ret = float(np.dot(weights, row.values))
        all_daily_returns.append(daily_ret)
        portfolio_values.append(portfolio_values[-1] * (1 + daily_ret))

    total_ret = portfolio_values[-1] / portfolio_values[0] - 1
    n_years = len(all_daily_returns) / 252
    ann_ret = (1 + total_ret) ** (1 / max(n_years, 0.01)) - 1
    ret_series = pd.Series(all_daily_returns)
    ann_vol = ret_series.std() * np.sqrt(252)
    sharpe_val = ann_ret / ann_vol if ann_vol > 0 else 0.0
    dd = _compute_max_drawdown_from_values(portfolio_values)

    return BacktestResult(
        strategy_name="Buy & Hold",
        dates=list(range(len(portfolio_values))),
        portfolio_values=portfolio_values,
        daily_returns=all_daily_returns,
        weights_history=[dict(zip(tickers, weights))],
        rebalance_dates=[],
        total_return=total_ret,
        annual_return=ann_ret,
        annual_volatility=ann_vol,
        sharpe=sharpe_val,
        max_drawdown_val=dd,
        n_rebalances=0,
        turnover_per_rebal=0.0,
    )


def compare_backtests(
    results: list[BacktestResult],
) -> pd.DataFrame:
    """Сравнительная таблица результатов бэктестинга.

    Args:
        results: Список BacktestResult.

    Returns:
        DataFrame со сравнением.
    """
    rows = []
    for r in results:
        rows.append({
            "Strategy": r.strategy_name,
            "Total Return": r.total_return,
            "Annual Return": r.annual_return,
            "Annual Volatility": r.annual_volatility,
            "Sharpe": r.sharpe,
            "Max Drawdown": r.max_drawdown_val,
            "Rebalances": r.n_rebalances,
            "Avg Turnover": r.turnover_per_rebal,
        })
    return pd.DataFrame(rows)


def _compute_max_drawdown_from_values(values: list[float]) -> float:
    """Max drawdown из списка значений портфеля."""
    arr = np.array(values)
    running_max = np.maximum.accumulate(arr)
    drawdowns = (arr - running_max) / np.where(running_max > 0, running_max, 1)
    return float(drawdowns.min())


def _empty_result(optimizer: str) -> BacktestResult:
    """Пустой результат при недостатке данных."""
    return BacktestResult(
        strategy_name=f"Walk-Forward {optimizer.replace('_', ' ').title()}",
        dates=[], portfolio_values=[], daily_returns=[],
        weights_history=[], rebalance_dates=[],
    )
