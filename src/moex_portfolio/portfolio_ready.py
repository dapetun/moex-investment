"""Предварительная проверка готовности портфеля без запуска оптимизатора."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .portfolio_adapter import PortfolioAdapterError, adapt_analyst_csv
from .portfolio_state import (
    HoldingsValidationError,
    load_holdings,
    weights_from_holdings,
)

REQUIRED_CSV_COLUMNS = (
    "as_of_date",
    "account_label",
    "ticker",
    "isin",
    "secid",
    "board",
    "security_type",
    "quantity",
    "market_value",
    "weight",
)


def check_portfolio_ready(
    *,
    csv_path: Path | None = None,
    holdings_path: Path | None = None,
    panel_tickers: set[str] | None = None,
    isin_to_ticker: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Проверить портфель CSV и/или holdings без optimize.

    Возвращает машиночитаемый отчёт: ok, checks[], blockers[], warnings[],
    what_user_must_provide[], what_can_be_derived[].
    """
    checks: list[dict[str, Any]] = []
    blockers: list[str] = []
    warnings: list[str] = []
    holdings: dict[str, Any] | None = None

    def add(name: str, ok: bool, detail: str, *, block: bool = False) -> None:
        checks.append({"name": name, "ok": ok, "detail": detail})
        if not ok and block:
            blockers.append(f"{name}: {detail}")
        elif not ok:
            warnings.append(f"{name}: {detail}")

    if csv_path is None and holdings_path is None:
        add(
            "input",
            False,
            "нужен --csv и/или существующий holdings.json",
            block=True,
        )
        return _report(False, checks, blockers, warnings, None)

    if csv_path is not None:
        if not csv_path.exists():
            add("csv_exists", False, f"файл не найден: {csv_path}", block=True)
        else:
            add("csv_exists", True, str(csv_path))
            try:
                holdings = adapt_analyst_csv(
                    csv_path,
                    isin_to_ticker=isin_to_ticker,
                    panel_tickers=panel_tickers,
                )
                add(
                    "csv_adapt",
                    True,
                    f"позиций={len(holdings.get('positions') or [])}",
                )
                adapter = holdings.get("adapter") or {}
                if adapter.get("weight_normalized"):
                    warnings.append(
                        "csv_weight_normalized: сумма весов была "
                        f"{adapter.get('weight_sum_before')}, нормализована адаптером"
                    )
                missing = adapter.get("missing_from_panel") or []
                if missing:
                    add(
                        "panel_coverage",
                        False,
                        f"тикеры вне панели: {missing}",
                        block=True,
                    )
                else:
                    add(
                        "panel_coverage",
                        True,
                        "все тикеры в панели"
                        if panel_tickers
                        else "панель не задана (проверка покрытия пропущена)",
                    )
                # согласованность weight vs MV
                _check_weight_vs_mv(holdings, add, warnings)
            except (PortfolioAdapterError, HoldingsValidationError, OSError) as e:
                add("csv_adapt", False, str(e), block=True)

    if csv_path is None:
        try:
            loaded = load_holdings()
            status = loaded.get("file_status") or "ok"
            if status == "missing":
                add("holdings_file", False, "holdings.json отсутствует", block=True)
            elif status == "empty":
                add("holdings_file", False, "holdings.json пуст", block=True)
            else:
                add("holdings_file", True, f"status={status}")
                holdings = loaded
                try:
                    w = weights_from_holdings(loaded)
                    add(
                        "holdings_weights",
                        True,
                        f"n={len(w)} sum={sum(w.values()):.6f}",
                    )
                except HoldingsValidationError as e:
                    add("holdings_weights", False, str(e), block=True)
        except HoldingsValidationError as e:
            add("holdings_file", False, str(e), block=True)

    ok = not blockers
    return _report(ok, checks, blockers, warnings, holdings)


def _check_weight_vs_mv(
    holdings: dict[str, Any],
    add: Any,
    warnings: list[str],
) -> None:
    positions = holdings.get("positions") or []
    with_mv = [p for p in positions if p.get("market_value") is not None]
    if len(with_mv) != len(positions) or not positions:
        add("weight_vs_mv", True, "MV неполное — сверка пропущена")
        return
    total = sum(float(p["market_value"]) for p in with_mv)
    if total <= 0:
        add("weight_vs_mv", False, "сумма market_value <= 0", block=True)
        return
    mismatches: list[str] = []
    for p in with_mv:
        w = float(p.get("weight") or 0.0)
        share = float(p["market_value"]) / total
        if abs(w - share) > 0.01:
            mismatches.append(
                f"{p.get('ticker')}: weight={w:.4f} mv_share={share:.4f}"
            )
    if mismatches:
        add(
            "weight_vs_mv",
            False,
            "расхождение >1 п.п.: " + "; ".join(mismatches),
        )
        warnings.append(
            "weight_vs_mv: явные weight имеют приоритет, но расхождение с MV "
            "нужно устранить до доверия к ребалансировке"
        )
    else:
        add("weight_vs_mv", True, "веса согласованы с MV (±1 п.п.)")


def _report(
    ok: bool,
    checks: list[dict[str, Any]],
    blockers: list[str],
    warnings: list[str],
    holdings: dict[str, Any] | None,
) -> dict[str, Any]:
    return {
        "ok": ok,
        "ready_for_optimize": ok,
        "checks": checks,
        "blockers": blockers,
        "warnings": warnings,
        "n_positions": len((holdings or {}).get("positions") or []),
        "required_csv_columns": list(REQUIRED_CSV_COLUMNS),
        "what_user_must_provide": [
            "CSV портфеля (или канонический holdings.json) с SECID/ISIN, "
            "весами и/или quantity+market_value",
            "as_of_date позиций",
            "ценовую панель по тикерам портфеля (user_csv или иной разрешённый источник)",
        ],
        "what_can_be_derived": [
            "консолидация multi-account по SECID",
            "нормализация весов CSV в допуске ±0.005 (с явным флагом)",
            "QC панели, Max Sharpe, compare, analyst bundle — после ready",
            "корпоративные события — отдельный ingest, не вход solver",
        ],
        "holdings_preview": {
            "as_of": (holdings or {}).get("as_of"),
            "cash": (holdings or {}).get("cash"),
            "tickers": [
                p.get("ticker") for p in ((holdings or {}).get("positions") or [])
            ],
        }
        if holdings
        else None,
    }
