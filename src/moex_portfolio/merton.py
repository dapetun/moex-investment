"""Merton Structural Credit Risk Model.

Структурная модель Мертона (1974):
- Фирма = call option на активы (equity = call on V)
- Default occurs if V < D (assets < debt at maturity)
- Uses Black-Scholes framework

Ключевые результаты:
- Probability of Default (PD)
- Distance to Default (DD)
- Credit Spread
- Recovery Rate
"""

import logging

import numpy as np
from scipy.stats import norm

logger = logging.getLogger(__name__)


def merton_equity_value(
    assets_value: float,
    debt_face_value: float,
    volatility_assets: float,
    risk_free_rate: float,
    time_to_maturity: float,
) -> float:
    """Стоимость капитала по модели Мертона.

    E = V * N(d1) - D * e^(-rT) * N(d2)

    Args:
        assets_value: Текущая стоимость активов фирмы (V).
        debt_face_value: Номинал долга (D).
        volatility_assets: Волатильность активов (sigma_V).
        risk_free_rate: Безрисковая ставка (r).
        time_to_maturity: Срок до погашения долга (T, в годах).

    Returns:
        Стоимость капитала (equity value).
    """
    d1, d2 = _compute_d1_d2(assets_value, debt_face_value, volatility_assets, risk_free_rate, time_to_maturity)

    equity = assets_value * norm.cdf(d1) - debt_face_value * np.exp(-risk_free_rate * time_to_maturity) * norm.cdf(d2)
    return max(equity, 0.0)


def merton_debt_value(
    assets_value: float,
    debt_face_value: float,
    volatility_assets: float,
    risk_free_rate: float,
    time_to_maturity: float,
) -> float:
    """Стоимость долга по модели Мертона.

    D_value = V - E  (или через BS: D = V - call(V, D))

    Args:
        assets_value: Стоимость активов.
        debt_face_value: Номинал долга.
        volatility_assets: Волатильность активов.
        risk_free_rate: Безрисковая ставка.
        time_to_maturity: Срок до погашения.

    Returns:
        Стоимость долга.
    """
    equity = merton_equity_value(
        assets_value, debt_face_value, volatility_assets, risk_free_rate, time_to_maturity
    )
    return assets_value - equity


def distance_to_default(
    assets_value: float,
    debt_face_value: float,
    volatility_assets: float,
    risk_free_rate: float,
    time_to_maturity: float,
) -> float:
    """Distance to Default (DD).

    DD = [ln(V/D) + (r + 0.5 * sigma^2) * T] / (sigma * sqrt(T))

    DD > 2: низкий риск дефолта
    DD 1-2: умеренный риск
    DD < 1: высокий риск

    Args:
        assets_value: Стоимость активов.
        debt_face_value: Номинал долга ( strike price).
        volatility_assets: Волатильность активов.
        risk_free_rate: Безрисковая ставка.
        time_to_maturity: Срок до погашения.

    Returns:
        Distance to Default.
    """
    if assets_value <= 0 or debt_face_value <= 0 or time_to_maturity <= 0:
        return 0.0

    d1, _ = _compute_d1_d2(assets_value, debt_face_value, volatility_assets, risk_free_rate, time_to_maturity)
    return d1


def probability_of_default(
    assets_value: float,
    debt_face_value: float,
    volatility_assets: float,
    risk_free_rate: float,
    time_to_maturity: float,
) -> float:
    """Вероятность дефолта (Risk-Neutral PD).

    PD = N(-DD) = N(-d2)

    Args:
        assets_value: Стоимость активов.
        debt_face_value: Номинал долга.
        volatility_assets: Волатильность активов.
        risk_free_rate: Безрисковая ставка.
        time_to_maturity: Срок до погашения.

    Returns:
        Вероятность дефолта (0-1).
    """
    _, d2 = _compute_d1_d2(assets_value, debt_face_value, volatility_assets, risk_free_rate, time_to_maturity)
    return norm.cdf(-d2)


def merton_credit_spread(
    assets_value: float,
    debt_face_value: float,
    volatility_assets: float,
    risk_free_rate: float,
    time_to_maturity: float,
) -> float:
    """Credit Spread по модели Мертона.

    Spread = YTM_corporate - r
    Вычисляется как разница между YTM долга и безрисковой ставкой.

    Args:
        assets_value: Стоимость активов.
        debt_face_value: Номинал долга.
        volatility_assets: Волатильность активов.
        risk_free_rate: Безрисковая ставка.
        time_to_maturity: Срок до погашения.

    Returns:
        Credit spread (годовая, дробью).
    """
    debt_value = merton_debt_value(
        assets_value, debt_face_value, volatility_assets, risk_free_rate, time_to_maturity
    )

    if debt_value <= 0 or time_to_maturity <= 0:
        return 0.0

    ytm = -np.log(debt_value / debt_face_value) / time_to_maturity
    return ytm - risk_free_rate


