"""Walk-forward сравнение стратегий. Отдельно от CLI optimize.

Производительность в отчёте — out-of-sample. Окна оценки — in-sample и не
пересекаются с тестовыми доходностями. Старый walk_forward_backtest не
используется: там нет дрейфа весов и оборот считается полной L1.
"""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from .compare import assess_turnover
from .optimizer import (
    InfeasibleWeightConstraints,
    equal_weight_portfolio,
    max_sharpe_portfolio,
    min_variance_portfolio,
)
from .risk_models import covariance_matrix

STRATEGIES = ("max_sharpe", "min_variance", "equal_weight", "buy_and_hold")
_SOLVERS = {
    "max_sharpe": max_sharpe_portfolio,
    "min_variance": min_variance_portfolio,
    "equal_weight": equal_weight_portfolio,
}


def synthetic_price_panel(
    kind: str,
    *,
    n_assets: int = 4,
    n_days: int = 120,
    seed: int = 0,
) -> pd.DataFrame:
    """Синтетические уровни цен. Это не рынок РФ."""
    rng = np.random.default_rng(seed)
    idx = pd.bdate_range("2020-01-01", periods=n_days)
    if kind == "stable":
        rets = rng.normal(0.0003, 0.008, size=(n_days, n_assets))
    elif kind == "regime":
        rets = rng.normal(0.0002, 0.01, size=(n_days, n_assets))
        half = n_days // 2
        rets[half:, 0] -= 0.0015
        rets[half:, 1] += 0.0015
        factor = rng.normal(0.0, 0.012, size=n_days - half)
        rets[half:] += factor[:, None]
    elif kind == "crash":
        rets = rng.normal(0.0001, 0.02, size=(n_days, n_assets))
        start = n_days // 2
        rets[start : start + 5] = -0.06
    else:
        raise ValueError(f"unknown scenario: {kind}")
    levels = 100.0 * np.exp(np.cumsum(rets, axis=0))
    return pd.DataFrame(levels, index=idx, columns=[f"A{i}" for i in range(n_assets)])


def _prepare_prices(
    prices: pd.DataFrame,
    *,
    start: str | None,
    end: str | None,
) -> tuple[pd.DataFrame, int]:
    cols = [c for c in prices.columns if not str(c).endswith("_VALUE")]
    frame = prices[cols].sort_index()
    if start is not None:
        frame = frame.loc[frame.index >= pd.Timestamp(start)]
    if end is not None:
        frame = frame.loc[frame.index <= pd.Timestamp(end)]
    before = len(frame)
    frame = frame.dropna(how="any")
    return frame.astype(float), before - len(frame)


def _train_returns(train_prices: pd.DataFrame) -> pd.DataFrame:
    return train_prices.pct_change().dropna(how="any")


def _targets(
    train_prices: pd.DataFrame,
    strategy: str,
    *,
    max_weight: float,
    max_top5: float | None,
    risk_free_rate: float,
    cov_method: str,
) -> tuple[np.ndarray | None, str, dict[str, Any]]:
    rets = _train_returns(train_prices)
    diag: dict[str, Any] = {}
    if len(rets) < 2:
        return None, "insufficient_train_returns", diag
    cov = covariance_matrix(rets, method=cov_method, diagnostics=diag)
    diag["train_return_rows"] = int(len(rets))
    mean = rets.mean()
    try:
        if strategy == "buy_and_hold":
            solved = equal_weight_portfolio(
                mean, cov, risk_free_rate=risk_free_rate, max_weight=max_weight, max_top5=max_top5
            )
        else:
            solved = _SOLVERS[strategy](
                mean, cov, risk_free_rate=risk_free_rate, max_weight=max_weight, max_top5=max_top5
            )
    except InfeasibleWeightConstraints as exc:
        return None, str(exc), diag
    if solved.get("success") is not True:
        return None, str(solved.get("message") or "solver_failed"), diag
    return np.asarray(solved["weights"], dtype=float), "ok", diag


def _drift(weights: np.ndarray, asset_returns: np.ndarray) -> tuple[float, np.ndarray]:
    gross = float(np.dot(weights, asset_returns))
    grown = weights * (1.0 + asset_returns)
    total = float(grown.sum())
    if total <= 0 or not np.isfinite(total):
        return gross, weights.copy()
    return gross, grown / total


