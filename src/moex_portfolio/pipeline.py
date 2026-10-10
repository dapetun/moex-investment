"""Оркестрация headless-расчётов без Streamlit.

Математика оптимизатора не изменяется — вызываются существующие функции.
"""

from __future__ import annotations

import logging
from typing import Any

import numpy as np
import pandas as pd

from .config import MAX_WEIGHT
from .filters import prepare_returns
from .optimizer import max_sharpe_portfolio
from .portfolio_state import HoldingsValidationError, weights_from_holdings
from .risk_models import covariance_matrix

logger = logging.getLogger(__name__)


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
        min_turnover: Порог оборота (0 для синтетики).
        mode: ``universe`` — все ликвидные тикеры фикстуры;
            ``holdings`` — только тикеры из holdings (непустые).
        holdings: Структура holdings для mode=holdings.

    Returns:
        weights (dict), metrics, tickers, success, message, mode.
    """
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

    weights_arr = np.asarray(opt["weights"], dtype=float)
    weights = {t: float(w) for t, w in zip(valid, weights_arr, strict=True)}

    return {
        "mode": mode,
        "tickers": valid,
        "weights": weights,
        "return": float(opt["return"]),
        "volatility": float(opt["volatility"]),
        "sharpe": float(opt["sharpe"]),
        "success": bool(opt.get("success", True)),
        "message": str(opt.get("message", "")),
        "risk_free_rate": risk_free_rate,
        "max_weight": max_weight,
        "cov_method": cov_method,
    }


def current_weights_or_empty(holdings: dict[str, Any]) -> dict[str, float]:
    """Веса из holdings или {} для пустого портфеля."""
    if not holdings.get("positions"):
        return {}
    return weights_from_holdings(holdings)
