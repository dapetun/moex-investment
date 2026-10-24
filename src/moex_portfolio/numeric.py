"""Строгие проверки конечных числовых значений для портфельных расчётов."""

from __future__ import annotations

import math
from typing import Any


class NumericValidationError(ValueError):
    """Неконечное или недопустимое число."""


def require_finite_number(value: Any, name: str, *, allow_none: bool = False) -> float:
    """Преобразовать в float и отвергнуть NaN/Inf/нечисло."""
    if value is None:
        if allow_none:
            raise NumericValidationError(f"{name} is None")
        raise NumericValidationError(f"{name} is required")
    try:
        x = float(value)
    except (TypeError, ValueError) as e:
        raise NumericValidationError(f"{name} is not a number: {value!r}") from e
    if not math.isfinite(x):
        raise NumericValidationError(
            f"{name} must be finite (got {value!r} → {x!r})"
        )
    return x


def require_nonnegative_finite(value: Any, name: str) -> float:
    """Конечное число >= 0."""
    x = require_finite_number(value, name)
    if x < 0:
        raise NumericValidationError(f"{name} must be >= 0 (got {x})")
    return x
