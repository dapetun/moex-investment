"""Оркестрация headless-расчётов без Streamlit.

Математика оптимизатора не изменяется — вызываются существующие функции.
Вокруг solver добавляются только проверки результата.
"""

from __future__ import annotations

import logging
import math
from typing import Any

import numpy as np
import pandas as pd

from .config import MAX_WEIGHT
from .filters import prepare_returns
from .numeric import NumericValidationError, require_finite_number, require_nonnegative_finite
from .optimizer import max_sharpe_portfolio
from .portfolio_state import HoldingsValidationError, weights_from_holdings
from .risk_models import covariance_matrix

logger = logging.getLogger(__name__)

WEIGHT_SUM_TOLERANCE = 1e-6
WEIGHT_BOUND_TOLERANCE = 1e-8


def _validate_solver_result(
    weights: dict[str, float],
    *,
    max_weight: float,
    metrics: dict[str, float],
) -> None:
    """Отклонить некорректный результат solver до записи target."""
    if not weights:
        raise NumericValidationError("optimizer returned empty weights")
    total = 0.0
    for ticker, value in weights.items():
        w = require_nonnegative_finite(value, f"weight[{ticker}]")
        if w > max_weight + WEIGHT_BOUND_TOLERANCE:
            raise NumericValidationError(
                f"weight[{ticker}]={w} exceeds max_weight={max_weight}"
            )
        total += w
    if abs(total - 1.0) > WEIGHT_SUM_TOLERANCE:
        raise NumericValidationError(
            f"weights sum to {total:.6f}, expected 1.0 "
            f"(tol={WEIGHT_SUM_TOLERANCE})"
        )
    for name, value in metrics.items():
        require_finite_number(value, name)


def run_optimize(
    raw_prices: pd.DataFrame,
    *,
    max_weight: float = MAX_WEIGHT,
    risk_free_rate: float = 0.0,
    cov_method: str = "ledoit_wolf",
    min_turnover: float = 0.0,
    mode: str = "universe",
    holdings: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Запустить Max Sharpe на подготовленных доходностях.

    Args:
        raw_prices: Панель CLOSE + VALUE.
        max_weight: Макс. вес актива.
        risk_free_rate: Безрисковая ставка (доля).
        cov_method: Метод ковариации.
        min_turnover: Порог оборота (0 для синтетики; для market — MIN_TURNOVER).
        mode: ``universe`` — все ликвидные тикеры фикстуры;
            ``holdings`` — только тикеры из holdings (непустые).
        holdings: Структура holdings для mode=holdings.

    Returns:
        weights (dict), metrics, tickers, success, message, mode.
        ``success`` — только True при явном success solver и валидных весах;
        отсутствующий флаг success трактуется как неуспех.
    """
    max_weight = require_finite_number(max_weight, "max_weight")
    if not (0.0 < max_weight <= 1.0):
        raise NumericValidationError(
            f"max_weight must be in (0, 1], got {max_weight}"
        )
    risk_free_rate = require_finite_number(risk_free_rate, "risk_free_rate")
    min_turnover = require_nonnegative_finite(min_turnover, "min_turnover")

    work = raw_prices
    if mode == "holdings":
        if not holdings or not holdings.get("positions"):
            raise HoldingsValidationError(
                "mode=holdings requires non-empty holdings positions"
            )
        tickers = [p["ticker"].upper() for p in holdings["positions"]]
        cols: list[str] = []
        for t in tickers:
            if t not in work.columns:
                raise HoldingsValidationError(f"ticker {t} missing in price panel")
            cols.append(t)
            v = f"{t}_VALUE"
            if v in work.columns:
                cols.append(v)
        work = work[cols]
    elif mode != "universe":
        raise ValueError(f"unknown optimize mode: {mode}")

    returns, valid = prepare_returns(work, min_turnover=min_turnover)
    if not valid:
        raise HoldingsValidationError("no valid tickers after filters")

    mean_ret = returns.mean()
    cov = covariance_matrix(returns, method=cov_method)
    opt = max_sharpe_portfolio(
        mean_ret,
        cov,
        risk_free_rate=risk_free_rate,
        max_weight=max_weight,
    )

    # Отсутствующий success ≠ успех (безопасный default).
    solver_ok = opt.get("success") is True
    weights_arr = np.asarray(opt["weights"], dtype=float)
    weights = {t: float(w) for t, w in zip(valid, weights_arr, strict=True)}

    metrics = {
        "return": float(opt["return"]),
        "volatility": float(opt["volatility"]),
        "sharpe": float(opt["sharpe"]),
    }
    message = str(opt.get("message", ""))
    success = False
    if solver_ok:
        try:
            _validate_solver_result(weights, max_weight=max_weight, metrics=metrics)
            success = True
        except NumericValidationError as e:
            message = f"post-solver validation failed: {e}"
            logger.warning(message)
            success = False
    elif "success" not in opt:
        suffix = "optimizer omitted success flag; treated as failure"
        message = f"{message}; {suffix}" if message else suffix
        logger.warning(message)

    # Веса оставляем в ответе для диагностики; target пишется только при success.
    return {
        "mode": mode,
        "tickers": valid,
        "weights": weights,
        "return": metrics["return"] if math.isfinite(metrics["return"]) else None,
        "volatility": (
            metrics["volatility"] if math.isfinite(metrics["volatility"]) else None
        ),
        "sharpe": metrics["sharpe"] if math.isfinite(metrics["sharpe"]) else None,
        "success": success,
        "message": message,
        "risk_free_rate": risk_free_rate,
        "max_weight": max_weight,
        "cov_method": cov_method,
        "min_turnover": min_turnover,
    }


def current_weights_or_empty(holdings: dict[str, Any]) -> dict[str, float]:
    """Веса из holdings или {} для пустого портфеля."""
    if not holdings.get("positions"):
        return {}
    return weights_from_holdings(holdings)
