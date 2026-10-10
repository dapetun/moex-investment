"""Адаптер фактического портфеля аналитика (CSV) → канон CLI holdings.json.

Не мигрирует и не перезаписывает ``/workspace/invest/portfolio/portfolio.csv``.
Канон CLI: ``data/portfolio/holdings.json`` (ticker + явные weight и/или shares).

Контракт (предложение → подтверждение Grok Bot cur-20261010-1936):
1. Факт для CLI — holdings.json; CSV аналитика — внешний read-only источник.
2. ISIN/SECID → ticker только при однозначном сопоставлении (колонка ticker,
   либо SECID=тикер, либо явная карта ``isin_to_ticker``).
3. Веса позиций суммируются в 1.0 (±1e-6); ``cash`` — абсолютная сумма вне весов.
4. Missing file ≠ empty positions (см. ``file_status`` в portfolio_state).
5. Тикер вне ценовой панели — флаг ``missing_from_panel``, вес не выдумывается.
6. Compare: одни ключи ticker и одна база явных весов.
"""

from __future__ import annotations

import csv
import logging
import re
from pathlib import Path
from typing import Any

from .numeric import NumericValidationError, require_nonnegative_finite
from .portfolio_state import (
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
    return pos


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
    p = Path(path)
    if not p.exists():
        raise PortfolioAdapterError(
            f"portfolio CSV not found: {p} (code=PORTFOLIO_CSV_MISSING)"
        )
    if not p.is_file():
        raise PortfolioAdapterError(
            f"portfolio CSV path is not a file: {p} (code=PORTFOLIO_CSV_INVALID)"
        )

    with p.open(encoding="utf-8-sig", newline="") as fh:
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
    return {
        **holdings,
        "adapter": {
            "source_path": str(p.resolve()),
            "source_format": "analyst_csv",
            "weight_basis": "explicit_position_weights",
            "cash_in_weight_sum": False,
            "weight_sum_tolerance": WEIGHT_SUM_TOLERANCE,
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
