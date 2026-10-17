"""Охрана SAFE_DEPLOY Permission A: пути и содержимое skill.

Используется шагами 4b/4c/6/10b в docs/analyst_skill_patch/SAFE_DEPLOY.md
и тестами. Сам по себе live-пути box не трогает.
"""

from __future__ import annotations

import os
import re
import sys
from pathlib import Path

_UNSAFE_EXACT = frozenset({"", "/", ".", "..", "\\", "C:\\", "c:\\"})


def _resolve(p: Path, *, strict: bool = False) -> Path:
    return p.expanduser().resolve(strict=strict)


def _under(child: Path, root: Path) -> bool:
    return child == root or root in child.parents


def assert_safe_abs_path(label: str, raw: str, *, min_len: int = 8) -> Path:
    """Отказ на пустых, корневых и слишком коротких путях (N43)."""
    if raw is None or raw in _UNSAFE_EXACT:
        raise SystemExit(f"{label} unsafe: {raw!r}")
    p = Path(raw)
    # абсолютный: Unix /… или Windows X:\…
    if not p.is_absolute():
        raise SystemExit(f"{label} must be absolute: {raw!r}")
    s = str(p)
    if len(s) < min_len:
        raise SystemExit(f"{label} too short: {raw!r}")
    # запрет «почти корень»
    if s.rstrip("/\\") in ("", "/", "\\") or re.fullmatch(r"[A-Za-z]:\\?", s):
        raise SystemExit(f"{label} looks like filesystem root: {raw!r}")
    return p


def validate_deploy_env(env: dict[str, str] | None = None, *, need_repo: bool = False) -> None:
    """Проверить согласованность корней deploy (N43/N44 + logical↔real)."""
    e = dict(os.environ if env is None else env)
    for key in (
        "BK",
        "WF",
        "AGENT_REAL",
        "SKILL_ROOT_LOGICAL",
        "SKILL_ROOT_REAL",
        "AGENT_DATA_LOGICAL",
        "DEPLOY_ROOT",
    ):
        if key not in e or e[key] == "":
            raise SystemExit(f"missing env {key}")
        assert_safe_abs_path(key, e[key])

    bk = _resolve(Path(e["BK"]))
    deploy = _resolve(Path(e["DEPLOY_ROOT"]))
    if bk != deploy:
        raise SystemExit(f"BK != DEPLOY_ROOT: {bk} vs {deploy}")

    wf = _resolve(Path(e["WF"]))
    skill_real = _resolve(Path(e["SKILL_ROOT_REAL"]))
    if wf != skill_real:
        raise SystemExit(f"WF != SKILL_ROOT_REAL: {wf} vs {skill_real}")

    skill_logical = Path(e["SKILL_ROOT_LOGICAL"])
    skill_from_logical = _resolve(skill_logical)
    if skill_from_logical != skill_real:
        raise SystemExit(
            f"SKILL_ROOT_LOGICAL realpath mismatch: {skill_from_logical} vs {skill_real}"
        )

    agent_data_logical = Path(e["AGENT_DATA_LOGICAL"])
    agent_data_real = _resolve(agent_data_logical)
    agent_real = _resolve(Path(e["AGENT_REAL"]))
    if not _under(agent_real, agent_data_real):
        raise SystemExit(
            f"AGENT_REAL outside AGENT_DATA tree: {agent_real} not under {agent_data_real}"
        )
    # N45: parent(AGENT_REAL) == AGENT_DATA_REAL/agents, имя = id Аналитика
    _EXPECTED_AGENT_ID = "5bda2f3d-a61a-48d6-8663-2441802d68de"
    agents_dir = agent_data_real / "agents"
    if agent_real.parent != agents_dir:
        raise SystemExit(
            f"AGENT_REAL parent must be {agents_dir}, got {agent_real.parent}"
        )
    if agent_real.name != _EXPECTED_AGENT_ID:
        raise SystemExit(
            f"AGENT_REAL unexpected agent id: {agent_real.name!r} "
            f"(want {_EXPECTED_AGENT_ID})"
        )
    if not _under(skill_real, agent_data_real):
        raise SystemExit(
            f"SKILL_ROOT_REAL outside AGENT_DATA: {skill_real} not under {agent_data_real}"
        )

    if not bk.is_dir() or not wf.is_dir() or not agent_real.is_dir():
        raise SystemExit("BK/WF/AGENT_REAL must be existing directories")

    if need_repo:
        repo = e.get("REPO_ROOT", "")
        if not repo:
            raise SystemExit("missing env REPO_ROOT")
        assert_safe_abs_path("REPO_ROOT", repo)
        scripts = Path(repo) / "scripts"
        if not scripts.is_dir():
            raise SystemExit("REPO_ROOT missing scripts/")


