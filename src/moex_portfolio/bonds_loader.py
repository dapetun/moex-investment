"""Загрузчик данных облигаций с MOEX ISS.

Загружает ОФЗ (государственные) и корпоративные облигации.
MOEX ISS API: engine=stock, market=bonds
"""

import logging
import time
from datetime import date

import pandas as pd
import requests

from .config import MOEX_ISS_BASE, REQUEST_DELAY

logger = logging.getLogger(__name__)


def get_bond_list() -> pd.DataFrame:
    """Получение списка всех облигаций с MOEX.

    Returns:
        DataFrame с информацией об облигациях.
    """
    url = f"{MOEX_ISS_BASE}/engines/stock/markets/bonds/boards/TQOB/securities.json"
    params = {"iss.meta": "off", "iss.only": "securities"}

    try:
        resp = requests.get(url, params=params, timeout=30)
        if resp.status_code != 200:
            logger.warning("Failed to fetch bond list: %d", resp.status_code)
            return pd.DataFrame()

        data = resp.json()
        rows = data.get("securities", {}).get("data", [])
        cols = data.get("securities", {}).get("columns", [])

        df = pd.DataFrame(rows, columns=cols)
        logger.info("Found %d bonds on MOEX", len(df))
        return df

    except Exception as e:
        logger.warning("Bond list fetch error: %s", e)
        return pd.DataFrame()


def get_ofz_list() -> pd.DataFrame:
    """Отбор только ОФЗ (государственные облигации).

    ОФЗ имеют тикеры, начинающиеся на 'SU'.

    Returns:
        DataFrame с ОФЗ.
    """
    all_bonds = get_bond_list()
    if all_bonds.empty:
        return all_bonds

    if "SECID" in all_bonds.columns:
        ofz = all_bonds[all_bonds["SECID"].str.startswith("SU", na=False)]
        logger.info("Found %d OFZ bonds", len(ofz))
        return ofz

    return pd.DataFrame()


def get_bond_market_data(
    market_date: date | None = None,
) -> pd.DataFrame:
    """Рыночные данные по облигациям: цена, доходность, купон.

    Args:
        market_date: Дата (по умолчанию сегодня).

    Returns:
        DataFrame с рыночными данными.
    """
    if market_date is None:
        market_date = date.today()

    date_str = market_date.strftime("%Y-%m-%d")
    url = f"{MOEX_ISS_BASE}/engines/stock/markets/bonds/boards/TQOB/securities.json"
    params = {
        "iss.meta": "off",
        "iss.only": "marketdata",
        "date": date_str,
    }

    try:
        resp = requests.get(url, params=params, timeout=30)
        if resp.status_code != 200:
            logger.warning("Failed to fetch bond market data: %d", resp.status_code)
            return pd.DataFrame()

        data = resp.json()
        rows = data.get("marketdata", {}).get("data", [])
        cols = data.get("marketdata", {}).get("columns", [])

        df = pd.DataFrame(rows, columns=cols)
        logger.info("Bond market data: %d rows", len(df))
        return df

    except Exception as e:
        logger.warning("Bond market data error: %s", e)
        return pd.DataFrame()


def get_bond_history(
    ticker: str,
    start_date: date,
    end_date: date | None = None,
    delay: float = REQUEST_DELAY,
) -> pd.DataFrame:
    """Исторические данные по облигации.

    Args:
        ticker: Тикер облигации (напр. 'SU26238RMFS0').
        start_date: Дата начала.
        end_date: Дата окончания (по умолчанию сегодня).
        delay: Задержка между запросами.

    Returns:
        DataFrame с историей цен.
    """
    if end_date is None:
        end_date = date.today()

    url = f"{MOEX_ISS_BASE}/engines/stock/markets/bonds/boards/TQOB/securities/{ticker}/candles.json"
    params = {
        "iss.meta": "off",
        "from": start_date.strftime("%Y-%m-%d"),
        "till": end_date.strftime("%Y-%m-%d"),
        "interval": "24",
    }

    try:
        resp = requests.get(url, params=params, timeout=15)
        time.sleep(delay)

        if resp.status_code != 200:
            logger.warning("Failed to fetch history for %s: %d", ticker, resp.status_code)
            return pd.DataFrame()

        data = resp.json()
        rows = data.get("candles", {}).get("data", [])
        cols = data.get("candles", {}).get("columns", [])

        if not rows:
            return pd.DataFrame()

        df = pd.DataFrame(rows, columns=cols)
        if "begin" in df.columns:
            df["date"] = pd.to_datetime(df["begin"]).dt.date
            df = df.set_index("date")

        return df

    except Exception as e:
        logger.warning("History fetch error for %s: %s", ticker, e)
        return pd.DataFrame()


