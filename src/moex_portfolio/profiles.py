"""Сохранение и загрузка профилей портфелей (JSON)."""

import json
import logging
from datetime import datetime
from pathlib import Path

from .config import DATA_DIR

logger = logging.getLogger(__name__)

PROFILES_DIR = DATA_DIR / "profiles"


def _ensure_profiles_dir() -> Path:
    """Создать директорию профилей, если не существует."""
    PROFILES_DIR.mkdir(parents=True, exist_ok=True)
    return PROFILES_DIR


def save_profile(
    name: str,
    clique: list[str],
    weights: dict[str, float],
    metrics: dict | None = None,
    params: dict | None = None,
) -> Path:
    """Сохранить профиль портфеля в JSON.

    Args:
        name: Название профиля.
        clique: Список тикеров.
        weights: Словарь {ticker: weight}.
        metrics: Метрики портфеля (опционально).
        params: Параметры оптимизации (опционально).

    Returns:
        Path к файлу профиля.
    """
    profiles_dir = _ensure_profiles_dir()
    filepath = profiles_dir / f"{name}.json"

    profile = {
        "name": name,
        "created_at": datetime.now().isoformat(),
        "clique": clique,
        "weights": weights,
        "metrics": _serialize_metrics(metrics) if metrics else {},
        "params": params or {},
    }

    filepath.write_text(json.dumps(profile, indent=2, ensure_ascii=False), encoding="utf-8")
    logger.info("Profile saved: %s", filepath)
    return filepath


def load_profile(name: str) -> dict:
    """Загрузить профиль портфеля из JSON.

    Args:
        name: Название профиля (без расширения .json).

    Returns:
        Словарь с данными профиля.

    Raises:
        FileNotFoundError: Если профиль не найден.
    """
    filepath = PROFILES_DIR / f"{name}.json"

    if not filepath.exists():
        raise FileNotFoundError(f"Profile '{name}' not found at {filepath}")

    data = json.loads(filepath.read_text(encoding="utf-8"))
    logger.info("Profile loaded: %s", name)
    return data


def list_profiles() -> list[str]:
    """Получить список сохранённых профилей.

    Returns:
        Список названий профилей.
    """
    profiles_dir = _ensure_profiles_dir()
    return sorted(p.stem for p in profiles_dir.glob("*.json"))


def delete_profile(name: str) -> bool:
    """Удалить профиль.

    Args:
        name: Название профиля.

    Returns:
        True если удалён, False если не найден.
    """
    filepath = PROFILES_DIR / f"{name}.json"
    if filepath.exists():
        filepath.unlink()
        logger.info("Profile deleted: %s", name)
        return True
    return False


def _serialize_metrics(metrics: dict) -> dict:
    """Сериализация метрик (numpy -> float)."""
    result = {}
    for k, v in metrics.items():
        if hasattr(v, "item"):
            result[k] = v.item()
        elif isinstance(v, float):
            result[k] = v
        elif v is None:
            result[k] = None
        else:
            result[k] = v
    return result
