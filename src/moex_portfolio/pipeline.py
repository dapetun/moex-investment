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
from .numeric import (
    NumericValidationError,
    require_finite_number,
    require_nonnegative_finite,
)
from .optimizer import (
    InfeasibleWeightConstraints,
    equal_weight_portfolio,
    max_sharpe_portfolio,
    min_variance_portfolio,
)
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
    max_top5: float | None = None,
    risk_free_rate: float = 0.0,
    risk_free_origin: str = "caller_default_zero",
    cov_method: str = "ledoit_wolf",
    min_turnover: float = 0.0,
    mode: str = "universe",
    holdings: dict[str, Any] | None = None,
    objective: str = "max_sharpe",
    current_weights: dict[str, float] | None = None,
    cost_bps: float | None = None,
    max_turnover: float | None = None,
    portfolio_value: float | None = None,
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
    cov_diag: dict[str, Any] = {}
    cov = covariance_matrix(returns, method=cov_method, diagnostics=cov_diag)
    solvers = {
        "max_sharpe": max_sharpe_portfolio,
        "min_variance": min_variance_portfolio,
        "equal_weight": equal_weight_portfolio,
    }
    if objective not in solvers:
        raise ValueError(f"unknown objective: {objective}")
    try:
        opt = solvers[objective](
            mean_ret,
            cov,
            risk_free_rate=risk_free_rate,
            max_weight=max_weight,
            max_top5=max_top5,
        )
    except InfeasibleWeightConstraints as e:
        return {
            "mode": mode,
            "objective": objective,
            "tickers": list(valid),
            "weights": {},
            "success": False,
            "message": str(e),
            "code": InfeasibleWeightConstraints.code,
            "risk_free_rate": risk_free_rate,
            "risk_free_rate_unit": "annual",
            "risk_free_origin": risk_free_origin,
            "risk_free_period": "daily_equivalent = annual/252; Sharpe uses annual return and annual rf",
            "max_weight": max_weight,
            "max_top5": max_top5,
            "policy_name": "custom",
            "cov_method": cov_method,
            "covariance_diagnostics": cov_diag,
            "min_turnover": min_turnover,
            "n_observations": int(len(returns)),
            "n_assets": int(returns.shape[1]),
            "target_updated": False,
        }

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
    turnover = _turnover_block(
        current_weights or {},
        weights if success else {},
        cost_bps=cost_bps,
        max_turnover=max_turnover,
        portfolio_value=portfolio_value,
    )
    code = None
    if success and turnover.get("turnover_limit_breached"):
        success = False
        code = "TURNOVER_LIMIT"
        message = (
            f"one_way_turnover {turnover['one_way_turnover']} exceeds "
            f"max_turnover {max_turnover}"
        )
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
        "code": code,
        "risk_free_rate": risk_free_rate,
        "risk_free_rate_unit": "annual",
        "risk_free_origin": risk_free_origin,
        "risk_free_period": (
            "Sharpe = (annual_return - annual_rf) / annual_vol; "
            "daily_equivalent = annual_rf/252 does not replace that formula"
        ),
        "max_weight": max_weight,
        "max_top5": max_top5,
        "objective": objective,
        "policy_name": "custom",
        "concentration": opt.get("concentration"),
        "cov_method": cov_method,
        "covariance_diagnostics": cov_diag,
        "min_turnover": min_turnover,
        "n_observations": int(len(returns)),
        "n_assets": int(returns.shape[1]),
        "turnover": turnover,
    }


def _turnover_block(
    current: dict[str, float],
    target: dict[str, float],
    *,
    cost_bps: float | None,
    max_turnover: float | None,
    portfolio_value: float | None,
) -> dict[str, Any]:
    """Развести L1, односторонний оборот и денежные издержки.

    Σ|Δw| — сумма модулей изменения весов.
    one_way = 0.5 * Σ|Δw| — доля портфеля, которую нужно продать
    (и столько же купить), если нет отдельного кэша и веса суммируются в 1.
    Деньги: one_way * portfolio_value * cost_bps/10000, только если оба
    числа заданы. Иначе cash_cost = null.
    """
    names = set(current) | set(target)
    if not names or not current:
        return {
            "status": "no_current_portfolio",
            "gross_abs_weight_change": None,
            "one_way_turnover": None,
            "portfolio_share_traded": None,
            "cash_cost": None,
            "cash_cost_status": "insufficient_data",
            "formula": "one_way = 0.5 * sum(|w_target - w_current|)",
        }
    gross = 0.0
    for name in names:
        gross += abs(float(target.get(name, 0.0)) - float(current.get(name, 0.0)))
    one_way = 0.5 * gross
    cash = None
    cash_status = "insufficient_data"
    if cost_bps is not None and portfolio_value is not None:
        cash = one_way * float(portfolio_value) * float(cost_bps) / 10_000.0
        cash_status = "estimated"
    breached = max_turnover is not None and one_way > float(max_turnover) + 1e-12
    return {
        "status": "ok",
        "gross_abs_weight_change": gross,
        "one_way_turnover": one_way,
        "portfolio_share_traded": one_way,
        "cost_bps": cost_bps,
        "portfolio_value": portfolio_value,
        "cash_cost": cash,
        "cash_cost_status": cash_status,
        "max_turnover": max_turnover,
        "turnover_limit_breached": breached,
        "formula": "one_way = 0.5 * sum(|w_target - w_current|); cash = one_way * value * bps/10000",
    }


def current_weights_or_empty(holdings: dict[str, Any]) -> dict[str, float]:
    """Веса из holdings или {} для пустого портфеля."""
    if not holdings.get("positions"):
        return {}
    return weights_from_holdings(holdings)
