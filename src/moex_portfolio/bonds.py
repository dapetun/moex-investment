"""Расчёт параметров облигаций: YTM, Duration, Convexity, Price.

Математические модели:
- YTM: решается уравнение NPV = 0 через scipy.optimize
- Macaulay Duration: взвешенное среднее сроков получения денежных потоков
- Modified Duration: Sensitivity к изменению ставки
- Convexity: кривизна зависимости цены от доходности
- Fair Price: теоретическая цена облигации
"""

import logging
from datetime import date

from scipy.optimize import brentq

logger = logging.getLogger(__name__)

TRADING_DAYS_PER_YEAR = 252
COUPON_DAYS_PER_YEAR = 365


def bond_price(
    coupon_rate: float,
    face_value: float,
    ytm: float,
    years_to_maturity: float,
    coupons_per_year: int = 2,
    coupon_value: float | None = None,
) -> float:
    """Теоретическая цена облигации.

    P = sum(C/(1+y/k)^i) + FV/(1+y/k)^(k*T)

    Args:
        coupon_rate: Купонная ставка (годовая, дробью, например 0.08 = 8%).
        face_value: Номинал облигации.
        ytm: Доходность к погашению (годовая, дробью).
        years_to_maturity: Срок до погашения (в годах).
        coupons_per_year: Выплат купонов в год (2 = полугодовые).
        coupon_value: Сумма купона (если None, считается как coupon_rate * face_value / coupons_per_year).

    Returns:
        Цена облигации.
    """
    if coupon_value is None:
        coupon_value = coupon_rate * face_value / coupons_per_year

    n_coupons = int(years_to_maturity * coupons_per_year)
    discount_rate = ytm / coupons_per_year

    if discount_rate == 0:
        return coupon_value * n_coupons + face_value

    pv_coupons = sum(
        coupon_value / (1 + discount_rate) ** i
        for i in range(1, n_coupons + 1)
    )
    pv_face = face_value / (1 + discount_rate) ** n_coupons

    return pv_coupons + pv_face


def bond_ytm(
    price: float,
    coupon_rate: float,
    face_value: float,
    years_to_maturity: float,
    coupons_per_year: int = 2,
    coupon_value: float | None = None,
) -> float:
    """Yield to Maturity (доходность к погашению).

    Решает уравнение: bond_price(ytm) = target_price

    Args:
        price: Рыночная цена облигации.
        coupon_rate: Купонная ставка (годовая, дробью).
        face_value: Номинал.
        years_to_maturity: Срок до погашения (в годах).
        coupons_per_year: Выплат купонов в год.
        coupon_value: Сумма купона.

    Returns:
        YTM (годовая доходность, дробью).
    """
    if years_to_maturity <= 0:
        return 0.0

    def price_diff(y):
        return bond_price(coupon_rate, face_value, y, years_to_maturity, coupons_per_year, coupon_value) - price

    try:
        ytm = brentq(price_diff, -0.5, 10.0, maxiter=1000)
        return ytm
    except ValueError:
        logger.warning("YTM not found for price=%.2f, coupon=%.2f%%, T=%.1f",
                        price, coupon_rate * 100, years_to_maturity)
        return 0.0


def macaulay_duration(
    coupon_rate: float,
    face_value: float,
    ytm: float,
    years_to_maturity: float,
    coupons_per_year: int = 2,
    coupon_value: float | None = None,
) -> float:
    """Macaulay Duration (средневзвешенный срок получения денежных потоков).

    D = (1/P) * sum(t_i * CF_i / (1+y/k)^i)

    Args:
        coupon_rate: Купонная ставка (годовая, дробью).
        face_value: Номинал.
        ytm: Доходность к погашению.
        years_to_maturity: Срок до погашения (в годах).
        coupons_per_year: Выплат купонов в год.
        coupon_value: Сумма купона.

    Returns:
        Macaulay Duration (в годах).
    """
    if coupon_value is None:
        coupon_value = coupon_rate * face_value / coupons_per_year

    n_coupons = int(years_to_maturity * coupons_per_year)
    discount_rate = ytm / coupons_per_year
    price = bond_price(coupon_rate, face_value, ytm, years_to_maturity, coupons_per_year, coupon_value)

    if price == 0 or discount_rate == 0:
        return years_to_maturity

    weighted_time = 0.0
    for i in range(1, n_coupons + 1):
        t = i / coupons_per_year
        cf = coupon_value if i < n_coupons else coupon_value + face_value
        pv = cf / (1 + discount_rate) ** i
        weighted_time += t * pv

    return weighted_time / price


