#!/usr/bin/env python3
"""Локальный синтетический пример walk-forward. Не вызывает ботов и не пишет target.

Запуск из корня репозитория:
    python scripts/run_walk_forward_example.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from moex_portfolio.walk_forward import (  # noqa: E402
    synthetic_price_panel,
    walk_forward_compare,
)

OUT = ROOT / "docs" / "examples" / "walk_forward_synthetic.json"


def _summary(report: dict) -> dict:
    rows = {}
    for name, row in report.get("strategies", {}).items():
        rows[name] = {
            key: row.get(key)
            for key in (
                "cumulative_net_return",
                "cagr",
                "annualized_volatility",
                "annualized_sharpe",
                "max_drawdown",
                "one_way_turnover_sum",
                "total_cash_cost",
                "formations",
                "rebalances",
                "failed_attempt_share",
                "mean_max_weight",
                "final_value",
            )
        }
    return {
        "status": report["status"],
        "performance_sample": report["performance_sample"],
        "parameters": report["parameters"],
        "strategies": rows,
    }


def main() -> int:
    payload = {
        "disclaimer": "Synthetic prices only. Not an estimate of the Russian market.",
        "scenarios": {},
        "sensitivity_stable": [],
    }
    for kind, seed in (("stable", 11), ("regime", 12), ("crash", 13)):
        prices = synthetic_price_panel(kind, n_assets=4, n_days=140, seed=seed)
        payload["scenarios"][kind] = {}
        for bps in (0.0, 10.0):
            report = walk_forward_compare(
                prices,
                train_days=40,
                rebalance_every=10,
                max_weight=0.5,
                risk_free_rate=0.0,
                cost_bps=bps,
                cov_method="sample",
            )
            payload["scenarios"][kind][f"cost_bps_{int(bps)}"] = _summary(report)
    stable = synthetic_price_panel("stable", n_assets=4, n_days=140, seed=11)
    for train, every in ((30, 5), (30, 20), (60, 10)):
        report = walk_forward_compare(
            stable,
            train_days=train,
            rebalance_every=every,
            max_weight=0.5,
            cost_bps=0.0,
        )
        item = _summary(report)
        item["train_days"] = train
        item["rebalance_every"] = every
        payload["sensitivity_stable"].append(item)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(OUT)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
