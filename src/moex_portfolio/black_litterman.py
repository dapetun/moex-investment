"""Модель Black-Litterman: сочетание рыночного равновесия иerview инвестора."""

import logging

import numpy as np
import pandas as pd
from scipy.optimize import minimize

from .metrics import portfolio_return, portfolio_volatility, sharpe_ratio

logger = logging.getLogger(__name__)


def implied_returns(
    cov_matrix: pd.DataFrame,
    market_weights: np.ndarray,
    risk_aversion: float = 1.0,
) -> np.ndarray:
    """Расчёт имплицированных доходностей рыночного равновесия (π).

    π = δ * Σ * w_mkt

    Args:
        cov_matrix: Ковариационная матрица (годовая).
        market_weights: Рыночные веса активов.
        risk_aversion: Коэффициент антипатии к риску (δ).

    Returns:
        Вектор имплицированных дневных доходностей.
    """
    sigma = cov_matrix.values

    # Ridge regularization: если матрица сингулярна или близка к сингулярной,
    # добавляем малый диагональный шум для численной стабильности
    cond = np.linalg.cond(sigma)
    if cond > 1e10:
        ridge = 1e-6 * np.eye(sigma.shape[0])
        sigma = sigma + ridge
        logger.warning(
            "Covariance matrix ill-conditioned (cond=%.1e), applying ridge=%.1e",
            cond, 1e-6,
        )

    pi = risk_aversion * sigma @ market_weights
    return pi


def black_litterman_returns(
    cov_matrix: pd.DataFrame,
    market_weights: np.ndarray,
    P: np.ndarray,
    Q: np.ndarray,
    omega: np.ndarray | None = None,
    tau: float = 0.05,
    risk_aversion: float = 1.0,
) -> tuple[np.ndarray, pd.DataFrame]:
    """Расчёт доходностей и ковариации по модели Black-Litterman.

    Формулы:
        E[R] = [(τΣ)^-1 + P'Ω^-1 P]^-1 [(τΣ)^-1 π + P'Ω^-1 Q]
        Var[R] = [(τΣ)^-1 + P'Ω^-1 P]^-1

    Args:
        cov_matrix: Ковариационная матрица (годовая).
        market_weights: Рыночные веса.
        P: Матрица views (n_views × n_assets). Каждая строка — view.
            Например, [[1, -1, 0, ...]] означает "акция 1 лучше акции 2".
        Q: Вектор целевых доходностей views (n_views,).
        omega: Матрица неопределённости views. Если None, вычисляется
               как diagonal(P @ (τΣ) @ P').
        tau: Масштабный коэффициент неопределённости рыночных данных.
        risk_aversion: Коэффициент антипатии к риску.

    Returns:
        Кортеж (posterior_returns, posterior_cov).
    """
    tickers = cov_matrix.columns.tolist()
    n = len(tickers)
    sigma = cov_matrix.values

    # Имплицированные доходности рыночного равновесия
    pi = implied_returns(cov_matrix, market_weights, risk_aversion)

    tau_sigma = tau * sigma

    # Ridge regularization для tau_sigma
    n = tau_sigma.shape[0]
    cond_tau = np.linalg.cond(tau_sigma)
    if cond_tau > 1e10:
        tau_sigma = tau_sigma + 1e-8 * np.eye(n)
        logger.warning("tau_sigma ill-conditioned (cond=%.1e), ridge applied", cond_tau)

    # Если omega не задана, вычисляем из tau * P Σ P'
    if omega is None:
        omega = np.diag(np.diag(P @ tau_sigma @ P.T))

    # Ridge regularization для omega
    diag_omega = np.diag(omega).copy()
    diag_omega[diag_omega < 1e-12] = 1e-12
    omega = np.diag(diag_omega)

    omega_inv = np.linalg.inv(omega)

    tau_sigma_inv = np.linalg.inv(tau_sigma)

    # A = (τΣ)^-1 + P' Ω^-1 P
    A = tau_sigma_inv + P.T @ omega_inv @ P

    # Ridge regularization для A
    cond_A = np.linalg.cond(A)
    if cond_A > 1e10:
        A = A + 1e-8 * np.eye(n)
        logger.warning("BL matrix A ill-conditioned (cond=%.1e), ridge applied", cond_A)

    # b = (τΣ)^-1 π + P' Ω^-1 Q
    b = tau_sigma_inv @ pi + P.T @ omega_inv @ Q

    # Posterior
    A_inv = np.linalg.inv(A)
    posterior_returns = A_inv @ b
    posterior_cov = pd.DataFrame(
        A_inv + sigma,
        index=tickers,
        columns=tickers,
    )

    logger.info(
        "Black-Litterman: %d assets, %d views, tau=%.3f",
        n, len(Q), tau,
    )

    return posterior_returns, posterior_cov


