"""Файловая блокировка против параллельных прогонов пайплайна."""

from __future__ import annotations

import os
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from .config import DATA_DIR

LOCKS_DIR = DATA_DIR / "locks"


class PipelineLockError(RuntimeError):
    """Не удалось получить блокировку (уже занята)."""


@contextmanager
def pipeline_lock(name: str = "pipeline") -> Iterator[Path]:
    """Контекстный менеджер эксклюзивной блокировки через O_EXCL.

    Args:
        name: Имя блокировки (файл ``{name}.lock``).

    Yields:
        Path к lock-файлу.

    Raises:
        PipelineLockError: если lock уже существует.
    """
    LOCKS_DIR.mkdir(parents=True, exist_ok=True)
    path = LOCKS_DIR / f"{name}.lock"
    flags = os.O_CREAT | os.O_EXCL | os.O_WRONLY
    try:
        fd = os.open(path, flags)
    except FileExistsError as e:
        raise PipelineLockError(
            f"pipeline lock busy: {path} (another process may be running)"
        ) from e

    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(f"pid={os.getpid()}\n")
        yield path
    finally:
        try:
            path.unlink(missing_ok=True)
        except OSError:
            pass
