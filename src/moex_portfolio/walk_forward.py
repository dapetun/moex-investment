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
    """Оставить календарь как есть. Пропуск не склеивается со следующим днём."""
    cols = [c for c in prices.columns if not str(c).endswith("_VALUE")]
    frame = prices[cols].sort_index()
    if start is not None:
        frame = frame.loc[frame.index >= pd.Timestamp(start)]
    if end is not None:
        frame = frame.loc[frame.index <= pd.Timestamp(end)]
    numeric = frame.apply(pd.to_numeric, errors="coerce")
    missing = int((~np.isfinite(numeric.to_numpy(dtype=float))).any(axis=1).sum())
    return numeric, missing


def _row_ok(row: pd.Series) -> bool:
    values = row.to_numpy(dtype=float)
    return bool(np.all(np.isfinite(values)) and np.all(values > 0))


def _failure_class(message: str) -> str:
    text = message.upper()
    if "INFEASIBLE" in text:
        return "infeasible_constraints"
    if "MISSING" in text or "INSUFFICIENT" in text:
        return "missing_data"
    return "solver_failure"


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


def _metrics(
    equity: list[float],
    net_daily: list[float],
    *,
    market_days: int,
    risk_free_rate: float,
) -> dict[str, Any]:
    """CAGR и Sharpe делят год на 252 рыночных дня, не на число списаний комиссии.

    Комиссия входит в ближайшую рыночную доходность, а не в лишний день.
    На коротком ряду это годовая условная ставка, не результат одного года.
    """
    if len(equity) < 2 or market_days < 1:
        return {
            "cumulative_net_return": None,
            "cagr": None,
            "annualized_volatility": None,
            "annualized_sharpe": None,
            "max_drawdown": None,
            "market_days": market_days,
        }
    net = float(equity[-1] / equity[0] - 1.0)
    cagr = float((equity[-1] / equity[0]) ** (252.0 / market_days) - 1.0)
    series = np.asarray(net_daily, dtype=float)
    vol = float(series.std(ddof=1) * np.sqrt(252.0)) if len(series) > 1 else 0.0
    ann_mean = float(series.mean() * 252.0) if len(series) else 0.0
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
        "market_days": market_days,
        "sharpe_formula": "(mean(net market-day return)*252 - annual_rf) / (std*sqrt(252))",
        "cagr_formula": "(final/initial)**(252/market_days) - 1",
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
        "rows_with_missing_prices": dropped,
        "n_price_rows": int(len(frame)),
        "execution_model": {
            "decision": "close of the decision date",
            "information_set": "complete closes through that date, inclusive",
            "fill": "same close",
            "spread_bps": 0,
            "slippage_bps": 0,
            "return_accrual": "new weights earn the next close-to-close return",
            "realistic_execution": False,
            "note": "Simplified close fill. Not an estimate of market execution.",
        },
        "fallback_policy": "keep drifted weights; stay in cash only if never formed",
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
            "failure_counts": {
                "solver_failure": 0,
                "infeasible_constraints": 0,
                "missing_data": 0,
            },
            "cash_days": 0,
            "market_days": 0,
            "pending_fee": 0.0,
            "max_weights": [],
            "top5": [],
            "steps": [],
        }
        for name in names
    }

    i = train_days - 1
    while i < len(frame) - 1:
        train = frame.iloc[i - train_days + 1 : i + 1]
        train_complete = bool(train.apply(_row_ok, axis=1).all())
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
            if do_trade and not train_complete:
                book["attempts"] += 1
                book["failures"] += 1
                book["failure_counts"]["missing_data"] += 1
                message = "missing_data"
                turnover_status = "missing_data"
            elif do_trade:
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
            failure_class = None
            if message == "missing_data":
                turnover_status = "missing_data"
                failure_class = "missing_data"
            else:
                turnover_status = "no_trade"
            if target is None and do_trade and message != "missing_data":
                book["failures"] += 1
                failure_class = _failure_class(message)
                book["failure_counts"][failure_class] += 1
                turnover_status = failure_class
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
                        book["pending_fee"] += cost / book["value"]
                        book["value"] -= cost
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
                    book["failure_counts"]["missing_data"] += 1
                    turnover_status = "missing_data"
                    continue
                asset_ret = cur / prev - 1.0
                in_cash = float(book["weights"].sum()) == 0.0
                if in_cash:
                    gross = 0.0
                    book["cash_days"] += 1
                else:
                    gross, drifted = _drift(book["weights"], asset_ret)
                    book["weights"] = drifted
                fee = float(book["pending_fee"])
                book["pending_fee"] = 0.0
                net = (1.0 - fee) * (1.0 + gross) - 1.0
                book["value"] *= 1.0 + gross
                book["equity"].append(book["value"])
                book["gross_daily"].append(gross)
                book["net_daily"].append(net)
                book["market_days"] += 1
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
                    "failure_class": failure_class,
                    "turnover_status": turnover_status,
                    "in_cash_after_decision": float(book["weights"].sum()) == 0.0,
                    "weights": None if target is None else [float(x) for x in target],
                    "one_way_turnover": one_way,
                    "cash_cost": cost,
                    "gross_period_return": float(np.prod(1.0 + np.asarray(step_gross)) - 1.0) if step_gross else 0.0,
                    "covariance_observations": diag.get("n_observations", diag.get("train_return_rows")),
                }
            )
        i = oos_end

    for name, book in books.items():
        metrics = _metrics(
            book["equity"],
            book["net_daily"],
            market_days=int(book["market_days"]),
            risk_free_rate=risk_free_rate,
        )
        attempts = int(book["attempts"])
        identity = None
        if book["net_daily"]:
            identity = float(np.prod(1.0 + np.asarray(book["net_daily"])) - 1.0)
        base["strategies"][name] = {
            **metrics,
            "one_way_turnover_sum": float(book["one_way"]),
            "total_cash_cost": float(book["costs"]),
            "formations": int(book["formations"]),
            "rebalances": int(book["rebalances"]),
            "failed_attempt_share": None if attempts == 0 else float(book["failures"] / attempts),
            "failure_counts": dict(book["failure_counts"]),
            "cash_day_share": (
                None if book["market_days"] == 0 else float(book["cash_days"] / book["market_days"])
            ),
            "return_identity_gap": (
                None if identity is None or metrics["cumulative_net_return"] is None
                else float(identity - metrics["cumulative_net_return"])
            ),
            "mean_max_weight": None if not book["max_weights"] else float(np.mean(book["max_weights"])),
            "mean_top5_sum": None if not book["top5"] else float(np.mean(book["top5"])),
            "final_value": float(book["value"]),
            "steps": book["steps"],
        }
    shares = [
        row["failed_attempt_share"]
        for row in base["strategies"].values()
        if row["failed_attempt_share"] is not None
    ]
    if shares and max(shares) - min(shares) > 0:
        base["comparison_warning"] = (
            "Strategies have different solver-failure shares; "
            "do not read the return gap as a pure strategy effect."
        )
    else:
        base["comparison_warning"] = None
    return base


