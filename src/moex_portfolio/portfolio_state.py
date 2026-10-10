"""Фактические позиции портфеля (holdings) — отдельно от результатов оптимизации.

Пустой портфель допустим. Не путать с profiles.py (снимок клики/весов оптимизатора).
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from .config import DATA_DIR

logger = logging.getLogger(__name__)

HOLDINGS_DIR = DATA_DIR / "portfolio"
HOLDINGS_FILENAME = "holdings.json"
WEIGHT_SUM_TOLERANCE = 1e-6


class HoldingsValidationError(ValueError):
    """Некорректная структура или содержимое holdings."""


def empty_holdings() -> dict[str, Any]:
    """Пустая конфигурация портфеля."""
    return {
        "as_of": None,
        "cash": 0.0,
        "positions": [],
    }


def holdings_path() -> Path:
    """Путь к файлу holdings.json."""
    return HOLDINGS_DIR / HOLDINGS_FILENAME


def validate_holdings(data: dict[str, Any]) -> None:
    """Проверка структуры holdings.

    Raises:
        HoldingsValidationError: при нарушении схемы или инвариантов.
    """
    if not isinstance(data, dict):
        raise HoldingsValidationError("holdings must be a dict")

    if "positions" not in data:
        raise HoldingsValidationError("missing 'positions'")

    positions = data["positions"]
    if not isinstance(positions, list):
        raise HoldingsValidationError("'positions' must be a list")

    cash = data.get("cash", 0.0)
    if cash is None:
        cash = 0.0
    try:
        cash_f = float(cash)
    except (TypeError, ValueError) as e:
        raise HoldingsValidationError("'cash' must be a number") from e
    if cash_f < 0:
        raise HoldingsValidationError("'cash' must be >= 0")

    seen: set[str] = set()
    weights: list[float] = []
    for i, pos in enumerate(positions):
        if not isinstance(pos, dict):
            raise HoldingsValidationError(f"position[{i}] must be a dict")
        ticker = pos.get("ticker")
        if not isinstance(ticker, str) or not ticker.strip():
            raise HoldingsValidationError(f"position[{i}]: empty ticker")
        ticker = ticker.strip().upper()
        if ticker in seen:
            raise HoldingsValidationError(f"duplicate ticker: {ticker}")
        seen.add(ticker)

        has_shares = pos.get("shares") is not None
        has_weight = pos.get("weight") is not None
        if not has_shares and not has_weight:
            raise HoldingsValidationError(
                f"position[{i}] ({ticker}): need shares and/or weight"
            )

        if has_shares:
            try:
                shares = float(pos["shares"])
            except (TypeError, ValueError) as e:
                raise HoldingsValidationError(
                    f"position[{i}] ({ticker}): invalid shares"
                ) from e
            if shares < 0:
                raise HoldingsValidationError(
                    f"position[{i}] ({ticker}): shares must be >= 0"
                )

        if has_weight:
            try:
                w = float(pos["weight"])
            except (TypeError, ValueError) as e:
                raise HoldingsValidationError(
                    f"position[{i}] ({ticker}): invalid weight"
                ) from e
            if w < 0:
                raise HoldingsValidationError(
                    f"position[{i}] ({ticker}): weight must be >= 0"
                )
            weights.append(w)

    if weights and abs(sum(weights) - 1.0) > WEIGHT_SUM_TOLERANCE:
        raise HoldingsValidationError(
            f"weights sum to {sum(weights):.6f}, expected 1.0"
        )


def _normalize(data: dict[str, Any]) -> dict[str, Any]:
    """Нормализация полей перед сохранением/возвратом."""
    positions = []
    for pos in data.get("positions", []):
        ticker = str(pos["ticker"]).strip().upper()
        item: dict[str, Any] = {"ticker": ticker, "note": str(pos.get("note") or "")}
        if pos.get("shares") is not None:
            item["shares"] = float(pos["shares"])
        if pos.get("weight") is not None:
            item["weight"] = float(pos["weight"])
        positions.append(item)

    cash = data.get("cash", 0.0)
    if cash is None:
        cash = 0.0

    return {
        "as_of": data.get("as_of"),
        "cash": float(cash),
        "positions": positions,
    }


def save_holdings(data: dict[str, Any], path: Path | None = None) -> Path:
    """Сохранить holdings в JSON после валидации."""
    validate_holdings(data)
    normalized = _normalize(data)
    validate_holdings(normalized)

    target = path or holdings_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        json.dumps(normalized, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    logger.info("Holdings saved: %s", target)
    return target


def load_holdings(path: Path | None = None) -> dict[str, Any]:
    """Загрузить holdings. Если файла нет — вернуть пустой портфель."""
    target = path or holdings_path()
    if not target.exists():
        logger.info("Holdings file missing, returning empty: %s", target)
        return empty_holdings()

    raw = json.loads(target.read_text(encoding="utf-8"))
    validate_holdings(raw)
    return _normalize(raw)


def weights_from_holdings(data: dict[str, Any]) -> dict[str, float]:
    """Извлечь явные веса. Без weight и без цен из shares — ошибка.

    Пустой портфель → {}.
    """
    validate_holdings(data)
    if not data["positions"]:
        return {}

    if all(p.get("weight") is not None for p in data["positions"]):
        return {
            str(p["ticker"]).strip().upper(): float(p["weight"])
            for p in data["positions"]
        }

    raise HoldingsValidationError(
        "cannot derive weights: positions have shares but no weights "
        "(provide weight fields or prices separately)"
    )