def assert_path_in_skill_root(
    cli_path_raw: str,
    skill_root_logical: str,
    *,
    agent_data_logical: str | None = None,
) -> str:
    """Вернуть realpath CLI-пути, если он остаётся под корнем skill.

    Допускает штатный symlink/junction ``agent-data → sand-data``:
    промежуточные ссылки, чей target равен agent-data/skill-root или лежит
    **внутри** этих деревьев. Target-предки (в т.ч. ``/``) — отказ (N38).
    Путь должен существовать (N34). Компонент ``..`` запрещён до resolve.
    """
    raw = Path(cli_path_raw)
    if ".." in raw.parts:
        raise SystemExit(f"path contains ..: {cli_path_raw}")

    skill_root = Path(skill_root_logical)
    root_real = _resolve(skill_root)
    if agent_data_logical is None:
        agent_data_logical = str(skill_root.parent)
    agent_real = _resolve(Path(agent_data_logical))

    try:
        cli_real = _resolve(raw, strict=True)
    except FileNotFoundError as e:
        raise SystemExit(f"path does not exist: {cli_path_raw}") from e
    if not _under(cli_real, root_real):
        raise SystemExit(f"path outside SKILL_ROOT: {cli_real} (root={root_real})")

    cur = Path(raw.anchor) if raw.anchor else Path("/")
    parts = raw.parts[1:] if raw.is_absolute() else raw.parts
    for part in parts:
        cur = cur / part
        if not cur.is_symlink():
            continue
        tgt = _resolve(cur)
        under_agent = tgt == agent_real or _under(tgt, agent_real)
        under_root = tgt == root_real or _under(tgt, root_real)
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
    in_block = False
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
                in_block = True
            else:
                fields[key] = val.strip().strip("'\"")
                key = None
                buf = []
                in_block = False
        elif key is not None and in_block:
            buf.append(line.strip())
        elif re.match(r"^\s+\S", line):
            # N41: indented content after plain scalar (key is None) — отказ
            raise SystemExit(f"orphan indented frontmatter line: {line!r}")
    if key is not None:
        fields[key] = "\n".join(buf).strip()
    return fields, body


