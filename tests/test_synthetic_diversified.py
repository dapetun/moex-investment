"""Устойчивость Max Sharpe на диверсифицированной синтетической панели."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from moex_portfolio.filters import compute_returns
from moex_portfolio.optimizer import max_sharpe_portfolio
from moex_portfolio.risk_models import covariance_matrix

ROOT = Path(__file__).resolve().parents[1]
DIV = ROOT / "data" / "fixtures" / "synthetic_prices_diversified.csv"
EQUAL = ROOT / "data" / "fixtures" / "synthetic_prices_equal_drift.csv"
TICKERS = ["AAA", "BBB", "CCC"]


@pytest.fixture(scope="module")
def prices() -> pd.DataFrame:
    assert DIV.exists(), "run scripts/generate_synthetic_prices_diversified.py"
    df = pd.read_csv(DIV, sep=";", index_col="TRADEDATE", parse_dates=True)
    return df[TICKERS]


def test_cov_positive_definite(prices: pd.DataFrame) -> None:
    rets = compute_returns(prices)
    eig = np.linalg.eigvalsh(rets.cov().values)
    assert float(eig.min()) > 0


def test_correlations_moderate_not_one(prices: pd.DataFrame) -> None:
    corr = compute_returns(prices).corr()
    off = corr.values[np.triu_indices(3, k=1)]
    assert float(np.max(np.abs(off))) < 0.85
    assert float(np.min(np.abs(off))) > 0.05


def test_max_sharpe_unequal_weights_and_bounds(prices: pd.DataFrame) -> None:
    rets = compute_returns(prices)
    cov = covariance_matrix(rets, method="ledoit_wolf")
    max_w = 0.5
    res = max_sharpe_portfolio(rets.mean(), cov, max_weight=max_w)
    assert res["success"] is True
    w = np.asarray(res["weights"], dtype=float)
    assert abs(float(w.sum()) - 1.0) < 1e-6
    assert float(w.min()) >= -1e-9
    assert float(w.max()) <= max_w + 1e-6
    assert float(w.max() - w.min()) > 0.05
    assert float(res["sharpe"]) < 20.0


def test_result_stable_across_reload(prices: pd.DataFrame) -> None:
    def once() -> np.ndarray:
        rets = compute_returns(prices)
        cov = covariance_matrix(rets, method="ledoit_wolf")
        return np.asarray(
            max_sharpe_portfolio(rets.mean(), cov, max_weight=0.5)["weights"],
            dtype=float,
        )

    w1, w2 = once(), once()
    assert np.allclose(w1, w2, atol=1e-9)


def test_equal_drift_archive_still_degenerate() -> None:
    """Старая панель сохранена для регрессии: corr≈1 → почти равные веса."""
    assert EQUAL.exists()
    df = pd.read_csv(EQUAL, sep=";", index_col="TRADEDATE", parse_dates=True)[TICKERS]
    rets = compute_returns(df)
    corr_off = rets.corr().values[np.triu_indices(3, k=1)]
    assert float(np.min(corr_off)) > 0.99
    cov = covariance_matrix(rets, method="ledoit_wolf")
    res = max_sharpe_portfolio(rets.mean(), cov, max_weight=0.5)
    w = np.asarray(res["weights"], dtype=float)
    assert float(np.max(np.abs(w - 1.0 / 3.0))) < 0.02