def _metrics(equity: list[float], net_daily: list[float], *, risk_free_rate: float) -> dict[str, Any]:
    if len(equity) < 2 or not net_daily:
        return {
            "cumulative_net_return": None,
            "cagr": None,
            "annualized_volatility": None,
            "annualized_sharpe": None,
            "max_drawdown": None,
        }
    net = float(equity[-1] / equity[0] - 1.0)
    n_days = len(net_daily)
    cagr = float((equity[-1] / equity[0]) ** (252.0 / max(n_days, 1)) - 1.0)
    series = np.asarray(net_daily, dtype=float)
    vol = float(series.std(ddof=1) * np.sqrt(252.0)) if n_days > 1 else 0.0
    ann_mean = float(series.mean() * 252.0)
    sharpe = None if vol == 0 else float((ann_mean - risk_free_rate) / vol)
    peak = equity[0]
    max_dd = 0.0
    for value in equity:
        peak = max(peak, value)
        if peak > 0:
            max_dd = min(max_dd, value / peak - 1.0)
    return {
        "cumulative_net_return": net,
        "cagr": cagr,
        "annualized_volatility": vol,
        "annualized_sharpe": sharpe,
        "max_drawdown": float(max_dd),
        "sharpe_formula": "(mean(net daily)*252 - annual_rf) / (std(net daily)*sqrt(252))",
    }


