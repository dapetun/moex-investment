"""Сравнение текущих и целевых весов портфеля (без брокера)."""

from __future__ import annotations

from typing import Any


def compare_weights(
    current: dict[str, float],
    target: dict[str, float],
    min_drift: float = 0.05,
) -> dict[str, Any]:
    """Сравнить веса и решить, нужен ли ребаланс по порогу drift.

    Args:
        current: Фактические веса.
        target: Целевые веса.
        min_drift: Порог абсолютного отклонения по любому тикеру.

    Returns:
        needs_rebalance, max_abs_drift, diffs, tickers, min_drift.
    """
    tickers = sorted(set(current) | set(target))
    diffs = []
    max_abs = 0.0
    for t in tickers:
        c = float(current.get(t, 0.0))
        tg = float(target.get(t, 0.0))
        drift = abs(c - tg)
        max_abs = max(max_abs, drift)
        diffs.append(
            {
                "ticker": t,
                "current": c,
                "target": tg,
                "drift": drift,
            }
        )

    return {
        "needs_rebalance": max_abs >= min_drift,
        "max_abs_drift": max_abs,
        "min_drift": min_drift,
        "diffs": diffs,
        "tickers": tickers,
    }
