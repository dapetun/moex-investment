"""Построение кривой доходности ОФЗ.

Interpolated yield curve на основе рыночных данных по ГКО/ОФЗ.
"""

import logging
from datetime import date

import numpy as np
import pandas as pd
from scipy.interpolate import CubicSpline

logger = logging.getLogger(__name__)


def build_yield_curve(
    ofz_data: pd.DataFrame,
    valuation_date: date | None = None,
) -> pd.DataFrame:
    """Построение кривой доходности ОФЗ.

    Args:
        ofz_data: DataFrame с ОФЗ, должен содержать:
            - SECID: тикер
            - YIELDTOOFFER или yield: доходность
            - MATDATE: дата погашения
        valuation_date: Дата оценки.

    Returns:
        DataFrame с колонками [maturity_years, yield_pct, ticker] отсортированный по сроку.
    """
    if valuation_date is None:
        valuation_date = date.today()

    if ofz_data.empty:
        return pd.DataFrame()

    records = []
    for _, row in ofz_data.iterrows():
        ticker = row.get("SECID", "")
        yield_val = row.get("YIELDTOOFFER") or row.get("yield") or row.get("YIELD")
        mat_date_str = row.get("MATDATE", "")

        if pd.isna(yield_val) or pd.isna(mat_date_str) or not mat_date_str:
            continue

        try:
            if isinstance(mat_date_str, str):
                mat_date = pd.to_datetime(mat_date_str).date()
            else:
                mat_date = pd.Timestamp(mat_date_str).date()

            years = (mat_date - valuation_date).days / 365.25
            if years <= 0:
                continue

            yield_pct = float(yield_val)
            records.append({
                "ticker": ticker,
                "maturity_years": years,
                "yield_pct": yield_pct,
                "maturity_date": mat_date,
            })
        except (ValueError, KeyError, TypeError) as e:
            logger.debug("Failed to parse yield for %s: %s", ticker, e)
            continue

    if not records:
        return pd.DataFrame()

    curve = pd.DataFrame(records)
    curve = curve.sort_values("maturity_years")
    curve = curve.drop_duplicates(subset=["maturity_years"], keep="first")

    logger.info(
        "Yield curve built: %d points, maturities %.1f-%.1f years",
        len(curve),
        curve["maturity_years"].min(),
        curve["maturity_years"].max(),
    )

    return curve


def interpolate_yield_curve(
    curve: pd.DataFrame,
    target_maturities: np.ndarray | None = None,
) -> pd.DataFrame:
    """Интерполяция кривой доходности (кубический сплайн).

    Args:
        curve: DataFrame с колонками [maturity_years, yield_pct].
        target_maturities: Целевые сроки (по умолчанию 0.25, 0.5, 1, 2, ..., 30).

    Returns:
        DataFrame с интерполированными значениями.
    """
    if len(curve) < 2:
        return curve

    if target_maturities is None:
        max_maturity = curve["maturity_years"].max()
        target_maturities = np.arange(0.25, min(max_maturity + 0.25, 31), 0.25)

    cs = CubicSpline(curve["maturity_years"].values, curve["yield_pct"].values)

    interpolated_yields = cs(target_maturities)

    result = pd.DataFrame({
        "maturity_years": target_maturities,
        "yield_pct": interpolated_yields,
    })

    return result


def zero_coupon_yield(
    coupon_rate: float,
    face_value: float,
    ytm: float,
    maturity_years: float,
) -> float:
    """Equivalent Zero-Coupon Yield.

    Эквивалентная бескупонная доходность для купонной облигации.

    Args:
        coupon_rate: Купонная ставка.
        face_value: Номинал.
        ytm: Текущая YTM.
        maturity_years: Срок до погашения.

    Returns:
        Zero-coupon yield.
    """
    from .bonds import bond_price

    price = bond_price(coupon_rate, face_value, ytm, maturity_years)

    if price <= 0 or maturity_years <= 0:
        return ytm

    return (face_value / price) ** (1 / maturity_years) - 1


def forward_rate(
    spot_rate_1: float,
    spot_rate_2: float,
    maturity_1: float,
    maturity_2: float,
) -> float:
    """Forward rate между двумя сроками.

    f(t1, t2) = [(1+r2)^t2 / (1+r1)^t1]^(1/(t2-t1)) - 1

    Args:
        spot_rate_1: Spot rate для срока t1.
        spot_rate_2: Spot rate для срока t2.
        maturity_1: Срок t1 (в годах).
        maturity_2: Срок t2 (в годах).

    Returns:
        Forward rate.
    """
    if maturity_2 <= maturity_1:
        return 0.0

    dt = maturity_2 - maturity_1
    ratio = (1 + spot_rate_2) ** maturity_2 / (1 + spot_rate_1) ** maturity_1
    return ratio ** (1 / dt) - 1


def compute_forward_rates(curve: pd.DataFrame) -> pd.DataFrame:
    """Расчёт forwards rates на основе кривой.

    Args:
        curve: DataFrame с [maturity_years, yield_pct].

    Returns:
        DataFrame с forward rates.
    """
    if len(curve) < 2:
        return pd.DataFrame()

    forwards = []
    for i in range(len(curve) - 1):
        t1 = curve.iloc[i]["maturity_years"]
        r1 = curve.iloc[i]["yield_pct"] / 100
        t2 = curve.iloc[i + 1]["maturity_years"]
        r2 = curve.iloc[i + 1]["yield_pct"] / 100

        fr = forward_rate(r1, r2, t1, t2)
        forwards.append({
            "from_maturity": t1,
            "to_maturity": t2,
            "forward_rate_pct": fr * 100,
        })

    return pd.DataFrame(forwards)


def spot_spread(
    bond_yield: float,
    risk_free_yield: float,
) -> float:
    """Credit Spread = YTM облигации - Risk-Free Rate (ОФЗ).

    Args:
        bond_yield: Доходность корпоративной облигации.
        risk_free_yield: Доходность ОФЗ аналогичного срока.

    Returns:
        Spread в процентах.
    """
    return bond_yield - risk_free_yield


def term_structure_analysis(curve: pd.DataFrame) -> dict:
    """Анализ формы кривой доходности.

    Определяет: нормальная / инвертированная / плоская.

    Args:
        curve: DataFrame с [maturity_years, yield_pct].

    Returns:
        Словарь с характеристиками кривой.
    """
    if len(curve) < 2:
        return {"shape": "insufficient_data"}

    short_yield = curve.iloc[0]["yield_pct"]
    long_yield = curve.iloc[-1]["yield_pct"]
    mid_idx = len(curve) // 2
    mid_yield = curve.iloc[mid_idx]["yield_pct"]

    spread = long_yield - short_yield

    if spread > 0.5:
        shape = "normal"
    elif spread < -0.5:
        shape = "inverted"
    else:
        shape = "flat"

    return {
        "shape": shape,
        "short_yield": short_yield,
        "mid_yield": mid_yield,
        "long_yield": long_yield,
        "term_spread_pct": spread,
        "steepness": spread / (curve.iloc[-1]["maturity_years"] - curve.iloc[0]["maturity_years"]),
    }
