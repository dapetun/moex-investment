"""Фактические позиции портфеля (holdings) — отдельно от результатов оптимизации.

Пустой портфель допустим. Не путать с profiles.py (снимок клики/весов оптимизатора).

Ограничение (MVP): ``compare`` / ``weights_from_holdings`` требуют явного поля
``weight`` у каждой позиции. Позиции только с ``shares`` без весов не оцениваются:
рыночные веса по количеству бумаг и котировкам — отдельная будущая задача
(без выдумывания весов и без нового источника данных в этом этапе).
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from .config import DATA_DIR
from .numeric import NumericValidationError, require_nonnegative_finite

logger = logging.getLogger(__name__)

HOLDINGS_DIR = DATA_DIR / "portfolio"
HOLDINGS_FILENAME = "holdings.json"
# Канон CLI / результат оптимизатора: сумма весов ≈ 1.0 (±1e-6).
WEIGHT_SUM_TOLERANCE = 1e-6
# Вход CSV аналитика: допуск шире; адаптер может явно нормализовать (см. portfolio_adapter).
ANALYST_WEIGHT_SUM_TOLERANCE = 5e-3

# Политика суммы весов в holdings.json.
# ``canonical`` — строгий допуск 1e-6 (по умолчанию и для target).
# ``legacy_analyst`` — явный маркер старого файла: при load допускается ±0.005
# с нормализацией только в памяти (файл на диск не перезаписывается).
WEIGHT_SUM_POLICY_CANONICAL = "canonical"
WEIGHT_SUM_POLICY_LEGACY_ANALYST = "legacy_analyst"
_WEIGHT_SUM_POLICIES = frozenset(
    {WEIGHT_SUM_POLICY_CANONICAL, WEIGHT_SUM_POLICY_LEGACY_ANALYST}
)

# Метаданные позиции, сохраняемые при load/save (PORTFOLIO_CONTRACT / RESULT 1936).
_POSITION_OPTIONAL_KEYS = (
    "isin",
    "secid",
    "board",
    "security_type",
    "account_label",
    "accounts",
    "market_value",
)


class HoldingsValidationError(ValueError):
    """Некорректная структура или содержимое holdings."""


def empty_holdings(*, file_status: str = "empty") -> dict[str, Any]:
    """Пустая конфигурация портфеля.

    ``file_status``:
    - ``empty`` — файл есть (или явное пустое состояние), позиций нет;
    - ``missing`` — файла нет (не путать с пустым портфелем).
    """
    return {
        "as_of": None,
        "cash": 0.0,
        "positions": [],
        "file_status": file_status,
    }


def holdings_path() -> Path:
    """Путь к файлу holdings.json."""
    return HOLDINGS_DIR / HOLDINGS_FILENAME


def _weight_sum_policy(data: dict[str, Any]) -> str:
    policy = data.get("weight_sum_policy", WEIGHT_SUM_POLICY_CANONICAL)
    if policy is None:
        return WEIGHT_SUM_POLICY_CANONICAL
    if not isinstance(policy, str) or policy not in _WEIGHT_SUM_POLICIES:
        raise HoldingsValidationError(
            f"unknown weight_sum_policy={policy!r}; "
            f"allowed: {sorted(_WEIGHT_SUM_POLICIES)} "
            f"(code=HOLDINGS_WEIGHT_POLICY_INVALID)"
        )
    return policy


def _normalize_legacy_weights_in_memory(
    data: dict[str, Any],
) -> tuple[float | None, bool]:
    """Нормализовать веса legacy_analyst в памяти (±0.005).

    Не записывает файл. Target/optimize результаты сюда не попадают —
    у них нет ``weight_sum_policy=legacy_analyst``.
    """
    positions = data.get("positions") or []
    weighted = [p for p in positions if isinstance(p, dict) and p.get("weight") is not None]
    if not weighted or len(weighted) != len(positions):
        return None, False
    total = sum(float(p["weight"]) for p in weighted)
    gap = abs(total - 1.0)
    if gap <= WEIGHT_SUM_TOLERANCE:
        return total, False
    if gap > ANALYST_WEIGHT_SUM_TOLERANCE:
        raise HoldingsValidationError(
            f"legacy weights sum to {total:.6f}, expected 1.0 "
            f"±{ANALYST_WEIGHT_SUM_TOLERANCE} (code=HOLDINGS_WEIGHT_SUM)"
        )
    for p in weighted:
        p["weight"] = float(p["weight"]) / total
    return total, True


def validate_holdings(
    data: dict[str, Any],
    *,
    weight_tolerance: float | None = None,
) -> None:
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

    _weight_sum_policy(data)

    cash = data.get("cash", 0.0)
    if cash is None:
        cash = 0.0
    try:
        require_nonnegative_finite(cash, "cash")
    except NumericValidationError as e:
        raise HoldingsValidationError(str(e)) from e

    tol = WEIGHT_SUM_TOLERANCE if weight_tolerance is None else weight_tolerance

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
            raise HoldingsValidationError(
                f"duplicate ticker: {ticker} (code=HOLDINGS_DUPLICATE_TICKER); "
                f"multi-account SECID must be consolidated by adapt-portfolio"
            )
        seen.add(ticker)

        has_shares = pos.get("shares") is not None
        has_weight = pos.get("weight") is not None
        if not has_shares and not has_weight:
            raise HoldingsValidationError(
                f"position[{i}] ({ticker}): need shares and/or weight"
            )

        if has_shares:
            try:
                require_nonnegative_finite(pos["shares"], f"position[{i}].shares")
            except NumericValidationError as e:
                raise HoldingsValidationError(str(e)) from e

        if has_weight:
            try:
                w = require_nonnegative_finite(pos["weight"], f"position[{i}].weight")
            except NumericValidationError as e:
                raise HoldingsValidationError(str(e)) from e
            weights.append(w)

    if weights and abs(sum(weights) - 1.0) > tol:
        raise HoldingsValidationError(
            f"weights sum to {sum(weights):.6f}, expected 1.0 "
            f"±{tol} (code=HOLDINGS_WEIGHT_SUM)"
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
        for key in _POSITION_OPTIONAL_KEYS:
            if pos.get(key) is None:
                continue
            val = pos[key]
            if key in {"isin", "secid", "board"} and isinstance(val, str):
                item[key] = val.strip().upper()
            elif key == "security_type" and isinstance(val, str):
                item[key] = val.strip().lower()
            elif key == "account_label" and isinstance(val, str):
                item[key] = val.strip()
            elif key == "accounts" and isinstance(val, list):
                item[key] = val
            elif key == "market_value":
                item[key] = float(val)
            else:
                item[key] = val
        positions.append(item)

    cash = data.get("cash", 0.0)
    if cash is None:
        cash = 0.0

    status = data.get("file_status")
    if status not in {"ok", "empty", "missing"}:
        status = "ok" if positions else "empty"
    out: dict[str, Any] = {
        "as_of": data.get("as_of"),
        "cash": float(cash),
        "positions": positions,
        "file_status": status,
    }
    policy = data.get("weight_sum_policy")
    if policy in _WEIGHT_SUM_POLICIES:
        out["weight_sum_policy"] = policy
    return out


def save_holdings(data: dict[str, Any], path: Path | None = None) -> Path:
    """Сохранить holdings в JSON после валидации.

    Сохранение всегда требует канонической суммы весов (±1e-6).
    ``legacy_analyst`` не ослабляет запись — только чтение в памяти.
    """
    validate_holdings(data, weight_tolerance=WEIGHT_SUM_TOLERANCE)
    normalized = _normalize(data)
    # На диске канон: убираем legacy-маркер, чтобы не маскировать будущие ошибки.
    normalized.pop("weight_sum_policy", None)
    validate_holdings(normalized, weight_tolerance=WEIGHT_SUM_TOLERANCE)

    target = path or holdings_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        json.dumps(normalized, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    logger.info("Holdings saved: %s", target)
    return target


def load_holdings(path: Path | None = None) -> dict[str, Any]:
    """Загрузить holdings.

    Файл отсутствует → ``file_status=missing`` (позиции []).
    Файл с пустыми positions → ``file_status=empty``.
    Непустой портфель → ``file_status=ok``.

    При явном ``weight_sum_policy=legacy_analyst`` допускается сумма ±0.005
    с нормализацией **только в возвращаемом объекте**; исходный файл не меняется.
    Отклонение суммы само по себе не делает файл legacy.
    """
    target = path or holdings_path()
    if not target.exists():
        logger.info("Holdings file missing (status=missing): %s", target)
        return empty_holdings(file_status="missing")

    raw = json.loads(target.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise HoldingsValidationError("holdings must be a dict")

    policy = _weight_sum_policy(raw)
    normalized = _normalize(raw)
    normalized["weight_sum_policy"] = policy

    weight_sum_before: float | None = None
    weight_normalized_on_load = False
    if policy == WEIGHT_SUM_POLICY_LEGACY_ANALYST:
        # Сначала мягкая проверка, затем нормализация в памяти.
        validate_holdings(normalized, weight_tolerance=ANALYST_WEIGHT_SUM_TOLERANCE)
        weight_sum_before, weight_normalized_on_load = _normalize_legacy_weights_in_memory(
            normalized
        )
        validate_holdings(normalized, weight_tolerance=WEIGHT_SUM_TOLERANCE)
    else:
        validate_holdings(normalized, weight_tolerance=WEIGHT_SUM_TOLERANCE)

    if not normalized["positions"]:
        normalized["file_status"] = "empty"
    else:
        normalized["file_status"] = "ok"
    if weight_sum_before is not None:
        normalized["weight_sum_before"] = weight_sum_before
        normalized["weight_normalized_on_load"] = weight_normalized_on_load
        normalized["weight_sum_after"] = sum(
            float(p["weight"])
            for p in normalized["positions"]
            if p.get("weight") is not None
        )
    return normalized


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
        "cannot derive weights from shares-only positions: "
        "every position must include explicit 'weight' for compare/optimize "
        "in the current MVP. "
        "Market-value weights from shares×prices are a future task "
        "(code=HOLDINGS_SHARES_WITHOUT_WEIGHTS)."
    )
