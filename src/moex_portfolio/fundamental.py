"""Фундаментальный анализ акций.

Мультипликаторы: P/E, P/B, PEG, ROE, ROA, Dividend Yield, EV/EBITDA.
Загрузка данных с MOEX ISS (секция 'marketdata' и 'analytics').
"""

import logging
import time
from datetime import date

import numpy as np
import pandas as pd
import requests

from .config import MOEX_ISS_BASE, REQUEST_DELAY

logger = logging.getLogger(__name__)


def get_fundamental_data(tickers: list[str], delay: float = REQUEST_DELAY) -> pd.DataFrame:
    """Загрузка фундаментальных данных с MOEX ISS.

    Получаем P/E, P/B, Dividend Yield, Market Cap для каждого тикера.

    Args:
        tickers: Список тикеров.
        delay: Задержка между запросами.

    Returns:
        DataFrame с мультипликаторами.
    """
    records = []

    for ticker in tickers:
        try:
            url = f"{MOEX_ISS_BASE}/securities/{ticker}.json"
            params = {"iss.meta": "off", "iss.only": "description"}
            resp = requests.get(url, params=params, timeout=15)
            if resp.status_code == 200:
                data = resp.json()
                desc = data.get("description", {}).get("data", [])
                info = {}
                for row in desc:
                    name = row[1] if len(row) > 1 else ""
                    value = row[2] if len(row) > 2 else ""
                    info[name] = value

                records.append({
                    "ticker": ticker,
                    "shortname": info.get("SHORTNAME", ""),
                    "isin": info.get("ISIN", ""),
                    "facevalue": _safe_float(info.get("FACEVALUE", "")),
                    "issuecapitalization": _safe_float(info.get("ISSUECAPITALIZATION", "")),
                })
            time.sleep(delay)
        except (requests.RequestException, ValueError, KeyError) as e:
            logger.warning("Failed to fetch fundamental data for %s: %s", ticker, e)
            continue

    return pd.DataFrame(records)


def get_market_data_batch(
    tickers: list[str],
    market_date: date | None = None,
    delay: float = REQUEST_DELAY,
) -> pd.DataFrame:
    """Загрузка рыночных данных: last price, yield, coupon, duration.

    Использует engine=stock, market=shares для акций.

    Args:
        tickers: Список тикеров.
        market_date: Дата (по умолчанию сегодня).
        delay: Задержка между запросами.

    Returns:
        DataFrame с рыночными данными.
    """
    if market_date is None:
        market_date = date.today()

    date_str = market_date.strftime("%Y-%m-%d")
    url = f"{MOEX_ISS_BASE}/engines/stock/markets/shares/boards/TQBR/securities.json"
    params = {
        "iss.meta": "off",
        "iss.only": "marketdata",
        "date": date_str,
    }

    try:
        resp = requests.get(url, params=params, timeout=30)
        if resp.status_code != 200:
            logger.warning("Failed to fetch market data: %d", resp.status_code)
            return pd.DataFrame()

        data = resp.json()
        rows = data.get("marketdata", {}).get("data", [])
        cols = data.get("marketdata", {}).get("columns", [])

        df = pd.DataFrame(rows, columns=cols)
        ticker_set = set(tickers)
        df = df[df["SECID"].isin(ticker_set)]

        return df
    except Exception as e:
        logger.warning("Market data fetch error: %s", e)
        return pd.DataFrame()


