"""Адаптер фактического портфеля аналитика (CSV) → канон CLI holdings.json.

Не мигрирует и не перезаписывает ``/workspace/invest/portfolio/portfolio.csv``.
Канон CLI: ``data/portfolio/holdings.json`` (ticker + явные weight и/или shares).

Контракт (предложение → подтверждение Grok Bot cur-20261010-1936):
1. Факт для CLI — holdings.json; CSV аналитика — внешний read-only источник.
2. ISIN/SECID → ticker только при однозначном сопоставлении (колонка ticker,
   либо SECID=тикер, либо явная карта ``isin_to_ticker``).
3. Канон весов после адаптера: сумма ≈ 1.0 (±1e-6). Вход CSV аналитика
   допускает ±0.005 с явной нормализацией (``weight_normalized``).
4. Одинаковый SECID на нескольких счетах → консолидация с ``accounts[]``;
   веса с разными знаменателями не суммируются.
5. Missing file ≠ empty positions (см. ``file_status`` в portfolio_state).
6. Тикер вне ценовой панели — флаг ``missing_from_panel``, вес не выдумывается.
7. Compare: одни ключи ticker и одна база явных весов.
"""

from __future__ import annotations

import csv
import logging
import re
from pathlib import Path
from typing import Any

from .numeric import NumericValidationError, require_nonnegative_finite
from .portfolio_state import (
    ANALYST_WEIGHT_SUM_TOLERANCE,
    WEIGHT_SUM_TOLERANCE,
    HoldingsValidationError,
    empty_holdings,
    validate_holdings,
)

logger = logging.getLogger(__name__)


class PortfolioAdapterError(ValueError):
    """Ошибка чтения/нормализации внешнего портфеля."""


def _cell(row: dict[str, str], *names: str) -> str | None:
    lower = {k.strip().lower(): v for k, v in row.items() if k is not None}
    for name in names:
        val = lower.get(name.lower())
        if val is not None and str(val).strip():
            return str(val).strip()
    return None


def resolve_ticker(
    row: dict[str, str],
    *,
    isin_to_ticker: dict[str, str] | None = None,
) -> str:
    """Ключ позиции для CLI = SECID (RESULT 1936 §1.2.c), не CSV-ticker облигации.

    Порядок: secid → карта ISIN→ticker → CSV ticker только если нет secid.
    """
    secid = _cell(row, "secid", "SECID")
    if secid:
        # облигации: secid часто = ISIN; акции: secid = тикер панели
        return secid.upper()

    isin = _cell(row, "isin", "ISIN")
    if isin and isin_to_ticker:
        mapped = isin_to_ticker.get(isin.upper()) or isin_to_ticker.get(isin)
        if mapped:
            return str(mapped).strip().upper()

    ticker = _cell(row, "ticker", "symbol", "secid_ticker")
    if ticker and re_fullmatch_ticker(ticker):
        return ticker.upper()

    raise PortfolioAdapterError(
        f"ambiguous instrument identity: need secid or unambiguous ISIN/ticker "
        f"mapping (isin={isin!r}, secid={secid!r}; code=PORTFOLIO_ID_AMBIGUOUS)"
    )


def re_fullmatch_ticker(value: str) -> bool:
    """SECID как тикер акции: буквы/цифры без пробелов, не ISIN."""
    s = value.strip().upper()
    if re.fullmatch(r"[A-Z]{2}[A-Z0-9]{9}[0-9]", s):
        return False  # ISIN
    return bool(re.fullmatch(r"[A-Z0-9._-]{1,32}", s))


