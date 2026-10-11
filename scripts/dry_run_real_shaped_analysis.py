#!/usr/bin/env python3
"""Dry-run первого реального анализа на искусственных данных той же структуры.

Не ISS. Не пишет в git. Не печатает абсолютные домашние пути.
Останавливается на первой ошибке; изолированный tmp DATA_DIR.
"""

from __future__ import annotations

import json
import os
import shutil
import sys
import tempfile
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from moex_portfolio import cli  # noqa: E402
from moex_portfolio.data_sources import redact_local_path  # noqa: E402

TICKERS = ["RSH1", "RSH2", "RSH3"]


def _make_prices(path: Path, *, n: int = 90, seed: int = 42) -> None:
    rng = np.random.default_rng(seed)
    dates = pd.bdate_range(end="2026-10-09", periods=n)
    mu = np.array([0.12, 0.07, 0.04]) / 252
    vol = np.array([0.25, 0.16, 0.10]) / np.sqrt(252)
    corr = np.array([[1, 0.35, 0.15], [0.35, 1, 0.25], [0.15, 0.25, 1]])
    L = np.linalg.cholesky(np.outer(vol, vol) * corr)
    noise = rng.standard_normal((n, 3)) @ L.T
    noise = noise - noise.mean(axis=0, keepdims=True)
    rets = mu + noise
    p0 = np.array([200.0, 80.0, 40.0])
    prices = np.empty_like(rets)
    prices[0] = p0
    for i in range(1, n):
        prices[i] = prices[i - 1] * (1 + rets[i])
    cols: dict[str, np.ndarray] = {}
    for j, t in enumerate(TICKERS):
        cols[t] = np.round(prices[:, j], 4)
        cols[f"{t}_VALUE"] = np.full(n, 5.0e7)
    df = pd.DataFrame(cols, index=dates)
    df.index.name = "TRADEDATE"
    df.to_csv(path, sep=";")


def _make_portfolio(path: Path) -> None:
    rows = [
        "as_of_date,account_label,ticker,isin,secid,board,security_type,"
        "quantity,market_value,weight,notes",
        "2026-10-10,acc_a,RSH1,RU00RSH10001,RSH1,TQBR,share,100,200000,0.20,dry-run",
        "2026-10-10,acc_b,RSH1,RU00RSH10001,RSH1,TQBR,share,50,100000,0.10,dry-run",
        "2026-10-10,acc_a,RSH2,RU00RSH20002,RSH2,TQBR,share,200,250000,0.25,dry-run",
        "2026-10-10,acc_a,RSH3,RU00RSH30003,RSH3,TQBR,share,300,450000,0.45,dry-run",
    ]
    path.write_text("\n".join(rows) + "\n", encoding="utf-8")


def _patch_paths(work: Path, cache: Path) -> None:
    data = work / "data"
    data.mkdir(parents=True, exist_ok=True)
    import moex_portfolio.cli as cli_mod
    import moex_portfolio.config as cfg
    import moex_portfolio.events as events
    import moex_portfolio.locks as locks
    import moex_portfolio.portfolio_state as ps
    import moex_portfolio.reporting as reporting
    import moex_portfolio.run_journal as rj

    cfg.DATA_DIR = data
    ps.HOLDINGS_DIR = data / "portfolio"
    rj.RUNS_DIR = data / "outbox" / "runs"
    locks.LOCKS_DIR = data / "locks"
    reporting.REPORTS_DIR = data / "outbox" / "reports"
    cli_mod.LAST_TARGET_PATH = data / "outbox" / "last_target.json"
    events.apply_event_dirs(data_root=data)
    os.environ["MOEX_ISS_ENABLED"] = "false"
    os.environ["MOEX_DATA_SOURCE"] = "user_csv"
    os.environ["MOEX_USER_PRICES_PATH"] = str(cache)
    os.environ["MOEX_RUNTIME_CACHE"] = str(cache)
    os.environ.pop("MOEX_USER_CSV_SKIP_STALENESS", None)


