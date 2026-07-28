"""Загрузка данных с MOEX ISS API."""

import logging
import time
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd
import requests
from tqdm import tqdm

from .config import (
    DATA_DIR,
    END_DATE,
    MAX_RETRIES,
    MIN_OBSERVATIONS,
    MOEX_ISS_BASE,
    REQUEST_DELAY,
    RETRY_BACKOFF,
    START_DATE,
)

logger = logging.getLogger(__name__)


def get_all_shares() -> list[str]:
    """Загрузка списка всех обыкновенных акций MOEX через ISS API.

    Returns:
        Список тикеров обыкновенных акций (SECTYPE == '1').
    """
    url = f"{MOEX_ISS_BASE}/engines/stock/markets/shares/securities.json"
    params = {
        "iss.meta": "off",
        "iss.only": "securities",
        "securities.columns": "SECID,SECNAME,SECTYPE",
    }

    response = requests.get(url, params=params, timeout=30)
    response.raise_for_status()
    data = response.json()

    df = pd.DataFrame(
        data["securities"]["data"], columns=data["securities"]["columns"]
    )

    # Оставляем только обыкновенные акции
    df = df[df["SECTYPE"] == "1"]
    return df["SECID"].unique().tolist()


def get_price_history(
    ticker: str,
    start: str | date = START_DATE,
    end: str | date = END_DATE,
) -> pd.DataFrame | None:
    """Загрузка истории цен для одного тикера с пагинацией и retry.

    Args:
        ticker: Тикер акции.
        start: Начальная дата.
        end: Конечная дата.

    Returns:
        DataFrame с колонками [ticker, ticker_VALUE] и индексом TRADEDATE,
        или None если данных нет.
    """
    url = f"{MOEX_ISS_BASE}/history/engines/stock/markets/shares/securities/{ticker}.json"
    all_data: list[list] = []
    start_row = 0

    session = requests.Session()

    while True:
        params = {
            "from": str(start),
            "till": str(end),
            "iss.meta": "off",
            "history.columns": "TRADEDATE,CLOSE,VALUE",
            "start": start_row,
        }

        retries = 0
        data = None
        while retries < MAX_RETRIES:
            try:
                response = session.get(url, params=params, timeout=15)
                data = response.json()
                break
            except (requests.ConnectionError, requests.Timeout) as e:
                retries += 1
                wait = RETRY_BACKOFF ** retries
                logger.warning(
                    "%s — connection error (attempt %d/%d), retry in %ds",
                    ticker, retries, MAX_RETRIES, wait,
                )
                time.sleep(wait)
        else:
            logger.error("%s — all retries exhausted, skipping", ticker)
            return None

        if "history" not in data:
            break

        rows = data["history"]["data"]
        if not rows:
            break

        all_data.extend(rows)

        if len(rows) < 100:
            break

        start_row += 100
        time.sleep(REQUEST_DELAY)

    if not all_data:
        return None

    df = pd.DataFrame(all_data, columns=["TRADEDATE", "CLOSE", "VALUE"])
    df["TRADEDATE"] = pd.to_datetime(df["TRADEDATE"])
    df = df.drop_duplicates(subset="TRADEDATE")
    df.set_index("TRADEDATE", inplace=True)
    df = df[~df.index.duplicated(keep="first")]
    df = df.rename(columns={"CLOSE": ticker, "VALUE": f"{ticker}_VALUE"})

    return df


def load_all_data(
    tickers: list[str] | None = None,
    start_date: str | date = START_DATE,
    end_date: str | date = END_DATE,
    use_cache: bool = True,
) -> pd.DataFrame:
    """Загрузка данных для списка тикеров с кэшированием в CSV.

    Args:
        tickers: Список тикеров. Если None — загружает все акции MOEX.
        start_date: Начальная дата.
        end_date: Конечная дата.
        use_cache: Использовать ли CSV-кэш.

    Returns:
        DataFrame с ценами и оборотами.
    """
    cache_path = DATA_DIR / "price_data.csv"

    if use_cache and cache_path.exists():
        logger.info("Loading from cache: %s", cache_path)
        return pd.read_csv(cache_path, sep=";", index_col="TRADEDATE")

    if tickers is None:
        tickers = get_all_shares()
        logger.info("Found %d tickers on MOEX", len(tickers))

    DATA_DIR.mkdir(parents=True, exist_ok=True)

    all_prices: list[pd.DataFrame] = []

    for ticker in tqdm(tickers, desc="Loading tickers"):
        df = get_price_history(ticker, start_date, end_date)

        if df is None:
            tqdm.write(f"{ticker} — no data")
        elif len(df) < MIN_OBSERVATIONS:
            tqdm.write(f"{ticker} — too few observations ({len(df)})")
        else:
            all_prices.append(df)

    prices = pd.concat(all_prices, axis=1)

    # Удаляем столбцы с >20% пропусков
    prices = prices.dropna(axis=1, thresh=int(len(prices) * 0.8))

    # Заполняем пропуски: forward fill + backward fill
    prices = prices.ffill().bfill()

    # Удаляем столбцы, где всё NaN
    prices = prices.dropna(axis=1, how="all")

    logger.info(
        "Loaded %d stocks, %d periods", prices.shape[1], prices.shape[0]
    )

    # Сохраняем кэш
    prices.to_csv(cache_path, sep=";")

    return prices


