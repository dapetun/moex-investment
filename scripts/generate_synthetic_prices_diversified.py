"""Сгенерировать детерминированную диверсифицированную синтетическую панель.

Не подгоняет веса оптимизатора: задаёт μ/σ/Corr, пишет CSV, печатает
факт результатов Max Sharpe для проверки.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from moex_portfolio.filters import compute_returns  # noqa: E402
from moex_portfolio.optimizer import max_sharpe_portfolio  # noqa: E402
from moex_portfolio.risk_models import covariance_matrix  # noqa: E402

SEED = 20261011
N_DAYS = 126  # ~6 месяцев торговых дней
TICKERS = ["AAA", "BBB", "CCC"]
# Годовые параметры (не равны → невырожденная задача)
MU_ANN = np.array([0.16, 0.09, 0.05])
VOL_ANN = np.array([0.30, 0.20, 0.12])
CORR = np.array(
    [
        [1.0, 0.40, 0.20],
        [0.40, 1.0, 0.30],
        [0.20, 0.30, 1.0],
    ]
)
P0 = np.array([100.0, 50.0, 20.0])
VALUE = np.array([1.0e8, 8.0e7, 6.0e7])


def build_panel() -> pd.DataFrame:
    rng = np.random.default_rng(SEED)
    dates = pd.bdate_range("2026-04-01", periods=N_DAYS)
    mu = MU_ANN / 252.0
    vol = VOL_ANN / np.sqrt(252.0)
    cov = np.outer(vol, vol) * CORR
    # симметризация + PD-проверка
    cov = 0.5 * (cov + cov.T)
    eig = np.linalg.eigvalsh(cov)
    if float(eig.min()) <= 0:
        raise RuntimeError(f"covariance not PD: eig={eig}")
    L = np.linalg.cholesky(cov)
    z = rng.standard_normal((N_DAYS, len(TICKERS)))
    # Шум с заданной cov; затем центрируем и добавляем точные mu,
    # чтобы выборочные средние не уезжали (не подгонка весов solver).
    noise = z @ L.T
    noise = noise - noise.mean(axis=0, keepdims=True)
    rets = mu + noise
    prices = np.empty_like(rets)
    prices[0] = P0
    for i in range(1, N_DAYS):
        prices[i] = prices[i - 1] * (1.0 + rets[i])
    cols: dict[str, np.ndarray] = {}
    for j, t in enumerate(TICKERS):
        cols[t] = np.round(prices[:, j], 6)
        cols[f"{t}_VALUE"] = np.full(N_DAYS, VALUE[j])
    df = pd.DataFrame(cols, index=dates)
    df.index.name = "TRADEDATE"
    return df


def summarize(df: pd.DataFrame) -> dict:
    rets = compute_returns(df[TICKERS])
    cov = covariance_matrix(rets, method="ledoit_wolf")
    # PD sample cov
    sample_eig = np.linalg.eigvalsh(rets.cov().values)
    opt = max_sharpe_portfolio(rets.mean(), cov, max_weight=0.5)
    weights = {t: float(w) for t, w in zip(TICKERS, opt["weights"], strict=True)}
    return {
        "mean_ann": (rets.mean() * 252).to_dict(),
        "vol_ann": (rets.std() * np.sqrt(252)).to_dict(),
        "corr": rets.corr().round(4).values.tolist(),
        "sample_cov_min_eig": float(sample_eig.min()),
        "weights": weights,
        "sharpe": float(opt["sharpe"]),
        "success": bool(opt["success"]),
        "weight_spread": float(max(opt["weights"]) - min(opt["weights"])),
    }


def main() -> int:
    fixtures = ROOT / "data" / "fixtures"
    fixtures.mkdir(parents=True, exist_ok=True)
    equal = fixtures / "synthetic_prices_equal_drift.csv"
    default = fixtures / "synthetic_prices.csv"
    diversified = fixtures / "synthetic_prices_diversified.csv"

    if default.exists() and not equal.exists():
        equal.write_bytes(default.read_bytes())
        print(f"archived equal-drift -> {equal.name}")

    df = build_panel()
    df.to_csv(diversified, sep=";")
    df.to_csv(default, sep=";")  # e2e / fixture default
    summary = summarize(df)
    print("wrote", diversified)
    print("wrote", default)
    print("summary", summary)
    if summary["sample_cov_min_eig"] <= 0:
        print("FAIL: sample cov not PD", file=sys.stderr)
        return 1
    if not summary["success"]:
        print("FAIL: optimizer unsuccessful", file=sys.stderr)
        return 1
    if summary["weight_spread"] < 0.05:
        print("FAIL: weights too similar", file=sys.stderr)
        return 1
    if summary["sharpe"] > 20:
        print("FAIL: sharpe still degenerate", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
