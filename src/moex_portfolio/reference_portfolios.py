"""Контрольные портфели без загрузки индексов и без ISS.

Внешний индекс принимается только как переданный ряд. Ценовой ряд не
помечается как полная доходность.
"""

from __future__ import annotations

from typing import Any

import pandas as pd


def _asset_prices(prices: pd.DataFrame) -> pd.DataFrame:
    cols = [c for c in prices.columns if not str(c).endswith("_VALUE")]
    return prices[cols].astype(float)


def reference_returns(
    prices: pd.DataFrame,
    *,
    start_weights: dict[str, float],
    cash_annual: float = 0.0,
    external_index: pd.Series | None = None,
    external_index_kind: str = "unspecified",
) -> dict[str, Any]:
    """Buy-and-hold, равные веса и кэш на общих датах."""
    panel = _asset_prices(prices).dropna(how="any")
    names = list(start_weights)
    missing = [n for n in names if n not in panel.columns]
    if missing:
        raise ValueError(f"missing price columns: {missing}")
    sub = panel[names]
    rets = sub.pct_change().dropna()
    w0 = pd.Series(start_weights, dtype=float)
    w0 = w0 / w0.sum()
    growth = sub / sub.iloc[0]
    bh_level = growth.mul(w0, axis=1).sum(axis=1)
    bh = bh_level.pct_change().dropna()
    equal = rets.mean(axis=1)
    cash = pd.Series(cash_annual / 252.0, index=rets.index)
    external: dict[str, Any]
    if external_index is None:
        external = {"status": "not_provided", "kind": None}
    else:
        aligned = external_index.reindex(rets.index)
        external = {
            "status": "aligned_inner",
            "kind": external_index_kind,
            "n_overlapping": int(aligned.notna().sum()),
            "labeled_total_return": external_index_kind == "total_return",
        }
    return {
        "buy_and_hold": {"rule": "weights drift with price, no rebalance", "n": int(len(bh))},
        "equal_weight": {"rule": "daily mean of simple returns, constant 1/N", "n": int(len(equal))},
        "cash": {
            "rule": "constant daily cash_annual/252",
            "annual_rate": cash_annual,
            "n": int(len(cash)),
        },
        "external_index": external,
    }