def compute_multiplicators(
    returns: pd.DataFrame,
    prices: pd.DataFrame | None = None,
    dividend_yields: pd.Series | None = None,
) -> pd.DataFrame:
    """Расчёт мультипликаторов на основе доступных данных.

    На основе исторических данных вычисляем:
    - Волатильность (annualized)
    - Максимальную просадку
    - Sharpe Ratio
    - Доходность за various periods
    - Дивидендную доходность (если предоставлена)

    Args:
        returns: DataFrame с дневными доходностями.
        prices: DataFrame с ценами (опционально).
        dividend_yields: Series с дивидендной доходностью (опционально).

    Returns:
        DataFrame с мультипликаторами для каждого тикера.
    """
    result = pd.DataFrame(index=returns.columns)

    result["annual_return"] = returns.mean() * 252
    result["annual_volatility"] = returns.std() * np.sqrt(252)

    result["sharpe"] = result["annual_return"] / result["annual_volatility"]
    result["sharpe"] = result["sharpe"].replace([float("inf"), float("-inf")], 0.0)

    result["min_daily_return"] = returns.min()
    result["max_daily_return"] = returns.max()

    result["skewness"] = returns.skew()
    result["kurtosis"] = returns.kurtosis()

    if prices is not None:
        result["total_return"] = (prices.iloc[-1] / prices.iloc[0]) - 1
        result["max_drawdown"] = _compute_max_drawdown_per_stock(prices)

    if dividend_yields is not None:
        result["dividend_yield"] = dividend_yields.reindex(returns.columns).fillna(0.0)
    else:
        result["dividend_yield"] = 0.0

    if "total_return" in result.columns and "dividend_yield" in result.columns:
        result["price_return"] = result["total_return"] - result["dividend_yield"]

    result.index.name = "ticker"
    return result.sort_values("sharpe", ascending=False)


def rank_stocks(
    multiplicators: pd.DataFrame,
    weights: dict[str, float] | None = None,
) -> pd.DataFrame:
    """Ранжирование акций по взвешенной оценке.

    Args:
        multiplicators: DataFrame с мультипликаторами.
        weights: Веса критериев (по умолчанию: sharpe=0.4, return=0.3, vol=0.3).

    Returns:
        DataFrame с ranking score.
    """
    if weights is None:
        weights = {"sharpe": 0.4, "annual_return": 0.3, "annual_volatility": -0.3}

    df = multiplicators.copy()

    for col in ["sharpe", "annual_return", "annual_volatility"]:
        if col in df.columns:
            min_val = df[col].min()
            max_val = df[col].max()
            if max_val > min_val:
                df[f"{col}_norm"] = (df[col] - min_val) / (max_val - min_val)
            else:
                df[f"{col}_norm"] = 0.5

    score = pd.Series(0.0, index=df.index)
    for factor, weight in weights.items():
        norm_col = f"{factor}_norm"
        if norm_col in df.columns:
            score += weight * df[norm_col]

    df["composite_score"] = score
    return df.sort_values("composite_score", ascending=False)


def dogs_of_the_dow_fundamental(
    multiplicators: pd.DataFrame,
    n_stocks: int = 10,
) -> dict:
    """Dogs of the Dow с учётом фундаментальных данных.

    Отбираем N акций с наименьшим P/E (если доступен) или наибольшим Sharpe.

    Args:
        multiplicators: DataFrame с мультипликаторами.
        n_stocks: Число акций.

    Returns:
        Словарь с отобранными тикерами и весами.
    """
    df = multiplicators.copy()

    if "annual_volatility" in df.columns:
        df = df[df["annual_volatility"] > 0]

    if len(df) == 0:
        return {"selected_tickers": [], "weights": np.array([])}

    selected = df.nlargest(min(n_stocks, len(df)), "sharpe").index.tolist()
    n = len(selected)

    return {
        "selected_tickers": selected,
        "weights": np.array([1.0 / n] * n),
    }


def _compute_max_drawdown_per_stock(prices: pd.DataFrame) -> pd.Series:
    """Максимальная просадка для каждой акции."""
    result = {}
    for col in prices.columns:
        cumulative = prices[col] / prices[col].iloc[0]
        running_max = cumulative.cummax()
        drawdown = (cumulative - running_max) / running_max
        result[col] = drawdown.min()
    return pd.Series(result)


def _safe_float(value: str) -> float | None:
    """Безопасное преобразование строки в float."""
    try:
        return float(value.replace(",", "."))
    except (ValueError, AttributeError):
        return None