def get_coupon_info(ticker: str, delay: float = REQUEST_DELAY) -> dict:
    """Получение информации о купонах облигации.

    Args:
        ticker: Тикер облигации.
        delay: Задержка.

    Returns:
        Словарь с купонной информацией.
    """
    url = f"{MOEX_ISS_BASE}/securities/{ticker}/bondization.json"
    params = {"iss.meta": "off"}

    try:
        resp = requests.get(url, params=params, timeout=15)
        time.sleep(delay)

        if resp.status_code != 200:
            return {}

        data = resp.json()
        bondization = data.get("bondization", {}).get("data", [])
        cols = data.get("bondization", {}).get("columns", [])

        if bondization and cols:
            return {"columns": cols, "data": bondization}

        return {}

    except Exception:
        return {}


def load_all_bonds(
    use_cache: bool = True,
    cache_path: str | None = None,
) -> pd.DataFrame:
    """Загрузка рыночных данных по всем облигациям.

    Args:
        use_cache: Использовать кэш.
        cache_path: Путь к файлу кэша.

    Returns:
        DataFrame с рыночными данными.
    """
    if cache_path is None:
        from .config import DATA_DIR
        cache_path = str(DATA_DIR / "bonds_data.csv")

    if use_cache:
        try:
            df = pd.read_csv(cache_path, index_col=0, sep=";")
            logger.info("Loaded bonds from cache: %d rows", len(df))
            return df
        except FileNotFoundError:
            pass

    df = get_bond_market_data()
    if not df.empty and "SECID" in df.columns:
        df.to_csv(cache_path, sep=";")
        logger.info("Saved bonds cache: %d rows", len(df))

    return df


def parse_bond_params(
    market_data: pd.DataFrame,
) -> pd.DataFrame:
    """Парсинг ключевых параметров облигаций из рыночных данных.

    Извлекает: номинал, цену, текущую доходность, купон, дату погашения.

    Args:
        market_data: Сырые рыночные данные.

    Returns:
        DataFrame с распарсенными параметрами.
    """
    if market_data.empty:
        return pd.DataFrame()

    result = pd.DataFrame()
    result["ticker"] = market_data.get("SECID", "")
    result["close"] = pd.to_numeric(market_data.get("CLOSE"), errors="coerce")
    result["yield_close"] = pd.to_numeric(market_data.get("YIELDTOOFFER"), errors="coerce")
    result["coupon"] = pd.to_numeric(market_data.get("COUPONVALUE"), errors="coerce")
    result["facevalue"] = pd.to_numeric(market_data.get("FACEVALUE"), errors="coerce")
    result["couponperiod"] = pd.to_numeric(market_data.get("COUPONPERIOD"), errors="coerce")
    result["prev_wa_price"] = pd.to_numeric(market_data.get("PREVWAPRICE"), errors="coerce")
    result["lotsize"] = pd.to_numeric(market_data.get("LOTSIZE"), errors="coerce")

    for col in ["MATDATE", "COUPONDATE", "EARLYREPAYMENTDATE"]:
        if col in market_data.columns:
            result[col.lower()] = market_data[col]

    result = result.dropna(subset=["ticker"])

    return result