def recovery_rate(
    assets_value: float,
    debt_face_value: float,
    volatility_assets: float,
    risk_free_rate: float,
    time_to_maturity: float,
) -> float:
    """Recovery Rate (ожидаемая величина возврата при дефолте).

    RR = (V / D) * N(h1) + (1 - sigma^2 / (2*r)) * N(h2) (approx)

    Упрощённая формула: RR ≈ assets_value * N(d1) / debt_face_value

    Args:
        assets_value: Стоимость активов.
        debt_face_value: Номинал долга.
        volatility_assets: Волатильность активов.
        risk_free_rate: Безрисковая ставка.
        time_to_maturity: Срок до погашения.

    Returns:
        Recovery Rate (0-1).
    """
    d1, _ = _compute_d1_d2(assets_value, debt_face_value, volatility_assets, risk_free_rate, time_to_maturity)

    implied_recovery = (assets_value / debt_face_value) * norm.cdf(d1)
    return min(max(implied_recovery, 0.0), 1.0)


def implied_asset_value(
    equity_value: float,
    debt_face_value: float,
    volatility_equity: float,
    risk_free_rate: float,
    time_to_maturity: float,
    leverage: float = 0.5,
    max_iter: int = 100,
    tol: float = 1e-6,
) -> tuple[float, float]:
    """Оценка стоимости активов и их волатильности через iterational method.

    Используем систему двух уравнений:
    1) E = V * N(d1) - D * e^(-rT) * N(d2)
    2) sigma_E * E = sigma_V * V * N(d1)

    Args:
        equity_value: Рыночная стоимость капитала.
        debt_face_value: Номинал долга.
        volatility_equity: Волатильность капитала.
        risk_free_rate: Безрисковая ставка.
        time_to_maturity: Срок до погашения.
        leverage: Начальная оценка leverage (V/D).
        max_iter: Максимум итераций.
        tol: Точность.

    Returns:
        Кортеж (implied_assets_value, implied_assets_volatility).
    """
    V = equity_value + debt_face_value
    sigma_V = volatility_equity * leverage

    for _ in range(max_iter):
        d1, d2 = _compute_d1_d2(V, debt_face_value, sigma_V, risk_free_rate, time_to_maturity)
        nd1 = norm.cdf(d1)

        if nd1 <= 0:
            break

        new_V = (equity_value + debt_face_value * np.exp(-risk_free_rate * time_to_maturity) * norm.cdf(d2)) / norm.cdf(d1)
        new_sigma_V = (volatility_equity * equity_value) / (nd1 * new_V) if new_V > 0 else sigma_V

        if abs(new_V - V) < tol and abs(new_sigma_V - sigma_V) < tol:
            break

        V = new_V
        sigma_V = new_sigma_V

    return V, sigma_V


def full_merton_analysis(
    equity_value: float,
    debt_face_value: float,
    volatility_equity: float,
    risk_free_rate: float,
    time_to_maturity: float,
) -> dict:
    """Полный анализ Merton Model.

    Args:
        equity_value: Рыночная стоимость капитала.
        debt_face_value: Номинал долга.
        volatility_equity: Волатильность капитала.
        risk_free_rate: Безрисковая ставка.
        time_to_maturity: Срок до погашения.

    Returns:
        Словарь с полным анализом.
    """
    V, sigma_V = implied_asset_value(
        equity_value, debt_face_value, volatility_equity,
        risk_free_rate, time_to_maturity,
    )

    dd = distance_to_default(V, debt_face_value, sigma_V, risk_free_rate, time_to_maturity)
    pd_val = probability_of_default(V, debt_face_value, sigma_V, risk_free_rate, time_to_maturity)
    spread = merton_credit_spread(V, debt_face_value, sigma_V, risk_free_rate, time_to_maturity)
    rr = recovery_rate(V, debt_face_value, sigma_V, risk_free_rate, time_to_maturity)
    equity_est = merton_equity_value(V, debt_face_value, sigma_V, risk_free_rate, time_to_maturity)
    debt_est = merton_debt_value(V, debt_face_value, sigma_V, risk_free_rate, time_to_maturity)

    leverage = debt_face_value / V if V > 0 else 0

    logger.info(
        "Merton: DD=%.2f, PD=%.2f%%, Spread=%.2f%%, Recovery=%.1f%%",
        dd, pd_val * 100, spread * 100, rr * 100,
    )

    return {
        "implied_assets_value": V,
        "implied_assets_volatility": sigma_V,
        "equity_value_market": equity_value,
        "equity_value_model": equity_est,
        "debt_value_market": debt_face_value,
        "debt_value_model": debt_est,
        "leverage": leverage,
        "distance_to_default": dd,
        "probability_of_default": pd_val,
        "credit_spread_bps": spread * 10_000,
        "recovery_rate": rr,
        "risk_free_rate": risk_free_rate,
        "time_to_maturity": time_to_maturity,
    }


def _compute_d1_d2(
    V: float,
    D: float,
    sigma: float,
    r: float,
    T: float,
) -> tuple[float, float]:
    """Вычисление d1 и d2 для Black-Scholes.

    d1 = [ln(V/D) + (r + sigma^2/2) * T] / (sigma * sqrt(T))
    d2 = d1 - sigma * sqrt(T)
    """
    if V <= 0 or D <= 0 or sigma <= 0 or T <= 0:
        return 0.0, 0.0

    sqrt_T = np.sqrt(T)
    d1 = (np.log(V / D) + (r + 0.5 * sigma**2) * T) / (sigma * sqrt_T)
    d2 = d1 - sigma * sqrt_T
    return d1, d2