def _quantile(values: list[float], q: float) -> float | None:
    if not values:
        return None
    return float(np.quantile(np.asarray(values, dtype=float), q))


def monte_carlo_compare(
    *,
    scenario: str,
    n_runs: int = 30,
    seed0: int = 1000,
    n_assets: int = 4,
    n_days: int = 80,
    train_days: int = 25,
    rebalance_every: int = 10,
    max_weight: float = 0.5,
    cost_bps: float = 0.0,
    risk_free_rate: float = 0.0,
) -> dict[str, Any]:
    """Несколько синтетических путей. Это не несколько лет реального рынка.

    На каждом seed все стратегии видят один и тот же ценовой путь.
    """
    if n_runs < 1:
        raise ValueError("n_runs must be positive")
    per_run: list[dict[str, Any]] = []
    for offset in range(n_runs):
        seed = seed0 + offset
        prices = synthetic_price_panel(scenario, n_assets=n_assets, n_days=n_days, seed=seed)
        report = walk_forward_compare(
            prices,
            train_days=train_days,
            rebalance_every=rebalance_every,
            max_weight=max_weight,
            cost_bps=cost_bps,
            risk_free_rate=risk_free_rate,
        )
        per_run.append(
            {
                "seed": seed,
                "strategies": report["strategies"],
                "warning": report["comparison_warning"],
            }
        )
    bench = [run["strategies"]["equal_weight"]["cumulative_net_return"] for run in per_run]
    summary: dict[str, Any] = {}
    for name in STRATEGIES:
        nets = [run["strategies"][name]["cumulative_net_return"] for run in per_run]
        finite_nets = [value for value in nets if value is not None]
        dds = [run["strategies"][name]["max_drawdown"] for run in per_run]
        turns = [run["strategies"][name]["one_way_turnover_sum"] for run in per_run]
        costs = [run["strategies"][name]["total_cash_cost"] for run in per_run]
        fails = [run["strategies"][name]["failed_attempt_share"] or 0.0 for run in per_run]
        gaps = [
            None if net is None or base_net is None else float(net - base_net)
            for net, base_net in zip(nets, bench)
        ]
        valid_gaps = [gap for gap in gaps if gap is not None]
        summary[name] = {
            "median_cumulative_net_return": _quantile(finite_nets, 0.5),
            "iqr_cumulative_net_return": [
                _quantile(finite_nets, 0.25),
                _quantile(finite_nets, 0.75),
            ],
            "median_max_drawdown": _quantile([value for value in dds if value is not None], 0.5),
            "median_one_way_turnover": _quantile(turns, 0.5),
            "median_cash_cost": _quantile(costs, 0.5),
            "median_failed_attempt_share": _quantile(fails, 0.5),
            "median_excess_vs_equal_weight": _quantile(valid_gaps, 0.5),
            "share_of_runs_ahead_of_equal_weight": (
                None
                if name == "equal_weight" or not valid_gaps
                else float(sum(gap > 0 for gap in valid_gaps) / len(valid_gaps))
            ),
        }
    return {
        "scenario": scenario,
        "n_runs": n_runs,
        "seed0": seed0,
        "seeds": [seed0 + offset for offset in range(n_runs)],
        "parameters": {
            "n_assets": n_assets,
            "n_days": n_days,
            "train_days": train_days,
            "rebalance_every": rebalance_every,
            "max_weight": max_weight,
            "cost_bps": cost_bps,
            "risk_free_rate": risk_free_rate,
        },
        "strategies": summary,
        "warning": "Independent synthetic paths, not independent years of a real market.",
    }
