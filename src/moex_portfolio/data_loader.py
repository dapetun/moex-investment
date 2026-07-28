"""Загрузка данных с MOEX ISS API."""

import logging
import time
from datetime import date
from pathlib import Path

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
