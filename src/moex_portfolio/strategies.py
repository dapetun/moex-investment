"""Сравнение Max Sharpe, Min Variance и 1/N на одной панели.

In-sample Sharpe не объявляется победителем. Holdout считает те же веса
на второй половине доходностей, без переоптимизации.
"""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from .metrics import sharpe_ratio
from .optimizer import (
    equal_weight_portfolio,
    max_sharpe_portfolio,
    min_variance_portfolio,
)
from .risk_models import covariance_matrix


def _price_returns(prices: pd.DataFrame) -> pd.DataFrame:
    cols = [c for c in prices.columns if not str(c).endswith("_VALUE")]
    return prices[cols].pct_change().dropna()


def compare_three_objectives(
    prices: pd.DataFrame,
    *,
    max_weight: float,
    max_top5: float | None = None,
    risk_free_rate: float = 0.0,
) -> dict[str, Any]:
    """Одинаковые данные, лимиты и ставка для трёх целей."""
    returns = _price_returns(prices)
    split = max(len(returns) // 2, 2)
    train = returns.iloc[:split]
    test = returns.iloc[split:]
    mean = train.mean()
    cov = covariance_matrix(train, method="sample")
    solvers = {
        "max_sharpe": max_sharpe_portfolio,
        "min_variance": min_variance_portfolio,
        "equal_weight": equal_weight_portfolio,
    }
    in_sample: dict[str, Any] = {}
    holdout: dict[str, Any] = {}
    for name, fn in solvers.items():
        opt = fn(
            mean,
            cov,
            risk_free_rate=risk_free_rate,
            max_weight=max_weight,
            max_top5=max_top5,
        )
        weights = np.asarray(opt["weights"], dtype=float)
        in_sample[name] = {
            "sharpe": opt["sharpe"],
            "volatility": opt["volatility"],
            "success": opt["success"],
            "sample": "in_sample",
        }
        if len(test) >= 2:
            holdout[name] = {
                "sharpe": float(
                    sharpe_ratio(weights, test.mean(), test.cov(), risk_free_rate)
                ),
                "sample": "out_of_sample_frozen_weights",
            }
    return {
        "in_sample": in_sample,
        "holdout": {
            "label": "out_of_sample_frozen_weights",
            "strategies": holdout,
        },
        "notes": "winner_by_in_sample_sharpe_is_not_a_decision",
        "risk_free_rate": risk_free_rate,
        "risk_free_rate_unit": "annual",
        "max_weight": max_weight,
        "max_top5": max_top5,
    }
