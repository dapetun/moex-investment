#!/usr/bin/env python3
"""30 синтетических путей на сценарий. Не отбор удачных прогонов.

Запуск: python scripts/run_walk_forward_monte_carlo.py
"""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from moex_portfolio.walk_forward import monte_carlo_compare  # noqa: E402

OUT = ROOT / "docs" / "examples" / "walk_forward_monte_carlo.json"


ENGINE_COMMIT = "8dfea581853701ac0277cc9fa89c54b57b44b2bb"


def _engine_blob(rev: str) -> str:
    return subprocess.check_output(
        ["git", "rev-parse", f"{rev}:src/moex_portfolio/walk_forward.py"],
        cwd=ROOT,
        text=True,
    ).strip()


def _require_engine_commit() -> str:
    """SHA движка должен уже существовать и совпадать с текущим файлом."""
    head_blob = _engine_blob("HEAD")
    engine_blob = _engine_blob(ENGINE_COMMIT)
    if head_blob != engine_blob:
        raise SystemExit(
            "walk_forward.py differs from ENGINE_COMMIT; "
            "do not label results with a commit that does not contain this code"
        )
    return ENGINE_COMMIT


def _config_sha256() -> str:
    config = {
        "cost_bps": [0.0, 10.0],
        "cov_method": "sample",
        "max_weight": 0.5,
        "n_assets": 4,
        "n_days": 80,
        "n_runs": 30,
        "rebalance_every": 10,
        "risk_free_rate": 0.0,
        "scenarios": {"crash": 3000, "regime": 2000, "stable": 1000},
        "train_days": 25,
    }
    raw = json.dumps(config, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(raw).hexdigest()


def main() -> int:
    payload = {
        "code_sha": _require_engine_commit(),
        "code_sha_role": (
            "Existing commit of src/moex_portfolio/walk_forward.py that "
            "produced the scenario numbers. Not necessarily the commit that "
            "added this JSON."
        ),
        "disclaimer": (
            "30 independent synthetic paths per scenario. "
            "Not 30 years of the Russian market and not a selected subset."
        ),
        "execution_model": "same close, no spread, no slippage; realistic_execution=false",
        "config_sha256": _config_sha256(),
        "aggregation_note": (
            "median(strategy) - median(equal_weight) is not the median of "
            "paired differences. median_excess_vs_equal_weight is the paired median."
        ),
        "scenarios": {},
    }
    for scenario, seed0 in (("stable", 1000), ("regime", 2000), ("crash", 3000)):
        payload["scenarios"][scenario] = {
            "cost_bps_0": monte_carlo_compare(scenario=scenario, seed0=seed0, cost_bps=0.0),
            "cost_bps_10": monte_carlo_compare(
                scenario=scenario, seed0=seed0, cost_bps=10.0
            ),
        }
    OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(OUT)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