def modified_duration(
    coupon_rate: float,
    face_value: float,
    ytm: float,
    years_to_maturity: float,
    coupons_per_year: int = 2,
    coupon_value: float | None = None,
) -> float:
    """Modified Duration — чувствительность цены к изменению доходности.

    D_mod = D_mac / (1 + y/k)

    Args:
        coupon_rate: Купонная ставка.
        face_value: Номинал.
        ytm: Доходность к погашению.
        years_to_maturity: Срок до погашения.
        coupons_per_year: Выплат купонов в год.
        coupon_value: Сумма купона.

    Returns:
        Modified Duration.
    """
    mac_d = macaulay_duration(
        coupon_rate, face_value, ytm, years_to_maturity, coupons_per_year, coupon_value
    )
    discount_rate = ytm / coupons_per_year

    if discount_rate == -1:
        return mac_d

    return mac_d / (1 + discount_rate)


def convexity(
    coupon_rate: float,
    face_value: float,
    ytm: float,
    years_to_maturity: float,
    coupons_per_year: int = 2,
    coupon_value: float | None = None,
) -> float:
    """Convexity — кривизна зависимости цены от доходности.

    C = (1/P) * sum(t_i * (t_i + 1) * CF_i / (1+y/k)^(i+2)) / k^2

    Args:
        coupon_rate: Купонная ставка.
        face_value: Номинал.
        ytm: Доходность к погашению.
        years_to_maturity: Срок до погашения.
        coupons_per_year: Выплат купонов в год.
        coupon_value: Сумма купона.

    Returns:
        Convexity.
    """
    if coupon_value is None:
        coupon_value = coupon_rate * face_value / coupons_per_year

    n_coupons = int(years_to_maturity * coupons_per_year)
    discount_rate = ytm / coupons_per_year
    price = bond_price(coupon_rate, face_value, ytm, years_to_maturity, coupons_per_year, coupon_value)

    if price == 0 or discount_rate == 0:
        return 0.0

    conv = 0.0
    for i in range(1, n_coupons + 1):
        t = i / coupons_per_year
        cf = coupon_value if i < n_coupons else coupon_value + face_value
        pv = cf / (1 + discount_rate) ** i
        conv += t * (t + 1 / coupons_per_year) * pv

    return conv / (price * (1 + discount_rate) ** 2)


def price_change_approximation(
    duration: float,
    convexity_val: float,
    current_price: float,
    yield_change: float,
) -> float:
    """Приближённое изменение цены облигации.

    ΔP/P ≈ -D * Δy + 0.5 * C * (Δy)^2

    Args:
        duration: Modified Duration.
        convexity_val: Convexity.
        current_price: Текущая цена.
        yield_change: Изменение доходности (например, 0.01 = 100 bps).

    Returns:
        Новая цена.
    """
    dp = current_price * (-duration * yield_change + 0.5 * convexity_val * yield_change**2)
    return current_price + dp


def years_between(d1: date, d2: date) -> float:
    """Разница между датами в годах (365 дней)."""
    return (d2 - d1).days / COUPON_DAYS_PER_YEAR


def bond_analysis(
    ticker: str,
    price: float,
    coupon_rate: float,
    face_value: float,
    maturity_date: date,
    coupons_per_year: int = 2,
    coupon_value: float | None = None,
    valuation_date: date | None = None,
) -> dict:
    """Полный анализ облигации.

    Args:
        ticker: Тикер облигации.
        price: Рыночная цена.
        coupon_rate: Купонная ставка.
        face_value: Номинал.
        maturity_date: Дата погашения.
        coupons_per_year: Выплат купонов в год.
        coupon_value: Сумма купона.
        valuation_date: Дата анализа.

    Returns:
        Словарь с параметрами: ytm, macaulay_duration, modified_duration,
        convexity, price_change_100bps, etc.
    """
    if valuation_date is None:
        valuation_date = date.today()

    years_to_maturity = years_between(valuation_date, maturity_date)
    if years_to_maturity <= 0:
        return {"ticker": ticker, "error": "Bond already matured"}

    ytm = bond_ytm(price, coupon_rate, face_value, years_to_maturity, coupons_per_year, coupon_value)

    mac_d = macaulay_duration(coupon_rate, face_value, ytm, years_to_maturity, coupons_per_year, coupon_value)
    mod_d = modified_duration(coupon_rate, face_value, ytm, years_to_maturity, coupons_per_year, coupon_value)
    conv = convexity(coupon_rate, face_value, ytm, years_to_maturity, coupons_per_year, coupon_value)

    price_up = price_change_approximation(mod_d, conv, price, 0.01)
    price_down = price_change_approximation(mod_d, conv, price, -0.01)

    return {
        "ticker": ticker,
        "price": price,
        "face_value": face_value,
        "coupon_rate": coupon_rate,
        "coupon_value": coupon_value or (coupon_rate * face_value / coupons_per_year),
        "years_to_maturity": years_to_maturity,
        "ytm": ytm,
        "macaulay_duration": mac_d,
        "modified_duration": mod_d,
        "convexity": conv,
        "price_change_100bps_up": price_up - price,
        "price_change_100bps_down": price_down - price,
        "current_yield": (coupon_rate * face_value) / price if price > 0 else 0,
    }
