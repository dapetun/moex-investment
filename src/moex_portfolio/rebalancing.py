"""Симуляция ребалансирования портфеля с учётом транзакционных издержек."""

import logging
from dataclasses import dataclass

import numpy as np
import pandas as pd

from .config import MAX_WEIGHT, MIN_WEIGHT
from .metrics import max_drawdown

logger = logging.getLogger(__name__)


@dataclass
class RebalanceResult:
    """Результат симуляции ребалансирования."""

    dates: list[str]
    portfolio_values: list[float]
    weights_history: list[dict[str, float]]
    turnover_history: list[float]
    total_cost: float
    n_rebalances: int
    annual_return: float
    annual_volatility: float
    sharpe: float
    max_drawdown: float

    def to_dataframe(self) -> pd.DataFrame:
        """Конвертация в DataFrame."""
        return pd.DataFrame({
            "date": self.dates,
            "value": self.portfolio_values,
        }).set_index("date")


@dataclass
class RebalanceConfig:
    """Параметры ребалансирования."""

    target_weights: dict[str, float]
    rebalance_freq_days: int = 21  # ~1 месяц
    transaction_cost_bps: float = 10.0  # 0.1% = 10 basis points
    min_drift: float = 0.05  # 5% — минимальное отклонение для ребаланса
    min_weight: float = MIN_WEIGHT
    max_weight: float = MAX_WEIGHT


def _compute_turnover(old_weights: dict[str, float], new_weights: dict[str, float]) -> float:
    """Вычисление оборота (суммарный объём сделок).

    Args:
        old_weights: Текущие веса.
        new_weights: Целевые веса.

    Returns:
        Суммарный оборот (0..2).
    """
    all_tickers = set(old_weights) | set(new_weights)
    turnover = 0.0
    for t in all_tickers:
        old = old_weights.get(t, 0.0)
        new = new_weights.get(t, 0.0)
        turnover += abs(new - old)
    return turnover


def _needs_rebalance(
    current_weights: dict[str, float],
    target_weights: dict[str, float],
    min_drift: float,
) -> bool:
    """Проверка необходимости ребалансировки.

    Args:
        current_weights: Текущие веса.
        target_weights: Целевые веса.
        min_drift: Минимальное отклонение для触发 ребаланса.

    Returns:
        True если нужно ребалансировать.
    """
    max_drift = 0.0
    all_tickers = set(current_weights) | set(target_weights)
    for t in all_tickers:
        drift = abs(current_weights.get(t, 0.0) - target_weights.get(t, 0.0))
        max_drift = max(max_drift, drift)
    return max_drift > min_drift


def simulate_rebalancing(
    returns: pd.DataFrame,
    config: RebalanceConfig,
    cov_method: str = "sample",
    lookback_window: int = 60,
) -> RebalanceResult:
    """Симуляция периодического ребалансирования портфеля.

    Стратегия:
    1. Начинаем с target_weights
    2. Каждые rebalance_freq_days дней проверяем отклонение
    3. Если отклонение > min_drift — ребалансируем
    4. Учитываем транзакционные издержки

    Args:
        returns: DataFrame с дневными доходностями.
        config: Параметры ребалансирования.
        cov_method: Метод расчёта ковариации.
        lookback_window: Окно для пересчёта оптимизации.

    Returns:
        RebalanceResult с метриками.
    """
    tickers = list(config.target_weights.keys())
    returns = returns[tickers].dropna()

    dates = returns.index.tolist()
    n_days = len(dates)

    # Начальные значения
    portfolio_value = 1_000_000.0  # 1M RUB
    current_weights = dict(config.target_weights)
    total_cost = 0.0
    n_rebalances = 0

    portfolio_values = [portfolio_value]
    weights_history = [dict(current_weights)]
    turnover_history = [0.0]

    for i in range(1, n_days):
        day_return = returns.iloc[i]
        weighted_return = sum(current_weights.get(t, 0.0) * day_return.get(t, 0.0) for t in tickers)
        portfolio_value *= (1 + weighted_return)

        # Обновляем веса по рыночной стоимости
        new_weights = {}
        for t in tickers:
            old_w = current_weights.get(t, 0.0)
            r = day_return.get(t, 0.0)
            new_w = old_w * (1 + r) / (1 + weighted_return) if (1 + weighted_return) != 0 else old_w
            new_weights[t] = new_w

        # Проверяем необходимость ребалансировки
        day_num = i + 1
        if day_num % config.rebalance_freq_days == 0:
            if _needs_rebalance(new_weights, config.target_weights, config.min_drift):
                turnover = _compute_turnover(new_weights, config.target_weights)
                cost = portfolio_value * turnover * (config.transaction_cost_bps / 10_000)
                portfolio_value -= cost
                total_cost += cost
                n_rebalances += 1
                new_weights = dict(config.target_weights)
                turnover_history.append(turnover)
            else:
                turnover_history.append(0.0)
        else:
            turnover_history.append(0.0)

        current_weights = new_weights
        portfolio_values.append(portfolio_value)
        weights_history.append(dict(current_weights))

    # Вычисляем метрики
    values_series = pd.Series(portfolio_values, index=dates)
    daily_returns = values_series.pct_change().dropna()

    ann_ret = daily_returns.mean() * 252
    ann_vol = daily_returns.std() * np.sqrt(252)
    sharpe_val = (ann_ret - 0.0) / ann_vol if ann_vol > 0 else 0.0
    max_dd = max_drawdown(daily_returns)

    result = RebalanceResult(
        dates=[str(d)[:10] for d in dates],
        portfolio_values=portfolio_values,
        weights_history=weights_history,
        turnover_history=turnover_history,
        total_cost=total_cost,
        n_rebalances=n_rebalances,
        annual_return=ann_ret,
        annual_volatility=ann_vol,
        sharpe=sharpe_val,
        max_drawdown=max_dd,
    )

    logger.info(
        "Rebalancing sim: %d days, %d rebalances, total cost %.2f, sharpe=%.3f",
        n_days, n_rebalances, total_cost, sharpe_val,
    )
    return result