def get_dividends(ticker: str) -> pd.DataFrame | None:
    """Загрузка дивидендов тикера через MOEX ISS.

    Args:
        ticker: Тикер акции.

    Returns:
        DataFrame с колонками [ticker, registryclosedate, value] или None.
    """
    url = f"{MOEX_ISS_BASE}/securities/{ticker}/dividends.json"
    params = {"iss.meta": "off"}

    try:
        response = requests.get(url, params=params, timeout=15)
        response.raise_for_status()
        data = response.json()
    except (requests.RequestException, ValueError):
        return None

    if "dividends" not in data or not data["dividends"]["data"]:
        return None

    df = pd.DataFrame(
        data["dividends"]["data"],
        columns=data["dividends"]["columns"],
    )

    if df.empty:
        return None

    # registryclosedate — дата закрытия реестра
    # value — размер дивиденда на акцию
    if "registryclosedate" in df.columns and "value" in df.columns:
        df["registryclosedate"] = pd.to_datetime(df["registryclosedate"])
        df = df[["registryclosedate", "value"]].dropna()
        df = df.sort_values("registryclosedate")
        return df

    return None


def adjust_prices_for_dividends(
    prices: pd.DataFrame,
    tickers: list[str] | None = None,
    start_date: str | date = START_DATE,
) -> pd.DataFrame:
    """Корректировка цен на дивиденды (ex-dividend adjustment).

    Для каждого тикера:
    - Загружает дивидендный календарь
    - Находит ex-dividend даты (registryclosedate)
    - Для каждой ex-div даты умножает ВСЕ цены ДО этой даты
      на множитель (close + dividend) / close

    Args:
        prices: DataFrame с ценами закрытия (столбцы = тикеры).
        tickers: Список тикеров для корректировки. Если None — все.
        start_date: Начальная дата (для фильтрации дивидендов).

    Returns:
        DataFrame с скорректированными ценами.
    """
    if tickers is None:
        tickers = [c for c in prices.columns if not c.endswith("_VALUE")]

    adjusted = prices.copy()
    adjusted_prices_count = 0

    for ticker in tqdm(tickers, desc="Dividend adjustment"):
        if ticker not in adjusted.columns:
            continue

        divs = get_dividends(ticker)
        if divs is None or divs.empty:
            continue

        # Фильтруем по дате
        if isinstance(start_date, str):
            start_date = date.fromisoformat(start_date)
        divs = divs[divs["registryclosedate"] >= pd.Timestamp(start_date)]

        if divs.empty:
            continue

        # Строим накопленный множитель (от конца к началу)
        prices_col = adjusted[ticker].dropna()
        if prices_col.empty:
            continue

        adjustment_factor = 1.0
        for _, row in divs.iterrows():
            ex_date = row["registryclosedate"]
            dividend = row["value"]

            if dividend <= 0:
                continue

            # Находим ближайшую дату торгов до ex-date
            mask = prices_col.index < ex_date
            if not mask.any():
                continue

            close_before = prices_col[mask].iloc[-1]
            if close_before > 0:
                adjustment_factor *= (close_before + dividend) / close_before

        if adjustment_factor != 1.0:
            mask = adjusted.index < divs["registryclosedate"].max()
            adjusted.loc[mask, ticker] = adjusted.loc[mask, ticker] * adjustment_factor
            adjusted_prices_count += 1
            logger.info(
                "%s: adjusted prices before %s, factor=%.4f",
                ticker, divs["registryclosedate"].max().date(), adjustment_factor,
            )

    logger.info("Adjusted %d tickers for dividends", adjusted_prices_count)
    return adjusted


async def _fetch_ticker_async(
    session,
    ticker: str,
    start: str | date,
    end: str | date,
) -> pd.DataFrame | None:
    """Асинхронная загрузка одного тикера."""
    import asyncio

    url = f"{MOEX_ISS_BASE}/history/engines/stock/markets/shares/securities/{ticker}.json"
    all_data: list[list] = []
    start_row = 0

    while True:
        params = {
            "from": str(start),
            "till": str(end),
            "iss.meta": "off",
            "history.columns": "TRADEDATE,CLOSE,VALUE",
            "start": start_row,
        }

        retries = 0
        data = None
        while retries < MAX_RETRIES:
            try:
                async with session.get(url, params=params, timeout=15) as response:
                    data = await response.json()
                    break
            except Exception:
                retries += 1
                wait = RETRY_BACKOFF ** retries
                await asyncio.sleep(wait)
        else:
            return None

        if "history" not in data:
            break

        rows = data["history"]["data"]
        if not rows:
            break

        all_data.extend(rows)

        if len(rows) < 100:
            break

        start_row += 100
        await asyncio.sleep(REQUEST_DELAY)

    if not all_data:
        return None

    df = pd.DataFrame(all_data, columns=["TRADEDATE", "CLOSE", "VALUE"])
    df["TRADEDATE"] = pd.to_datetime(df["TRADEDATE"])
    df = df.drop_duplicates(subset="TRADEDATE")
    df.set_index("TRADEDATE", inplace=True)
    df = df[~df.index.duplicated(keep="first")]
    df = df.rename(columns={"CLOSE": ticker, "VALUE": f"{ticker}_VALUE"})
    return df


