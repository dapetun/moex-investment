"""Фильтрация данных: ликвидность, аномалии, волатильность."""

import logging

import pandas as pd

from .config import MAX_DAILY_CHANGE, MIN_TURNOVER

logger = logging.getLogger(__name__)


def separate_prices_and_volumes(
    raw_data: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Разделение сырых данных на цены и объёмы.

    Args:
        raw_data: DataFrame со столбцами [ticker, ticker_VALUE, ...].

    Returns:
        Кортеж (prices, volumes).
    """
    value_cols = [c for c in raw_data.columns if c.endswith("_VALUE")]
    price_cols = [c for c in raw_data.columns if not c.endswith("_VALUE")]

    return raw_data[price_cols], raw_data[value_cols]


def filter_by_turnover(
    prices: pd.DataFrame,
    volumes: pd.DataFrame,
    min_turnover: float = MIN_TURNOVER,
) -> list[str]:
    """Отбор акций по среднему дневному обороту.

    Args:
        prices: DataFrame с ценами.
        volumes: DataFrame с объёмами (столбцы ticker_VALUE).
        min_turnover: Минимальный средний дневной оборот.

    Returns:
        Список тикеров, прошедших фильтр.
    """
    avg_turnover = volumes.mean()
    liquid = avg_turnover[avg_turnover > min_turnover].index
    tickers = [x.replace("_VALUE", "") for x in liquid]

    logger.info(
        "Turnover filter: %d -> %d stocks (min_turnover=%.0f)",
        len(prices.columns), len(tickers), min_turnover,
    )
    return tickers


def compute_returns(prices: pd.DataFrame) -> pd.DataFrame:
    """Расчёт дневных доходностей через pct_change.

    Args:
        prices: DataFrame с ценами закрытия.

    Returns:
        DataFrame с доходностями (первая строка удалена).
    """
    return prices.pct_change().dropna()


def remove_anomalies(
    returns: pd.DataFrame,
    max_change: float = MAX_DAILY_CHANGE,
) -> pd.DataFrame:
    """Удаление дней с аномальными скачками (> max_change).

    Args:
        returns: DataFrame с доходностями.
        max_change: Максимально допустимое изменение за день (0.8 = 80%).

    Returns:
        DataFrame без аномальных дней.
    """
    initial_rows = len(returns)
    returns = returns[(returns.abs() < max_change).all(axis=1)]
    removed = initial_rows - len(returns)
    if removed > 0:
        logger.info("Removed %d anomalous days (threshold=%.0f%%)", removed, max_change * 100)
    return returns


def remove_zero_volatility(returns: pd.DataFrame) -> pd.DataFrame:
    """Удаление акций с нулевой волатильностью.

    Args:
        returns: DataFrame с доходностями.

    Returns:
        DataFrame без акций с нулевой волатильностью.
    """
    volatility = returns.std()
    valid = volatility[volatility > 0].index
    removed = len(returns.columns) - len(valid)
    if removed > 0:
        logger.info("Removed %d zero-volatility stocks", removed)
    return returns[valid]


def prepare_returns(
    raw_data: pd.DataFrame,
    min_turnover: float = MIN_TURNOVER,
    max_change: float = MAX_DAILY_CHANGE,
) -> tuple[pd.DataFrame, list[str]]:
    """Полный пайплайн подготовки доходностей.

    Args:
        raw_data: Сырые данные с ценами и объёмами.
        min_turnover: Минимальный оборот для фильтрации ликвидности.
        max_change: Максимальное изменение за день.

    Returns:
        Кортеж (returns, valid_tickers).
    """
    prices, volumes = separate_prices_and_volumes(raw_data)
    liquid_tickers = filter_by_turnover(prices, volumes, min_turnover)

    prices = prices[liquid_tickers]

    returns = compute_returns(prices)
    returns = remove_anomalies(returns, max_change)
    returns = remove_zero_volatility(returns)

    valid_tickers = returns.columns.tolist()
    logger.info("Final: %d stocks, %d periods", len(valid_tickers), len(returns))

    return returns, valid_tickers