def csv_row_to_position(
    row: dict[str, str],
    *,
    isin_to_ticker: dict[str, str] | None = None,
) -> dict[str, Any] | None:
    """Одна строка CSV → позиция holdings. None = строка cash/пропуск."""
    kind = (_cell(row, "type", "security_type", "asset_class") or "").lower()
    if kind in {"cash", "money", "currency"}:
        return None

    ticker_hint = _cell(row, "ticker", "symbol", "secid", "isin")
    if ticker_hint and ticker_hint.upper() in {"CASH", "RUB", "USD", "EUR"}:
        return None

    ticker = resolve_ticker(row, isin_to_ticker=isin_to_ticker)
    pos: dict[str, Any] = {
        "ticker": ticker,
        "note": _cell(row, "note", "notes", "name") or "",
    }
    sec_type = _cell(row, "security_type", "type")
    if sec_type and sec_type.lower() not in {"cash", "money", "currency"}:
        pos["security_type"] = sec_type.lower()
    account = _cell(row, "account_label", "account")
    if account:
        pos["account_label"] = account

    isin = _cell(row, "isin", "ISIN")
    if isin:
        pos["isin"] = isin.upper()
    secid = _cell(row, "secid", "SECID")
    if secid:
        pos["secid"] = secid.upper()
    board = _cell(row, "board", "boardid")
    if board:
        pos["board"] = board.upper()

    w_raw = _cell(row, "weight", "w", "target_weight")
    q_raw = _cell(row, "quantity", "shares", "qty", "amount")
    if w_raw is None and q_raw is None:
        raise PortfolioAdapterError(
            f"position {ticker}: need weight and/or quantity/shares "
            f"(code=PORTFOLIO_ROW_INCOMPLETE)"
        )
    if w_raw is not None:
        try:
            pos["weight"] = require_nonnegative_finite(float(w_raw.replace(",", ".")), "weight")
        except (NumericValidationError, ValueError) as e:
            raise PortfolioAdapterError(f"position {ticker}: bad weight: {e}") from e
    if q_raw is not None:
        try:
            pos["shares"] = require_nonnegative_finite(
                float(q_raw.replace(",", ".")), "shares"
            )
        except (NumericValidationError, ValueError) as e:
            raise PortfolioAdapterError(f"position {ticker}: bad shares: {e}") from e
    mv_raw = _cell(row, "market_value", "marketvalue")
    if mv_raw is not None:
        try:
            pos["market_value"] = require_nonnegative_finite(
                float(mv_raw.replace(",", ".")), "market_value"
            )
        except (NumericValidationError, ValueError) as e:
            raise PortfolioAdapterError(f"position {ticker}: bad market_value: {e}") from e
    return pos


def _account_ref(pos: dict[str, Any]) -> dict[str, Any]:
    """Ссылка на исходный счёт для консолидированной позиции."""
    ref: dict[str, Any] = {}
    if pos.get("account_label"):
        ref["account_label"] = pos["account_label"]
    if pos.get("weight") is not None:
        ref["weight"] = float(pos["weight"])
    if pos.get("shares") is not None:
        ref["shares"] = float(pos["shares"])
    if pos.get("market_value") is not None:
        ref["market_value"] = float(pos["market_value"])
    return ref


