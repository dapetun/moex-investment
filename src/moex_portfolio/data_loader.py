"""Загрузка данных с MOEX ISS API."""

import logging
import time
from datetime import date, datetime, timedelta
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
from .defaults import DEFAULTS

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
            except (requests.ConnectionError, requests.Timeout):
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


def get_dividend_yields(
    tickers: list[str],
    prices: pd.DataFrame,
    lookback_days: int = 365,
) -> pd.Series:
    """Расчёт реальной дивидендной доходности по данным MOEX ISS.

    Параллельно загружает дивиденды для всех тикеров через aiohttp.

    Args:
        tickers: Список тикеров.
        prices: DataFrame с ценами закрытия (столбцы = тикеры).
        lookback_days: Период для суммирования дивидендов (по умолчанию 365).

    Returns:
        Series с дивидендной доходностью по каждому тикеру.
    """
    import asyncio

    import aiohttp

    now = pd.Timestamp.now()
    cutoff = now - timedelta(days=lookback_days)
    valid_tickers = [t for t in tickers if t in prices.columns]

    async def _fetch_one(session: aiohttp.ClientSession, ticker: str) -> tuple[str, float]:
        current_price = prices[ticker].iloc[-1]
        if pd.isna(current_price) or current_price <= 0:
            return ticker, 0.0

        url = f"{MOEX_ISS_BASE}/securities/{ticker}/dividends.json"
        try:
            async with session.get(url, params={"iss.meta": "off"}, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                if resp.status != 200:
                    return ticker, 0.0
                data = await resp.json()
        except Exception:
            return ticker, 0.0

        divs_data = data.get("dividends", {}).get("data", [])
        if not divs_data:
            return ticker, 0.0

        cols = data.get("dividends", {}).get("columns", [])
        if "registryclosedate" not in cols or "value" not in cols:
            return ticker, 0.0

        df = pd.DataFrame(divs_data, columns=cols)
        df["registryclosedate"] = pd.to_datetime(df["registryclosedate"], errors="coerce")
        df = df.dropna(subset=["registryclosedate", "value"])
        recent = df[df["registryclosedate"] >= cutoff]
        if recent.empty:
            return ticker, 0.0

        total_divs = recent["value"].sum()
        dy = total_divs / current_price
        return ticker, dy

    async def _fetch_all() -> dict[str, float]:
        sem = asyncio.Semaphore(10)

        async def _limited(session: aiohttp.ClientSession, ticker: str) -> tuple[str, float]:
            async with sem:
                return await _fetch_one(session, ticker)

        async with aiohttp.ClientSession() as session:
            tasks = [_limited(session, t) for t in valid_tickers]
            results = await asyncio.gather(*tasks)
        return dict(results)

    try:
        yields_dict = asyncio.run(_fetch_all())
    except RuntimeError:
        loop = asyncio.new_event_loop()
        yields_dict = loop.run_until_complete(_fetch_all())
        loop.close()

    for t in tickers:
        if t not in yields_dict:
            yields_dict[t] = 0.0

    dy_series = pd.Series(yields_dict)
    nonzero = (dy_series > 0).sum()
    logger.info(
        "Dividend yields: %d/%d stocks have positive yield",
        nonzero, len(valid_tickers),
    )
    return dy_series


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

    import aiohttp

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
            except (aiohttp.ClientError, asyncio.TimeoutError, ValueError) as e:
                retries += 1
                wait = RETRY_BACKOFF ** retries
                logger.debug("%s — request error (attempt %d/%d): %s", ticker, retries, MAX_RETRIES, e)
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


def check_cache_freshness(
    cache_path: Path | None = None,
    max_age_hours: int | None = None,
) -> dict:
    """Проверка актуальности кэшированных данных.

    Args:
        cache_path: Путь к CSV-кэшу. Если None — проверяет price_data.csv.
        max_age_hours: Максимальный возраст кэша в часах. Если None — из defaults.

    Returns:
        Словарь с информацией о кэше:
        - exists: bool — существует ли файл
        - path: str — путь к файлу
        - last_modified: str — дата последнего изменения (ISO)
        - age_hours: float — возраст в часах
        - is_fresh: bool — актуален ли кэш
        - max_age_hours: int — максимально допустимый возраст
        - last_data_date: str — последняя дата данных в CSV (или None)
        - rows: int — количество строк
        - columns: int — количество столбцов
    """
    if cache_path is None:
        cache_path = DATA_DIR / "price_data.csv"
    if max_age_hours is None:
        max_age_hours = DEFAULTS.cache_max_age_hours

    result = {
        "exists": cache_path.exists(),
        "path": str(cache_path),
        "last_modified": None,
        "age_hours": None,
        "is_fresh": False,
        "max_age_hours": max_age_hours,
        "last_data_date": None,
        "rows": 0,
        "columns": 0,
    }

    if not cache_path.exists():
        return result

    mtime = datetime.fromtimestamp(cache_path.stat().st_mtime)
    age = datetime.now() - mtime
    age_hours = age.total_seconds() / 3600

    result["last_modified"] = mtime.isoformat()
    result["age_hours"] = round(age_hours, 1)
    result["is_fresh"] = age_hours < max_age_hours

    try:
        df = pd.read_csv(cache_path, sep=";", index_col="TRADEDATE", nrows=0)
        result["columns"] = len(df.columns)
        full_df = pd.read_csv(cache_path, sep=";", index_col="TRADEDATE")
        result["rows"] = len(full_df)
        if len(full_df) > 0:
            result["last_data_date"] = str(full_df.index[-1])
    except (pd.errors.ParserError, OSError, ValueError) as e:
        logger.warning("Failed to read cache metadata: %s", e)

    return result


def auto_update_cache(
    tickers: list[str] | None = None,
    end_date: str | date = END_DATE,
    force: bool = False,
) -> tuple[pd.DataFrame, dict]:
    """Автоматическое обновление кэша: загружает данные только если кэш устарел.

    Args:
        tickers: Список тикеров. Если None — загружает все.
        end_date: Конечная дата.
        force: Принудительная перезагрузка (игнорировать кэш).

    Returns:
        Кортеж (DataFrame с данными, info dict с результатом обновления).
    """
    cache_info = check_cache_freshness()

    if force:
        logger.info("Force refresh: ignoring cache")
        data = load_all_data_async(tickers=tickers, end_date=end_date, use_cache=False)
        new_info = check_cache_freshness()
        return data, {"action": "force_refresh", "cache": new_info}

    if not cache_info["exists"]:
        logger.info("No cache found, downloading all data")
        data = load_all_data_async(tickers=tickers, end_date=end_date, use_cache=False)
        new_info = check_cache_freshness()
        return data, {"action": "full_download", "cache": new_info}

    if cache_info["is_fresh"]:
        logger.info("Cache is fresh (%.1fh old), loading from cache", cache_info["age_hours"])
        data = load_all_data_async(tickers=tickers, end_date=end_date, use_cache=True)
        return data, {"action": "loaded_from_cache", "cache": cache_info}

    logger.info(
        "Cache is stale (%.1fh old, max %dh), running incremental update",
        cache_info["age_hours"], DEFAULTS.cache_max_age_hours,
    )
    data = incremental_update(tickers=tickers, end_date=end_date, use_cache=True)
    new_info = check_cache_freshness()
    return data, {"action": "incremental_update", "cache": new_info}