def simulate_buy_and_hold(
    returns: pd.DataFrame,
    target_weights: dict[str, float],
) -> RebalanceResult:
    """Симуляция buy-and-hold стратегии (без ребалансирования).

    Args:
        returns: DataFrame с дневными доходностями.
        target_weights: Начальные веса.

    Returns:
        RebalanceResult.
    """
    tickers = list(target_weights.keys())
    returns = returns[tickers].dropna()

    dates = returns.index.tolist()
    n_days = len(dates)

    portfolio_value = 1_000_000.0
    current_weights = dict(target_weights)

    portfolio_values = [portfolio_value]
    weights_history = [dict(current_weights)]

    for i in range(1, n_days):
        day_return = returns.iloc[i]
        weighted_return = sum(current_weights.get(t, 0.0) * day_return.get(t, 0.0) for t in tickers)
        portfolio_value *= (1 + weighted_return)

        new_weights = {}
        for t in tickers:
            old_w = current_weights.get(t, 0.0)
            r = day_return.get(t, 0.0)
            new_w = old_w * (1 + r) / (1 + weighted_return) if (1 + weighted_return) != 0 else old_w
            new_weights[t] = new_w

        current_weights = new_weights
        portfolio_values.append(portfolio_value)
        weights_history.append(dict(current_weights))

    values_series = pd.Series(portfolio_values, index=dates)
    daily_returns = values_series.pct_change().dropna()

    ann_ret = daily_returns.mean() * 252
    ann_vol = daily_returns.std() * np.sqrt(252)
    sharpe_val = (ann_ret - 0.0) / ann_vol if ann_vol > 0 else 0.0
    max_dd = max_drawdown(daily_returns)

    return RebalanceResult(
        dates=[str(d)[:10] for d in dates],
        portfolio_values=portfolio_values,
        weights_history=weights_history,
        turnover_history=[0.0] * n_days,
        total_cost=0.0,
        n_rebalances=0,
        annual_return=ann_ret,
        annual_volatility=ann_vol,
        sharpe=sharpe_val,
        max_drawdown=max_dd,
    )


def compare_strategies(
    returns: pd.DataFrame,
    config: RebalanceConfig,
    cov_method: str = "sample",
) -> pd.DataFrame:
    """Сравнение стратегий: buy-and-hold vs rebalancing.

    Args:
        returns: DataFrame с доходностями.
        config: Параметры ребалансирования.
        cov_method: Метод ковариации.

    Returns:
        DataFrame со сравнением метрик.
    """
    rebal = simulate_rebalancing(returns, config, cov_method=cov_method)
    bh = simulate_buy_and_hold(returns, config.target_weights)

    metrics = {
        "Metric": [
            "Annual Return",
            "Annual Volatility",
            "Sharpe Ratio",
            "Max Drawdown",
            "Total Transaction Cost",
            "Number of Rebalances",
        ],
        "Rebalancing": [
            f"{rebal.annual_return:.2%}",
            f"{rebal.annual_volatility:.2%}",
            f"{rebal.sharpe:.3f}",
            f"{rebal.max_drawdown:.2%}",
            f"{rebal.total_cost:,.0f} RUB",
            str(rebal.n_rebalances),
        ],
        "Buy & Hold": [
            f"{bh.annual_return:.2%}",
            f"{bh.annual_volatility:.2%}",
            f"{bh.sharpe:.3f}",
            f"{bh.max_drawdown:.2%}",
            "0 RUB",
            "0",
        ],
    }

    return pd.DataFrame(metrics)
