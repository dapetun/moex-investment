"""Файловая блокировка против параллельных прогонов пайплайна."""

from __future__ import annotations

import logging
import os
import re
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from .config import DATA_DIR

logger = logging.getLogger(__name__)

LOCKS_DIR = DATA_DIR / "locks"
_PID_RE = re.compile(r"pid=(\d+)")


class PipelineLockError(RuntimeError):
    """Не удалось получить блокировку (уже занята)."""


def _pid_alive(pid: int) -> bool:
    """Проверить, жив ли процесс-держатель lock (best-effort)."""
    if pid <= 0:
        return False
    if os.name == "nt":
        import ctypes

        # PROCESS_QUERY_LIMITED_INFORMATION
        handle = ctypes.windll.kernel32.OpenProcess(0x1000, False, pid)
        if handle:
            ctypes.windll.kernel32.CloseHandle(handle)
            return True
        return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        # процесс существует, но нет прав сигналить — считаем живым
        return True
    except OSError:
        return False
    return True


def _try_reclaim_stale_lock(path: Path) -> bool:
    """Удалить lock, если PID мёртв. Возвращает True, если файл снят."""
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return False
    match = _PID_RE.search(text)
    if not match:
        return False
    pid = int(match.group(1))
    if _pid_alive(pid):
        return False
    try:
        path.unlink(missing_ok=True)
        logger.warning("Reclaimed stale pipeline lock %s (dead pid=%s)", path, pid)
        return True
    except OSError:
        return False


@contextmanager
def pipeline_lock(name: str = "pipeline") -> Iterator[Path]:
    """Контекстный менеджер эксклюзивной блокировки через O_EXCL.

    Args:
        name: Имя блокировки (файл ``{name}.lock``).

    Yields:
        Path к lock-файлу.

    Raises:
        PipelineLockError: если lock уже существует и процесс жив.
    """
    LOCKS_DIR.mkdir(parents=True, exist_ok=True)
    path = LOCKS_DIR / f"{name}.lock"
    flags = os.O_CREAT | os.O_EXCL | os.O_WRONLY

    def _acquire() -> int:
        return os.open(path, flags)

    try:
        fd = _acquire()
    except FileExistsError:
        if _try_reclaim_stale_lock(path):
            try:
                fd = _acquire()
            except FileExistsError as e:
                raise PipelineLockError(
                    f"pipeline lock busy: {path} (another process may be running)"
                ) from e
        else:
            raise PipelineLockError(
                f"pipeline lock busy: {path} (another process may be running); "
                "if the previous run crashed and the PID is still listed as alive, "
                "remove the lock file manually after confirming no CLI is running"
            )

    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(f"pid={os.getpid()}\n")
        yield path
    finally:
        try:
            path.unlink(missing_ok=True)
        except OSError:
            pass
