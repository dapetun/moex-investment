"""Модели риска: сжатие ковариации, EWMA, бета."""

import logging

import numpy as np
import pandas as pd
from sklearn.covariance import LedoitWolf

logger = logging.getLogger(__name__)


def ledoit_wolf_covariance(returns: pd.DataFrame) -> pd.DataFrame:
    """Ковариационная матрица с Ledoit-Wolf сжатием.

    Сжатие (shrinkage) стабилизирует оценку ковариации,
    особенно когда число активов сравнимо с числом наблюдений.

    Args:
        returns: DataFrame с доходностями (столбцы = активы).

    Returns:
        Сжатая ковариационная матрица (DataFrame).
    """
    lw = LedoitWolf().fit(returns.dropna())
    cov = pd.DataFrame(
        lw.covariance_,
        index=returns.columns,
        columns=returns.columns,
    )
    logger.info(
        "Ledoit-Wolf shrinkage: alpha=%.4f", lw.shrinkage_
    )
    return cov


def ewma_covariance(
    returns: pd.DataFrame,
    span: int = 60,
) -> pd.DataFrame:
    """EWMA ковариационная матрица (экспоненциально взвешенная).

    Более近期的数据获得 больший вес.
    Хорошо подходит для нестационарных данных.

    Args:
        returns: DataFrame с доходностями.
        span: Параметр сглаживания (чем меньше, тем быстрее забывает).

    Returns:
        EWMA ковариационная матрица (DataFrame).
    """
    cov = returns.ewm(span=span).cov()
    # Берём последний снимок ковариации
    last_date = returns.index[-1]
    return cov.loc[last_date]


def compute_beta(
    returns: pd.DataFrame,
    market_returns: pd.Series,
) -> pd.Series:
    """Расчёт беты каждого актива относительно рынка.

    Beta > 1: актив более волатилен, чем рынок.
    Beta < 1: актив менее волатилен.
    Beta < 0: актив движется против рынка.

    Args:
        returns: DataFrame с доходностями активов.
        market_returns: Series с доходностями рынка (бенчмарка).

    Returns:
        Series с бетами для каждого актива.
    """
    # Выравниваем индексы
    common_idx = returns.index.intersection(market_returns.index)
    r = returns.loc[common_idx]
    m = market_returns.loc[common_idx]

    # Считаем ковариацию каждого актива с рынком
    cov_rm = r.apply(lambda col: col.cov(m))
    var_m = m.var()

    if var_m == 0:
        return pd.Series(0.0, index=returns.columns)

    beta = cov_rm / var_m
    logger.info("Beta computed for %d assets", len(beta))
    return beta


def compute_alpha(
    returns: pd.DataFrame,
    market_returns: pd.Series,
    risk_free_rate: float = 0.0,
) -> pd.Series:
    """Jensen's Alpha для каждого актива.

    Alpha > 0: актив переформировал рынок (после корректировки на риск).
    Alpha < 0: актив недоперформировал.

    Args:
        returns: DataFrame с доходностями активов.
        market_returns: Series с доходностями рынка.
        risk_free_rate: Безрисковая ставка (годовая).

    Returns:
        Series с альфами для каждого актива (годовая).
    """
    daily_rf = risk_free_rate / 252
    beta = compute_beta(returns, market_returns)

    excess_returns = returns.mean() - daily_rf
    market_excess = market_returns.mean() - daily_rf

    alpha = excess_returns - beta * market_excess
    return alpha * 252  # Годовая альфа


def covariance_matrix(
    returns: pd.DataFrame,
    method: str = "sample",
    ewma_span: int = 60,
) -> pd.DataFrame:
    """Универсальное вычисление ковариационной матрицы.

    Args:
        returns: DataFrame с доходностями.
        method: 'sample', 'ledoit_wolf', или 'ewma'.
        ewma_span: Параметр сглаживания для EWMA.

    Returns:
        Ковариационная матрица.
    """
    if method == "ledoit_wolf":
        return ledoit_wolf_covariance(returns)
    elif method == "ewma":
        return ewma_covariance(returns, span=ewma_span)
    else:
        return returns.cov()
