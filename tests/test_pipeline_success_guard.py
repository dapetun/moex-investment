"""Регрессии: отсутствующий success solver и пост-валидация весов."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from moex_portfolio.numeric import NumericValidationError
from moex_portfolio.pipeline import run_optimize

FIXTURE = Path(__file__).resolve().parents[1] / "data" / "fixtures" / "synthetic_prices.csv"


@pytest.fixture
def prices():
    return pd.read_csv(FIXTURE, sep=";", index_col="TRADEDATE", parse_dates=True)


def test_missing_success_flag_is_failure(prices, monkeypatch):
    def _omit_success(*_a, **_k):
        return {
            "weights": np.array([0.5, 0.3, 0.2]),
            "return": 0.1,
            "volatility": 0.2,
            "sharpe": 0.5,
            "message": "ok but no flag",
        }

    monkeypatch.setattr("moex_portfolio.pipeline.max_sharpe_portfolio", _omit_success)
    result = run_optimize(prices, max_weight=0.5, min_turnover=0.0)
    assert result["success"] is False
    assert "success flag" in result["message"].lower() or "omitted" in result["message"].lower()


def test_invalid_max_weight_rejected(prices):
    with pytest.raises(NumericValidationError):
        run_optimize(prices, max_weight=0.0, min_turnover=0.0)
    with pytest.raises(NumericValidationError):
        run_optimize(prices, max_weight=1.5, min_turnover=0.0)


def test_post_solver_rejects_bad_weights(prices, monkeypatch):
    def _bad_weights(*_a, **_k):
        return {
            "weights": np.array([2.0, -1.0, 0.0]),
            "return": 0.1,
            "volatility": 0.2,
            "sharpe": 0.5,
            "success": True,
            "message": "force bad",
        }

    monkeypatch.setattr("moex_portfolio.pipeline.max_sharpe_portfolio", _bad_weights)
    result = run_optimize(prices, max_weight=0.5, min_turnover=0.0)
    assert result["success"] is False
    assert "post-solver" in result["message"]