def walk_forward_compare(
    prices: pd.DataFrame,
    *,
    train_days: int = 40,
    rebalance_every: int = 10,
    start: str | None = None,
    end: str | None = None,
    strategies: list[str] | None = None,
    max_weight: float = 0.5,
    max_top5: float | None = None,
    risk_free_rate: float = 0.0,
    cost_bps: float = 0.0,
    initial_capital: float = 1.0,
    cov_method: str = "sample",
) -> dict[str, Any]:
    """Сравнить стратегии на одном календаре без look-ahead.

    Equal Weight возвращается к 1/N только в даты пересмотра.
    Buy-and-hold после первого формирования сделок не делает.
    Отчётная доходность — out-of-sample. Окна оценки помечены in-sample.
    """
    names = list(strategies or STRATEGIES)
    unknown = [s for s in names if s not in STRATEGIES]
    if unknown:
        raise ValueError(f"unknown strategies: {unknown}")
    if train_days < 3 or rebalance_every < 1:
        raise ValueError("train_days >= 3 and rebalance_every >= 1 are required")

    frame, dropped = _prepare_prices(prices, start=start, end=end)
    columns = list(frame.columns)
    base: dict[str, Any] = {
        "status": "ok",
        "performance_sample": "out_of_sample",
        "estimation_sample": "in_sample_windows",
        "parameters": {
            "train_days": train_days,
            "rebalance_every": rebalance_every,
            "start": None if start is None else str(start),
            "end": None if end is None else str(end),
            "max_weight": max_weight,
            "max_top5": max_top5,
            "risk_free_rate": risk_free_rate,
            "risk_free_rate_unit": "annual",
            "cost_bps": cost_bps,
            "initial_capital": initial_capital,
            "cov_method": cov_method,
            "strategies": names,
        },
        "rows_dropped_for_missing_prices": dropped,
        "n_price_rows": int(len(frame)),
        "strategies": {},
    }
    if len(frame) < train_days + 1:
        base["status"] = "insufficient_observations"
        return base

    books = {
        name: {
            "weights": np.zeros(len(columns)),
            "formed": False,
            "value": float(initial_capital),
            "equity": [float(initial_capital)],
            "gross_daily": [],
            "net_daily": [],
            "one_way": 0.0,
            "costs": 0.0,
            "formations": 0,
            "rebalances": 0,
            "attempts": 0,
            "failures": 0,
            "max_weights": [],
            "top5": [],
            "steps": [],
        }
        for name in names
    }

    i = train_days - 1
    while i < len(frame) - 1:
        train = frame.iloc[i - train_days + 1 : i + 1]
        oos_end = min(i + rebalance_every, len(frame) - 1)
        decision = frame.index[i]
        oos_start = frame.index[i + 1]
        if train.index.max() >= oos_start:
            raise RuntimeError("train window overlaps the first out-of-sample date")
        for name in names:
            book = books[name]
            do_trade = not (name == "buy_and_hold" and book["formed"])
            target = None
            message = "held"
            diag: dict[str, Any] = {}
            if do_trade:
                book["attempts"] += 1
                target, message, diag = _targets(
                    train,
                    name,
                    max_weight=max_weight,
                    max_top5=max_top5,
                    risk_free_rate=risk_free_rate,
                    cov_method=cov_method,
                )
            one_way = None
            cost = 0.0
            turnover_status = "no_trade"
            if target is None and do_trade:
                book["failures"] += 1
                turnover_status = "solver_failed"
            elif target is not None:
                current = {col: float(w) for col, w in zip(columns, book["weights"])}
                tgt = {col: float(w) for col, w in zip(columns, target)}
                cash_current = None if book["formed"] else 1.0
                cash_target = None if book["formed"] else 0.0
                if not book["formed"]:
                    current = dict.fromkeys(columns, 0.0)
                assessed = assess_turnover(
                    current,
                    tgt,
                    cash_current=cash_current,
                    cash_target=cash_target,
                    cost_bps=cost_bps,
                    portfolio_value=book["value"],
                )
                turnover_status = str(assessed["status"])
                if assessed["one_way_identified"] and assessed["one_way_turnover"] is not None:
                    one_way = float(assessed["one_way_turnover"])
                    cost = float(assessed["cash_cost"] or 0.0)
                    if cost and book["value"] > 0:
                        cost_return = -cost / book["value"]
                        book["value"] -= cost
                        book["net_daily"].append(cost_return)
                        book["equity"].append(book["value"])
                    book["costs"] += cost
                    book["one_way"] += one_way
                    book["weights"] = target
                    if book["formed"]:
                        book["rebalances"] += 1
                    else:
                        book["formations"] += 1
                        book["formed"] = True
                    book["max_weights"].append(float(np.max(target)))
                    k = min(5, len(target))
                    book["top5"].append(float(np.sort(target)[::-1][:k].sum()))
                else:
                    book["failures"] += 1
            step_gross = []
            for j in range(i + 1, oos_end + 1):
                prev = frame.iloc[j - 1].to_numpy(dtype=float)
                cur = frame.iloc[j].to_numpy(dtype=float)
                if np.any(prev <= 0) or not np.all(np.isfinite(cur)) or not np.all(np.isfinite(prev)):
                    book["failures"] += 1
                    turnover_status = "missing_or_invalid_price"
                    break
                asset_ret = cur / prev - 1.0
                if float(book["weights"].sum()) == 0.0:
                    gross = 0.0
                else:
                    gross, drifted = _drift(book["weights"], asset_ret)
                    book["weights"] = drifted
                book["value"] *= 1.0 + gross
                book["equity"].append(book["value"])
                book["gross_daily"].append(gross)
                book["net_daily"].append(gross)
                step_gross.append(gross)
            book["steps"].append(
                {
                    "decision_date": str(pd.Timestamp(decision).date()),
                    "train_start": str(pd.Timestamp(train.index[0]).date()),
                    "train_end": str(pd.Timestamp(train.index[-1]).date()),
                    "oos_start": str(pd.Timestamp(oos_start).date()),
                    "oos_end": str(pd.Timestamp(frame.index[oos_end]).date()),
                    "estimation": "in_sample",
                    "performance": "out_of_sample",
                    "status": message if do_trade else "buy_and_hold_no_further_trades",
                    "turnover_status": turnover_status,
                    "weights": None if target is None else [float(x) for x in target],
                    "one_way_turnover": one_way,
                    "cash_cost": cost,
                    "gross_period_return": float(np.prod(1.0 + np.asarray(step_gross)) - 1.0) if step_gross else 0.0,
                    "covariance_observations": diag.get("n_observations", diag.get("train_return_rows")),
                }
            )
        i = oos_end

    for name, book in books.items():
        metrics = _metrics(book["equity"], book["net_daily"], risk_free_rate=risk_free_rate)
        attempts = int(book["attempts"])
        base["strategies"][name] = {
            **metrics,
            "one_way_turnover_sum": float(book["one_way"]),
            "total_cash_cost": float(book["costs"]),
            "formations": int(book["formations"]),
            "rebalances": int(book["rebalances"]),
            "failed_attempt_share": None if attempts == 0 else float(book["failures"] / attempts),
            "mean_max_weight": None if not book["max_weights"] else float(np.mean(book["max_weights"])),
            "mean_top5_sum": None if not book["top5"] else float(np.mean(book["top5"])),
            "final_value": float(book["value"]),
            "steps": book["steps"],
        }
    return base