async def _load_all_async(
    tickers: list[str],
    start_date: str | date,
    end_date: str | date,
    max_concurrent: int = 10,
) -> list[pd.DataFrame]:
    """Асинхронная загрузка списка тикеров с ограничением параллелизма."""
    import asyncio

    import aiohttp

    semaphore = asyncio.Semaphore(max_concurrent)
    results = []

    async with aiohttp.ClientSession() as session:
        async def _limited_fetch(ticker):
            async with semaphore:
                return await _fetch_ticker_async(session, ticker, start_date, end_date)

        tasks = [_limited_fetch(t) for t in tickers]
        for coro in asyncio.as_completed(tasks):
            result = await coro
            if result is not None:
                results.append(result)

    return results


def load_all_data_async(
    tickers: list[str] | None = None,
    start_date: str | date = START_DATE,
    end_date: str | date = END_DATE,
    use_cache: bool = True,
    max_concurrent: int = 10,
) -> pd.DataFrame:
    """Асинхронная загрузка данных для списка тикеров.

    В ~10-50 раз быстрее синхронной версии за счёт параллельных запросов.

    Args:
        tickers: Список тикеров. Если None — загружает все акции MOEX.
        start_date: Начальная дата.
        end_date: Конечная дата.
        use_cache: Использовать ли CSV-кэш.
        max_concurrent: Максимальное число параллельных запросов.

    Returns:
        DataFrame с ценами и оборотами.
    """
    import asyncio

    cache_path = DATA_DIR / "price_data.csv"

    if use_cache and cache_path.exists():
        logger.info("Loading from cache: %s", cache_path)
        return pd.read_csv(cache_path, sep=";", index_col="TRADEDATE")

    if tickers is None:
        tickers = get_all_shares()
        logger.info("Found %d tickers on MOEX", len(tickers))

    DATA_DIR.mkdir(parents=True, exist_ok=True)

    all_prices = asyncio.run(
        _load_all_async(tickers, start_date, end_date, max_concurrent)
    )

    if not all_prices:
        logger.error("No data loaded")
        return pd.DataFrame()

    prices = pd.concat(all_prices, axis=1)
    prices = prices.dropna(axis=1, thresh=int(len(prices) * 0.8))
    prices = prices.ffill().bfill()
    prices = prices.dropna(axis=1, how="all")

    logger.info("Loaded %d stocks, %d periods", prices.shape[1], prices.shape[0])
    prices.to_csv(cache_path, sep=";")

    return prices


def incremental_update(
    tickers: list[str] | None = None,
    end_date: str | date = END_DATE,
    use_cache: bool = True,
) -> pd.DataFrame:
    """Инкрементальное обновление кэша: загружает только новые данные.

    Если кэш существует, определяет последнюю дату и загружает данные
    только с этой даты, дописывая к существующему файлу.

    Args:
        tickers: Список тикеров. Если None — загружает все.
        end_date: Конечная дата.
        use_cache: Использовать ли существующий кэш.

    Returns:
        Обновлённый DataFrame.
    """
    cache_path = DATA_DIR / "price_data.csv"

    if use_cache and cache_path.exists():
        existing = pd.read_csv(cache_path, sep=";", index_col="TRADEDATE")
        existing.index = pd.to_datetime(existing.index)
        last_date = existing.index.max()
        logger.info("Incremental update from %s", last_date.date())

        # Определяем тикеры для обновления
        if tickers is None:
            tickers = get_all_shares()

        # Загружаем данные с последней даты
        import asyncio
        new_data = asyncio.run(
            _load_all_async(tickers, last_date + pd.Timedelta(days=1), end_date)
        )

        if new_data:
            new_prices = pd.concat(new_data, axis=1)
            # Объединяем: перезаписываем существующие столбцы, дописываем новые
            combined = existing.combine_first(new_prices)
            combined = combined.ffill().bfill()
            combined.to_csv(cache_path, sep=";")
            logger.info(
                "Incremental update: %d stocks, %d periods (was %d)",
                combined.shape[1], combined.shape[0], existing.shape[0],
            )
            return combined

        logger.info("No new data to update")
        return existing

    return load_all_data_async(
        tickers=tickers, end_date=end_date, use_cache=False,
    )