def _merge_same_secid(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Слить строки с одним SECID/ticker с разных счетов.

    Допустимо: суммировать portfolio-level weights (один знаменатель) или
    market_value (затем пересчёт весов по всему портфелю). Иначе — ошибка.
    """
    ticker = rows[0]["ticker"]
    has_w = [r.get("weight") is not None for r in rows]
    has_s = [r.get("shares") is not None for r in rows]
    has_mv = [r.get("market_value") is not None for r in rows]

    if any(has_w) and not all(has_w):
        raise PortfolioAdapterError(
            f"cannot consolidate {ticker}: mixed weight presence across accounts "
            f"(code=PORTFOLIO_CONSOLIDATION_AMBIGUOUS)"
        )
    if any(has_s) and not all(has_s):
        raise PortfolioAdapterError(
            f"cannot consolidate {ticker}: mixed shares presence across accounts "
            f"(code=PORTFOLIO_CONSOLIDATION_AMBIGUOUS)"
        )
    if any(has_mv) and not all(has_mv):
        raise PortfolioAdapterError(
            f"cannot consolidate {ticker}: mixed market_value across accounts "
            f"(code=PORTFOLIO_CONSOLIDATION_AMBIGUOUS)"
        )

    # market_value — предпочтительная база (один денежный знаменатель).
    use_mv = all(has_mv)
    use_w = all(has_w) and not use_mv
    if not use_mv and not use_w and not all(has_s):
        raise PortfolioAdapterError(
            f"cannot consolidate {ticker}: need shared weight or market_value basis "
            f"(code=PORTFOLIO_CONSOLIDATION_AMBIGUOUS)"
        )

    merged: dict[str, Any] = {
        "ticker": ticker,
        "note": "; ".join(
            dict.fromkeys(str(r.get("note") or "") for r in rows if r.get("note"))
        ),
        "accounts": [_account_ref(r) for r in rows],
    }
    for key in ("isin", "secid", "board", "security_type"):
        vals = {r[key] for r in rows if r.get(key)}
        if len(vals) > 1:
            raise PortfolioAdapterError(
                f"cannot consolidate {ticker}: conflicting {key}={sorted(vals)} "
                f"(code=PORTFOLIO_CONSOLIDATION_AMBIGUOUS)"
            )
        if len(vals) == 1:
            merged[key] = next(iter(vals))

    if all(has_s):
        merged["shares"] = sum(float(r["shares"]) for r in rows)
    if use_mv:
        merged["market_value"] = sum(float(r["market_value"]) for r in rows)
        merged["_weight_basis"] = "market_value"
    elif use_w:
        # Веса аналитика — доли одного портфеля; сумма по счетам корректна.
        merged["weight"] = sum(float(r["weight"]) for r in rows)
        merged["_weight_basis"] = "portfolio_weight"
    if any(r.get("missing_from_panel") for r in rows):
        merged["missing_from_panel"] = True
    return merged


def consolidate_positions(positions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Агрегировать одинаковый SECID; сохранить связь со счетами."""
    order: list[str] = []
    groups: dict[str, list[dict[str, Any]]] = {}
    for pos in positions:
        t = pos["ticker"]
        if t not in groups:
            order.append(t)
            groups[t] = []
        groups[t].append(pos)

    out: list[dict[str, Any]] = []
    for t in order:
        rows = groups[t]
        if len(rows) == 1:
            out.append(rows[0])
        else:
            out.append(_merge_same_secid(rows))
    return out


def _apply_market_value_weights(positions: list[dict[str, Any]]) -> None:
    """Пересчитать weight из market_value, если база консолидации — MV."""
    if not any(p.get("_weight_basis") == "market_value" for p in positions):
        return
    if not all(p.get("market_value") is not None for p in positions):
        raise PortfolioAdapterError(
            "cannot recompute weights: market_value missing on some positions "
            "after consolidation (code=PORTFOLIO_CONSOLIDATION_AMBIGUOUS)"
        )
    total = sum(float(p["market_value"]) for p in positions)
    if total <= 0:
        raise PortfolioAdapterError(
            "cannot recompute weights: total market_value <= 0 "
            "(code=PORTFOLIO_CONSOLIDATION_AMBIGUOUS)"
        )
    for p in positions:
        p["weight"] = float(p["market_value"]) / total
        p.pop("_weight_basis", None)


def _normalize_analyst_weights(
    positions: list[dict[str, Any]],
) -> tuple[float | None, bool]:
    """Явная нормализация legacy-суммы весов в пределах ANALYST_WEIGHT_SUM_TOLERANCE.

    Returns:
        (sum_before, normalized_flag). sum_before is None if no weights.
    """
    weighted = [p for p in positions if p.get("weight") is not None]
    if not weighted:
        return None, False
    if len(weighted) != len(positions):
        # уже отсечено PORTFOLIO_MIXED_WEIGHTS выше
        return None, False
    total = sum(float(p["weight"]) for p in positions)
    gap = abs(total - 1.0)
    if gap > ANALYST_WEIGHT_SUM_TOLERANCE:
        raise PortfolioAdapterError(
            f"weights sum to {total:.6f}, expected 1.0 "
            f"±{ANALYST_WEIGHT_SUM_TOLERANCE} (code=PORTFOLIO_WEIGHT_SUM)"
        )
    if gap <= WEIGHT_SUM_TOLERANCE:
        return total, False
    for p in positions:
        p["weight"] = float(p["weight"]) / total
    return total, True


def extract_cash_from_rows(rows: list[dict[str, str]]) -> float:
    """Сумма денежных строк (type=cash или ticker=CASH)."""
    total = 0.0
    for row in rows:
        kind = (_cell(row, "type", "security_type", "asset_class") or "").lower()
        ticker = (_cell(row, "ticker", "symbol", "secid") or "").upper()
        if kind in {"cash", "money", "currency"} or ticker in {"CASH", "RUB"}:
            for key in ("quantity", "amount", "value", "cash", "shares"):
                raw = _cell(row, key)
                if raw is not None:
                    try:
                        total += float(raw.replace(",", "."))
                    except ValueError as e:
                        raise PortfolioAdapterError(
                            f"bad cash amount {raw!r}"
                        ) from e
                    break
    return total


def adapt_analyst_csv(
    path: Path | str,
    *,
    isin_to_ticker: dict[str, str] | None = None,
    as_of: str | None = None,
    cash: float | None = None,
    panel_tickers: set[str] | None = None,
) -> dict[str, Any]:
    """Прочитать CSV аналитика → структура holdings (без записи на диск).

    Returns:
        holdings-совместимый dict + ``adapter`` метаданные.
    """
    csv_path = Path(path)
    if not csv_path.exists():
        raise PortfolioAdapterError(
            f"portfolio CSV not found: {csv_path} (code=PORTFOLIO_CSV_MISSING)"
        )
    if not csv_path.is_file():
        raise PortfolioAdapterError(
            f"portfolio CSV path is not a file: {csv_path} (code=PORTFOLIO_CSV_INVALID)"
        )

    with csv_path.open(encoding="utf-8-sig", newline="") as fh:
        reader = csv.DictReader(fh)
        if not reader.fieldnames:
            raise PortfolioAdapterError(
                "portfolio CSV has no header (code=PORTFOLIO_CSV_INVALID)"
            )
        rows = list(reader)

    # as_of_date из CSV (одинаковое во всех строках) если не передан явно
    if as_of is None:
        as_ofs = {
            _cell(r, "as_of", "as_of_date", "date")
            for r in rows
            if _cell(r, "as_of", "as_of_date", "date")
        }
        if len(as_ofs) == 1:
            as_of = next(iter(as_ofs))
        elif len(as_ofs) > 1:
            raise PortfolioAdapterError(
                f"conflicting as_of_date values in CSV: {sorted(as_ofs)} "
                f"(code=PORTFOLIO_ASOF_CONFLICT)"
            )

    positions: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []
    for i, row in enumerate(rows):
        try:
            kind = (_cell(row, "type", "security_type") or "").lower()
            ticker_cell = (_cell(row, "ticker", "symbol") or "").upper()
            if kind in {"cash", "money", "currency"} or ticker_cell in {"CASH", "RUB"}:
                continue
            if not any(str(v or "").strip() for v in row.values()):
                continue
            pos = csv_row_to_position(row, isin_to_ticker=isin_to_ticker)
            if pos is None:
                continue
            if panel_tickers is not None:
                if pos["ticker"] not in {t.upper() for t in panel_tickers}:
                    pos["missing_from_panel"] = True
            positions.append(pos)
        except PortfolioAdapterError as e:
            errors.append({"row": i, "error": str(e)})

    # Любая битая строка позиции — отказ всего файла (RESULT 2002 §3.3)
    if errors:
        raise PortfolioAdapterError(
            f"portfolio CSV row errors ({len(errors)}): {errors[0]['error']} "
            f"(code=PORTFOLIO_ROW_ERRORS)"
        )
    if not positions:
        raise PortfolioAdapterError(
            "no valid positions in portfolio CSV (code=PORTFOLIO_CSV_EMPTY)"
        )

    has_w = [p.get("weight") is not None for p in positions]
    if any(has_w) and not all(has_w):
        raise PortfolioAdapterError(
            "mixed weight/shares rows: weight required on all rows or none "
            "(code=PORTFOLIO_MIXED_WEIGHTS)"
        )

    positions = consolidate_positions(positions)
    _apply_market_value_weights(positions)
    weight_sum_before, weight_normalized = _normalize_analyst_weights(positions)
    for p in positions:
        p.pop("_weight_basis", None)

    cash_val = float(cash) if cash is not None else extract_cash_from_rows(rows)
    holdings: dict[str, Any] = {
        "as_of": as_of,
        "cash": cash_val,
        "positions": [
            {k: v for k, v in p.items() if k != "missing_from_panel"}
            for p in positions
        ],
    }
    try:
        validate_holdings(holdings)
    except HoldingsValidationError as e:
        raise PortfolioAdapterError(str(e)) from e

    missing = [p["ticker"] for p in positions if p.get("missing_from_panel")]
    status = "ok" if positions else "empty"
    holdings["file_status"] = status
    weight_basis = "explicit_position_weights"
    if any(p.get("accounts") for p in positions):
        weight_basis = "consolidated_portfolio_weights"
    return {
        **holdings,
        "adapter": {
            "source_path": str(csv_path.resolve()),
            "source_format": "analyst_csv",
            "weight_basis": weight_basis,
            "cash_in_weight_sum": False,
            "weight_sum_tolerance": WEIGHT_SUM_TOLERANCE,
            "analyst_weight_sum_tolerance": ANALYST_WEIGHT_SUM_TOLERANCE,
            "weight_sum_before": weight_sum_before,
            "weight_normalized": weight_normalized,
            "row_errors": errors,
            "missing_from_panel": missing,
            "file_status": status,
        },
    }


def holdings_for_compare(holdings: dict[str, Any]) -> dict[str, float]:
    """Явные веса для compare; проверяет единую базу."""
    from .portfolio_state import weights_from_holdings

    return weights_from_holdings(
        {
            "as_of": holdings.get("as_of"),
            "cash": holdings.get("cash", 0.0),
            "positions": holdings.get("positions", []),
        }
    )


def empty_adapted() -> dict[str, Any]:
    h = empty_holdings()
    h["adapter"] = {
        "source_format": "none",
        "file_status": "empty",
        "cash_in_weight_sum": False,
    }
    return h
