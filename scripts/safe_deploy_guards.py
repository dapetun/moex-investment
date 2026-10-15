"""Охрана SAFE_DEPLOY Permission A: пути и содержимое skill.

Используется шагами 4b/4c/6/10b в docs/analyst_skill_patch/SAFE_DEPLOY.md
и тестами. Сам по себе live-пути box не трогает.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path


def _resolve(p: Path) -> Path:
    return p.expanduser().resolve(strict=False)


def _under(child: Path, root: Path) -> bool:
    return child == root or root in child.parents


def assert_path_in_skill_root(
    cli_path_raw: str,
    skill_root_logical: str,
    *,
    agent_data_logical: str | None = None,
) -> str:
    """Вернуть realpath CLI-пути, если он остаётся под корнем skill.

    Допускает штатный symlink/junction ``agent-data → sand-data``:
    промежуточные ссылки, чей target — предок (или сам) реального skill root /
    agent-data, допустимы. Ссылки и пути, уводящие за пределы этого дерева, —
    отказ. Компонент ``..`` в исходном пути запрещён (до resolve).
    """
    raw = Path(cli_path_raw)
    if ".." in raw.parts:
        raise SystemExit(f"path contains ..: {cli_path_raw}")

    skill_root = Path(skill_root_logical)
    root_real = _resolve(skill_root)
    if agent_data_logical is None:
        agent_data_logical = str(skill_root.parent)
    agent_real = _resolve(Path(agent_data_logical))

    cli_real = _resolve(raw)
    if not _under(cli_real, root_real):
        raise SystemExit(f"path outside SKILL_ROOT: {cli_real} (root={root_real})")

    # Обход логических компонент: escape-symlink/junction за пределы дерева.
    # На Windows junction часто не is_symlink(), но resolve уже отсёк финал;
    # здесь ловим промежуточные ссылки, если ОС их помечает.
    cur = Path(raw.anchor) if raw.anchor else Path("/")
    parts = raw.parts[1:] if raw.is_absolute() else raw.parts
    for part in parts:
        cur = cur / part
        if not cur.is_symlink():
            continue
        tgt = _resolve(cur)
        under_agent = (
            tgt == agent_real
            or _under(tgt, agent_real)
            or _under(agent_real, tgt)
        )
        under_root = (
            tgt == root_real or _under(tgt, root_real) or _under(root_real, tgt)
        )
        if not (under_agent or under_root):
            raise SystemExit(f"symlink escape at {cur} -> {tgt}")
    return str(cli_real)


def canonicalize_path(path: str) -> str:
    return str(_resolve(Path(path)))


def split_skill_md(text: str) -> tuple[dict[str, str], str]:
    """Разобрать SKILL.md: поля frontmatter + тело после закрывающего ---."""
    if not text.startswith("---"):
        raise SystemExit("skill missing opening frontmatter ---")
    rest = text[3:]
    end = rest.find("\n---")
    if end < 0:
        raise SystemExit("skill missing closing frontmatter ---")
    fm_raw = rest[:end].strip("\n")
    body = rest[end + 4 :].lstrip("\n")
    fields: dict[str, str] = {}
    key = None
    buf: list[str] = []
    for line in fm_raw.splitlines():
        m = re.match(r"^([A-Za-z0-9_-]+):\s*(.*)$", line)
        if m and not line.startswith(" "):
            if key is not None:
                fields[key] = "\n".join(buf).strip()
            key = m.group(1)
            val = m.group(2)
            if val in (">", ">-", "|", "|-"):
                buf = []
            else:
                fields[key] = val.strip().strip("'\"")
                key = None
                buf = []
        elif key is not None:
            buf.append(line.strip())
    if key is not None:
        fields[key] = "\n".join(buf).strip()
    return fields, body


def _norm_ws(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip()


def compare_skill_md(repo_text: str, live_text: str) -> None:
    """Отказать, если name/тело не совпали; description — по нормализации пробелов.

    Подтверждённая нормализация платформы (pa-1405): ``>`` → ``>-``, перенос строк
    в description. Тело инструкций после frontmatter — байт-в-байт.
    """
    rf, rb = split_skill_md(repo_text)
    lf, lb = split_skill_md(live_text)
    if rf.get("name") != lf.get("name"):
        raise SystemExit(
            f"skill name mismatch: repo={rf.get('name')!r} live={lf.get('name')!r}"
        )
    if rb != lb:
        raise SystemExit("skill body (after frontmatter) differs from approved repo text")
    if _norm_ws(rf.get("description", "")) != _norm_ws(lf.get("description", "")):
        raise SystemExit(
            "skill description semantic mismatch after whitespace normalize"
        )


def load_manifest(path: Path) -> dict[str, str]:
    d: dict[str, str] = {}
    for i, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        parts = line.split(None, 1)
        if len(parts) != 2 or len(parts[0]) != 64:
            raise SystemExit(f"bad manifest line {i}: {line!r}")
        d[canonicalize_path(parts[1])] = parts[0]
    return d


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        print(
            "usage: safe_deploy_guards.py path-check RAW ROOT [AGENT_DATA]\n"
            "       safe_deploy_guards.py skill-compare REPO_SKILL LIVE_SKILL\n"
            "       safe_deploy_guards.py canon PATH",
            file=sys.stderr,
        )
        return 2
    cmd = argv[1]
    if cmd == "path-check":
        agent = argv[4] if len(argv) > 4 else None
        print(assert_path_in_skill_root(argv[2], argv[3], agent_data_logical=agent))
        return 0
    if cmd == "skill-compare":
        compare_skill_md(
            Path(argv[2]).read_text(encoding="utf-8"),
            Path(argv[3]).read_text(encoding="utf-8"),
        )
        print("skill content ok")
        return 0
    if cmd == "canon":
        print(canonicalize_path(argv[2]))
        return 0
    print(f"unknown command {cmd}", file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
