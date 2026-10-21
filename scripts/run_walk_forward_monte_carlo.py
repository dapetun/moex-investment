#!/usr/bin/env python3
"""30 синтетических путей на сценарий. Не отбор удачных прогонов.

Запуск: python scripts/run_walk_forward_monte_carlo.py
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from moex_portfolio.walk_forward import monte_carlo_compare  # noqa: E402

OUT = ROOT / "docs" / "examples" / "walk_forward_monte_carlo.json"


def _sha() -> str:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
        ).strip()
    except (OSError, subprocess.CalledProcessError):
        return "unknown"


def main() -> int:
    payload = {
        "code_sha": _sha(),
        "disclaimer": (
            "30 independent synthetic paths per scenario. "
            "Not 30 years of the Russian market and not a selected subset."
        ),
        "execution_model": "same close, no spread, no slippage",
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