def _redact_obj(obj: object, work: Path) -> object:
    if isinstance(obj, dict):
        return {k: _redact_obj(v, work) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_redact_obj(x, work) for x in obj]
    if isinstance(obj, str):
        s = obj.replace("\\", "/")
        home = str(Path.home()).replace("\\", "/")
        w = str(work).replace("\\", "/")
        s = s.replace(w, "<local>")
        s = s.replace(home, "<local>")
        return s
    return obj


def main() -> int:
    work = Path(tempfile.mkdtemp(prefix="moex-dry-real-"))
    prices = work / "user_prices.csv"
    portfolio = work / "portfolio.csv"
    cache = work / "runtime_prices.csv"
    _make_prices(prices)
    _make_portfolio(portfolio)
    _patch_paths(work, cache)

    report: dict = {
        "scenario": "dry_run_real_shaped",
        "ok": False,
        "work_dir": "<local>/moex-dry-real-*",
        "tickers": TICKERS,
        "steps": [],
    }

    def step(name: str, argv: list[str], *, expect: int = 0) -> bool:
        # capture stdout
        import io
        from contextlib import redirect_stderr, redirect_stdout

        buf_o, buf_e = io.StringIO(), io.StringIO()
        with redirect_stdout(buf_o), redirect_stderr(buf_e):
            code = cli.main(argv)
        entry: dict = {"step": name, "ok": code == expect, "exit": code, "expect": expect}
        raw = buf_o.getvalue().strip()
        if raw:
            try:
                entry["payload"] = _redact_obj(json.loads(raw), work)
            except json.JSONDecodeError:
                entry["stdout"] = redact_local_path(raw[:120])
        if code != expect:
            entry["stderr_tail"] = buf_e.getvalue()[-400:]
        report["steps"].append(entry)
        return entry["ok"]

    ok = True
    ok = step(
        "check-portfolio-ready",
        [
            "check-portfolio-ready",
            "--csv",
            str(portfolio),
            "--panel-tickers",
            ",".join(TICKERS),
        ],
    ) and ok
    if not ok:
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 1

    ok = step(
        "import-user-prices",
        [
            "import-user-prices",
            "--csv",
            str(prices),
            "--require-tickers",
            ",".join(TICKERS),
        ],
    ) and ok
    if not ok:
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 1

    fixture = ROOT / "data" / "fixtures" / "synthetic_prices_diversified.csv"
    ok = step(
        "refuse-fixture",
        ["import-user-prices", "--csv", str(fixture)],
        expect=4,
    ) and ok
    if not ok:
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 1

    # панель заканчивается 2026-10-09; при запуске 2026-10-11 достаточно 5 дней
    for name, argv in (
        ("validate-data", ["validate-data", "--max-staleness-days", "5"]),
        (
            "adapt-portfolio",
            [
                "adapt-portfolio",
                "--csv",
                str(portfolio),
                "--panel-tickers",
                ",".join(TICKERS),
                "--write-holdings",
            ],
        ),
        (
            "optimize",
            [
                "optimize",
                "--allow-optimize",
                "--mode",
                "holdings",
                "--max-weight",
                "0.5",
                "--max-staleness-days",
                "5",
            ],
        ),
        ("compare", ["compare", "--min-drift", "0.05"]),
        (
            "build-analyst-bundle",
            ["build-analyst-bundle", "--out-dir", str(work / "bundle")],
        ),
    ):
        if not step(name, argv):
            print(json.dumps(report, ensure_ascii=False, indent=2))
            return 1

    report["ok"] = all(s["ok"] for s in report["steps"])
    report["fail_safe"] = (
        "stop on first nonzero exit; isolated DATA_DIR; "
        "repo data/ not used as write target"
    )
    if report["ok"]:
        shutil.rmtree(work, ignore_errors=True)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