def optimize_black_litterman(
    returns: pd.DataFrame,
    P: np.ndarray,
    Q: np.ndarray,
    market_weights: np.ndarray | None = None,
    tau: float = 0.05,
    risk_aversion: float = 1.0,
    min_weight: float = 0.0,
    max_weight: float = 0.3,
) -> dict:
    """Оптимизация портфеля по Black-Litterman.

    Args:
        returns: DataFrame с историческими доходностями.
        P: Матрица views (n_views × n_assets).
        Q: Вектор целевых доходностей views.
        market_weights: Рыночные веса. Если None — равные.
        tau: Масштаб неопределённости.
        risk_aversion: Коэффициент антипатии к риску.
        min_weight: Минимальный вес актива.
        max_weight: Максимальный вес актива.

    Returns:
        Словарь с: weights, return, volatility, sharpe, bl_returns, bl_cov.
    """
    tickers = returns.columns.tolist()
    n = len(tickers)

    if market_weights is None:
        market_weights = np.array([1.0 / n] * n)

    cov_matrix = returns.cov()
    bl_returns, bl_cov = black_litterman_returns(
        cov_matrix, market_weights, P, Q, tau=tau, risk_aversion=risk_aversion,
    )

    bl_returns_series = pd.Series(bl_returns, index=tickers)

    # Нормализация весов
    if max_weight * n < 1.0:
        max_weight = 1.0 / n
    if min_weight * n > 1.0:
        min_weight = 1.0 / n

    bounds = [(min_weight, max_weight)] * n
    constraints = [{"type": "eq", "fun": lambda w: np.sum(w) - 1.0}]
    init_weights = np.array([1.0 / n] * n)

    def neg_sharpe(w):
        return -sharpe_ratio(w, bl_returns_series, bl_cov)

    result = minimize(
        neg_sharpe,
        init_weights,
        method="SLSQP",
        bounds=bounds,
        constraints=constraints,
    )

    if not result.success:
        logger.warning("BL optimization failed: %s", result.message)

    weights = result.x
    return {
        "weights": weights,
        "return": portfolio_return(weights, bl_returns_series),
        "volatility": portfolio_volatility(weights, bl_cov),
        "sharpe": sharpe_ratio(weights, bl_returns_series, bl_cov),
        "bl_returns": bl_returns_series,
        "bl_cov": bl_cov,
    }


def create_views_from_correlation(
    returns: pd.DataFrame,
    corr_matrix: pd.DataFrame,
    top_n: int = 5,
) -> tuple[np.ndarray, np.ndarray]:
    """Автоматическое создание views на основе корреляций.

    Создаёт views типа "акция A лучше акции B" для наименее
    коррелированных пар.

    Args:
        returns: DataFrame с доходностями.
        corr_matrix: Матрица корреляций.
        top_n: Количество views.

    Returns:
        Кортеж (P, Q).
    """
    tickers = returns.columns.tolist()
    n = len(tickers)
    mean_returns = returns.mean()

    # Находим пары с наименьшей корреляцией
    pairs = []
    for i in range(n):
        for j in range(i + 1, n):
            pairs.append((tickers[i], tickers[j], corr_matrix.iloc[i, j]))

    pairs.sort(key=lambda x: x[2])
    selected = pairs[:top_n]

    P = np.zeros((top_n, n))
    Q = np.zeros(top_n)

    for k, (a, b, _) in enumerate(selected):
        i = tickers.index(a)
        j = tickers.index(b)
        P[k, i] = 1
        P[k, j] = -1
        # View: разность средних доходностей (дневная)
        Q[k] = mean_returns[a] - mean_returns[b]

    logger.info("Created %d views from correlation analysis", top_n)
    return P, Q
