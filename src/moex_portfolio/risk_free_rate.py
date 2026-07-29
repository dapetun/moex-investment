"""Автоматическое получение безрисковой ставки из разных источников.

Источники:
1. Ключевая ставка ЦБ РФ (cbr.ru)
2. Доходность ОФЗ (MOEX RGBI)
3. Ручной ввод пользователя
"""

import logging
from enum import Enum

import pandas as pd
import requests

logger = logging.getLogger(__name__)


class RiskFreeSource(str, Enum):
    """Источники безрисковой ставки."""

    CBR_KEY_RATE = "cbr_key_rate"
    OFZ_YIELD = "ofz_yield"
    MANUAL = "manual"


# ─── Ключевая ставка ЦБ РФ ──────────────────────────────────


def fetch_cbr_key_rate() -> float | None:
    """Текущая ключевая ставка ЦБ РФ через XML API.

    Returns:
        Ключевая ставка в процентах (годовых) или None при ошибке.
    """
    url = "https://www.cbr.ru/DailyInfoWebServ/DailyInfo.asmx"
    # SOAP XML-запрос для получения последней ключевой ставки
    soap_body = f"""<?xml version="1.0" encoding="utf-8"?>
<soap12:Envelope xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
                 xmlns:xsd="http://www.w3.org/2001/XMLSchema"
                 xmlns:soap12="http://www.w3.org/2003/05/soap-envelope">
  <soap12:Body>
    <KeyRate xmlns="http://web.cbr.ru/">
      <from>{pd.Timestamp.now().strftime('%Y-%m-%d')}</from>
      <to>{pd.Timestamp.now().strftime('%Y-%m-%d')}</to>
    </KeyRate>
  </soap12:Body>
</soap12:Envelope>"""

    headers = {
        "Content-Type": "application/soap+xml; charset=utf-8",
    }

    try:
        resp = requests.post(url, data=soap_body, headers=headers, timeout=15)
        resp.raise_for_status()

        # Парсим XML
        import xml.etree.ElementTree as ET

        root = ET.fromstring(resp.text)
        ns = {"soap": "http://www.w3.org/2003/05/soap-envelope",
              "cbr": "http://web.cbr.ru/"}

        rates = []
        for rate_elem in root.findall(".//cbr:KeyRateResult/cbr:d", ns):
            val = rate_elem.find("cbr:Value", ns)
            if val is not None and val.text:
                rates.append(float(val.text.replace(",", ".")))

        if rates:
            rate = rates[-1]  # Последняя ставка
            logger.info("CBR key rate: %.2f%%", rate)
            return rate

        # Fallback: пробуем другой API
        return _fetch_cbr_key_rate_fallback()

    except Exception as e:
        logger.warning("Failed to fetch CBR key rate: %s", e)
        return _fetch_cbr_key_rate_fallback()


def _fetch_cbr_key_rate_fallback() -> float | None:
    """Fallback: ключевая ставка через HTML-таблицу ЦБ."""
    url = "https://www.cbr.ru/hd_base/KeyRate/"
    try:
        resp = requests.get(url, timeout=15)
        resp.raise_for_status()

        import xml.etree.ElementTree as ET
        root = ET.fromstring(resp.text)

        # Ищем таблицу с ключевыми ставками
        for table in root.findall(".//table"):
            rows = table.findall(".//tr")
            for row in rows:
                cells = row.findall(".//td")
                if len(cells) >= 2:
                    val_text = cells[1].text
                    if val_text:
                        return float(val_text.replace(",", ".").strip())

    except Exception as e:
        logger.debug("CBR fallback failed: %s", e)

    return None


# ─── Доходность ОФЗ (через MOEX) ───────────────────────────


def fetch_ofz_yield() -> float | None:
    """Текущая доходность ОФЗ через MOEX ISS.

    Берём доходность OFZ-PD посередине кривой (3-5 лет).
    Доходность ОФЗ — хороший прокси для безрисковой ставки.

    Returns:
        Доходность ОФЗ в процентах (годовых) или None при ошибке.
    """
    url = "https://iss.moex.com/iss/statistics/engines/stock/markets/bonds/bondization.json"
    params = {
        "iss.meta": "off",
        "iss.only": "spectrum",
        "spectrum.columns": "SECID,YIELDTOSELL,YIELDTOBUY",
        "limit": 100,
    }

    try:
        resp = requests.get(url, params=params, timeout=15)
        resp.raise_for_status()
        data = resp.json()

        spectrum = data.get("spectrum", {}).get("data", [])
        cols = data.get("spectrum", {}).get("columns", [])

        if not spectrum:
            return None

        df = pd.DataFrame(spectrum, columns=cols)

        # Фильтруем ОФЗ с фиксированным купоном
        ofz_mask = df["SECID"].str.startswith("OFZ-PD", na=False)
        ofz = df[ofz_mask].copy()

        if ofz.empty:
            # Fallback: берём любые ОФЗ
            ofz_mask = df["SECID"].str.startswith("OFZ", na=False)
            ofz = df[ofz_mask].copy()

        if ofz.empty:
            return None

        # Средняя доходность к покупке
        yield_col = "YIELDTOBUY" if "YIELDTOBUY" in ofz.columns else "YIELDTOSELL"
        yields = pd.to_numeric(ofz[yield_col], errors="coerce").dropna()

        if yields.empty:
            return None

        median_yield = float(yields.median())
        logger.info("OFZ median yield: %.2f%%", median_yield)
        return median_yield

    except Exception as e:
        logger.warning("Failed to fetch OFZ yield: %s", e)
        return None


# ─── Получение ставки по источнику ──────────────────────────


def get_risk_free_rate(
    source: RiskFreeSource = RiskFreeSource.CBR_KEY_RATE,
    manual_rate: float | None = None,
) -> tuple[float, str]:
    """Получение безрисковой ставки из выбранного источника.

    Args:
        source: Источник ставки.
        manual_rate: Ручная ставка (используется при source=MANUAL).

    Returns:
        Кортеж (ставка_в_процентах, описание_источника).
    """
    if source == RiskFreeSource.MANUAL:
        if manual_rate is None:
            manual_rate = 16.0  # Fallback
        return manual_rate, f"Manual input: {manual_rate:.2f}%"

    if source == RiskFreeSource.CBR_KEY_RATE:
        rate = fetch_cbr_key_rate()
        if rate is not None:
            return rate, f"CBR key rate: {rate:.2f}%"
        # Fallback to OFZ
        logger.info("CBR unavailable, falling back to OFZ yield")
        rate = fetch_ofz_yield()
        if rate is not None:
            return rate, f"OFZ yield (fallback): {rate:.2f}%"
        return 16.0, "Default: 16.0% (all sources unavailable)"

    if source == RiskFreeSource.OFZ_YIELD:
        rate = fetch_ofz_yield()
        if rate is not None:
            return rate, f"OFZ yield: {rate:.2f}%"
        # Fallback to CBR
        logger.info("OFZ unavailable, falling back to CBR key rate")
        rate = fetch_cbr_key_rate()
        if rate is not None:
            return rate, f"CBR key rate (fallback): {rate:.2f}%"
        return 16.0, "Default: 16.0% (all sources unavailable)"

    return 16.0, "Default: 16.0%"