def _norm_ws(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip()


_ALLOWED_FM_KEYS = frozenset({"name", "description"})


def compare_skill_md(repo_text: str, live_text: str) -> None:
    """Отказать, если name/тело не совпали; description — по нормализации пробелов.

    Подтверждённая нормализация платформы (pa-1405): ``>`` → ``>-``, перенос строк
    в description. Тело инструкций после frontmatter — байт-в-байт.
    Допустимы только ключи name/description (N35); лишние поля — отказ.
    """
    rf, rb = split_skill_md(repo_text)
    lf, lb = split_skill_md(live_text)
    for label, fields in (("repo", rf), ("live", lf)):
        extra = set(fields) - _ALLOWED_FM_KEYS
        if extra:
            raise SystemExit(f"unexpected frontmatter keys in {label}: {sorted(extra)}")
        missing = _ALLOWED_FM_KEYS - set(fields)
        if missing:
            raise SystemExit(f"missing frontmatter keys in {label}: {sorted(missing)}")
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


def extract_bash_steps(md_text: str) -> list[str]:
    """Извлечь fenced ```bash блоки из SAFE_DEPLOY.md (N39)."""
    blocks: list[str] = []
    parts = md_text.split("```bash")
    for part in parts[1:]:
        end = part.find("```")
        if end < 0:
            continue
        blocks.append(part[:end].strip("\n"))
    return blocks


def assert_safe_deploy_integrity(md_text: str) -> None:
    """Структурная целостность SAFE_DEPLOY: ловит мутации M1–M4 (N39)."""
    blocks = extract_bash_steps(md_text)
    if len(blocks) < 6:
        raise SystemExit(f"too few bash blocks: {len(blocks)}")

    def find_one(pred, label: str) -> str:
        for b in blocks:
            if pred(b):
                return b
        raise SystemExit(f"missing bash block: {label}")

    step2 = find_one(lambda b: "BEFORE_MARKER" in b, "step2")
    step3 = find_one(lambda b: "MANIFEST_BEFORE" in b and "noclobber" in b, "step3")
    step4b = find_one(lambda b: "4b ok" in b, "step4b")
    step6 = find_one(lambda b: "allowed_exact" in b and "MANIFEST_AFTER" in b, "step6")
    step10a = find_one(lambda b: 'cp -a "$BK/profile.json"' in b, "step10a")
    step10b = find_one(
        lambda b: "path existed before deploy — refuse delete" in b
        or "path existed before deploy - refuse delete" in b
        or ("refuse delete" in b and "path-check" in b),
        "step10b",
    )

    _ALLOWLIST_EXACT = (
        "/home/box/agent-data/agents/5bda2f3d-a61a-48d6-8663-2441802d68de/profile.json",
        "/home/box/agent-data/workflows/skill-1791618014068/SKILL.md",
        "/home/box/agent-data/workflows/skill-1791618006478/SKILL.md",
        "/home/box/agent-data/workflows/skill-1791617999761/SKILL.md",
        "/workspace/invest/portfolio/analysis_spec.md",
    )

    for label, block in (
        ("step2", step2),
        ("step3", step3),
        ("step4b", step4b),
        ("step6", step6),
        ("step10a", step10a),
        ("step10b", step10b),
    ):
        if not block.lstrip().startswith("set -euo pipefail"):
            raise SystemExit(f"{label} must start with set -euo pipefail")
        if "validate-env" not in block:
            raise SystemExit(f"{label} missing validate-env")
        if "export BK" not in block:
            raise SystemExit(f"{label} missing export BK (M5)")
        if 'BK="$BK"' not in block:
            raise SystemExit(f"{label} missing BL11 env prefix BK=")
        if not re.search(r"validate-env[^\n]*\|\|\s*exit\s+[12]", block):
            raise SystemExit(f"{label} validate-env must use || exit 1|2 (not || true)")
        if 'case "$AGENT_REAL"' not in block:
            raise SystemExit(f"{label} missing case AGENT_REAL")
        case_body = block.split('case "$AGENT_REAL"', 1)[1].split("esac", 1)[0]
        if '"/"' not in case_body:
            raise SystemExit(f"{label} AGENT_REAL case must reject /")

    if not re.search(r"path-check[\s\S]{0,200}\|\|\s*exit\s+1", step4b):
        raise SystemExit("step4b path-check missing || exit 1 (BL8)")
    # M4: allowlist — ровно 5 путей, без лишних skill-*
    paths = re.findall(r'g\.canonicalize_path\("([^"]+)"\)', step6)
    if tuple(paths) != _ALLOWLIST_EXACT:
        raise SystemExit(
            f"step6 allowlist mismatch: got {paths!r} want {list(_ALLOWLIST_EXACT)!r}"
        )
    if "before.get(f) != h" not in step6:
        raise SystemExit("step6 missing before.get(f) != h check (M8)")


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        print(
            "usage: safe_deploy_guards.py path-check RAW ROOT [AGENT_DATA]\n"
            "       safe_deploy_guards.py skill-compare REPO_SKILL LIVE_SKILL\n"
            "       safe_deploy_guards.py canon PATH\n"
            "       safe_deploy_guards.py validate-env [--need-repo]\n"
            "       safe_deploy_guards.py extract-steps SAFE_DEPLOY.md",
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
    if cmd == "validate-env":
        need_repo = "--need-repo" in argv[2:]
        validate_deploy_env(need_repo=need_repo)
        print("deploy env ok")
        return 0
    if cmd == "extract-steps":
        blocks = extract_bash_steps(Path(argv[2]).read_text(encoding="utf-8"))
        print(len(blocks))
        return 0
    print(f"unknown command {cmd}", file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
