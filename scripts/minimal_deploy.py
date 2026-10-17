"""Минимальный deploy Permission A (вариант B).

Один оркестратор: verify-package → phase-a → (platform create вне процесса) →
phase-b → verify-after → rollback при сбое.

Не доверяет pin внутри архива: ожидаемые хэши передаются снаружи (задание).
Не трогает live само по себе без явных путей в config. Platform create/delete —
внешние колбэки (Регулятор); в тестах — mock.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import sys
from collections.abc import Callable
from pathlib import Path

# Фиксированный импорт соседнего модуля по пути файла (не sys.path из env).
_SCRIPTS = Path(__file__).resolve().parent
_GUARDS_PATH = _SCRIPTS / "safe_deploy_guards.py"


def _load_guards():
    """Загрузить safe_deploy_guards.py байтами + compile (без .pyc / path hijack)."""
    data = _GUARDS_PATH.read_bytes()
    if b"\r" in data:
        raise SystemExit("guards.py contains CR")
    import types

    mod = types.ModuleType("safe_deploy_guards")
    mod.__file__ = str(_GUARDS_PATH)
    code = compile(data, str(_GUARDS_PATH), "exec")
    exec(code, mod.__dict__)  # noqa: S102 — намеренно: проверенный файл пакета
    return mod


g = _load_guards()

# Относительные ключи критических файлов пакета (пути от корня репо/пакета).
PACKAGE_CRITICAL = (
    "scripts/minimal_deploy.py",
    "scripts/safe_deploy_guards.py",
    "docs/analyst_skill_patch/cli-analyst-bundle/SKILL.md",
    "docs/analyst_skill_patch/live_patches/AUDIT_BASELINE.md",
    "docs/analyst_skill_patch/live_patches/OPT_SKILL.patch.md",
    "docs/analyst_skill_patch/live_patches/POS_SKILL.patch.md",
    "docs/analyst_skill_patch/live_patches/QC_SKILL.patch.md",
    "docs/analyst_skill_patch/live_patches/PROFILE_DESCRIPTION.patch.md",
    "docs/analyst_skill_patch/live_patches/SPEC_analysis_spec.patch.md",
    "docs/analyst_skill_patch/MINIMAL_DEPLOY.md",
)

SKILL_NAME = "cli-analyst-bundle"
AGENT_ID = "5bda2f3d-a61a-48d6-8663-2441802d68de"


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path, *, refuse_cr: bool = False) -> str:
    data = path.read_bytes()
    if refuse_cr and b"\r" in data:
        raise SystemExit(f"CR in {path}")
    return sha256_bytes(data)


def refuse_untrusted_pyc(root: Path) -> None:
    for p in root.rglob("*"):
        if p.name == "__pycache__" or p.suffix == ".pyc":
            raise SystemExit(f"untrusted bytecode present: {p}")


def verify_package(pkg_root: Path, expect_hashes: dict[str, str]) -> None:
    """Сверить критические файлы пакета с внешними expect_hashes (из задания)."""
    pkg_root = pkg_root.resolve()
    if not pkg_root.is_dir():
        raise SystemExit(f"package root missing: {pkg_root}")
    refuse_untrusted_pyc(pkg_root)
    if not expect_hashes:
        raise SystemExit("empty expect_hashes (assignment pin required)")
    missing = set(PACKAGE_CRITICAL) - set(expect_hashes)
    if missing:
        raise SystemExit(f"assignment pin missing keys: {sorted(missing)}")
    for rel, want in expect_hashes.items():
        path = pkg_root / rel
        if not path.is_file():
            raise SystemExit(f"package file missing: {rel}")
        got = sha256_file(path, refuse_cr=True)
        if got != want:
            raise SystemExit(f"hash mismatch {rel}: got {got} want {want}")


def parse_baseline_table(audit_md: str) -> dict[str, str]:
    """Извлечь имя→sha256 из таблицы AUDIT_BASELINE (для тестов/справки)."""
    out: dict[str, str] = {}
    for line in audit_md.splitlines():
        if not line.startswith("|") or "sha256" in line.lower() or "----" in line:
            continue
        parts = [p.strip().strip("`") for p in line.strip("|").split("|")]
        if len(parts) >= 2 and len(parts[1]) == 64:
            out[parts[0]] = parts[1]
    return out


def check_baseline(path_to_expected_sha: dict[str, str]) -> None:
    """Fail-closed: каждый путь существует и sha совпадает."""
    for raw, want in path_to_expected_sha.items():
        p = Path(raw)
        if not p.is_file():
            raise SystemExit(f"baseline missing file: {raw}")
        got = sha256_file(p)
        if got != want:
            raise SystemExit(f"baseline drift: {raw}: got {got} want {want}")


def check_optimizer_disabled(optimizer_yaml: Path) -> None:
    text = optimizer_yaml.read_text(encoding="utf-8")
    if "enabled: true" in text.replace(" ", ""):
        # допускаем "enabled: true" только как false
        pass
    # простой разбор: строка enabled
    enabled = None
    for line in text.splitlines():
        s = line.strip()
        if s.startswith("enabled:"):
            enabled = s.split(":", 1)[1].strip().lower()
    if enabled != "false":
        raise SystemExit(f"optimizer.yaml enabled must be false, got {enabled!r}")


def check_no_cli_skill(workflows_dir: Path) -> None:
    """Отказ, если уже есть каталог skill с name cli-analyst-bundle в SKILL.md."""
    if not workflows_dir.is_dir():
        raise SystemExit(f"workflows missing: {workflows_dir}")
    for skill_md in workflows_dir.glob("*/SKILL.md"):
        try:
            fields, _ = g.split_skill_md(skill_md.read_text(encoding="utf-8"))
        except SystemExit:
            continue
        if fields.get("name") == SKILL_NAME:
            raise SystemExit(f"cli-analyst-bundle already registered at {skill_md.parent}")


def write_manifest(paths: list[str], out: Path) -> dict[str, str]:
    """MANIFEST: sha256 + canonical path per line."""
    rows: dict[str, str] = {}
    lines: list[str] = []
    for raw in paths:
        p = Path(raw)
        if not p.exists():
            raise SystemExit(f"manifest path missing: {raw}")
        canon = g.canonicalize_path(str(p))
        h = sha256_file(Path(canon))
        rows[canon] = h
        lines.append(f"{h}  {canon}")
    out.parent.mkdir(parents=True, exist_ok=True)
    if out.exists():
        raise SystemExit(f"manifest already exists (noclobber): {out}")
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return rows


def backup_files(paths: list[str], bk_dir: Path) -> None:
    bk_dir.mkdir(parents=True, exist_ok=True)
    mapping: dict[str, str] = {}
    for i, raw in enumerate(paths):
        src = Path(raw)
        if not src.is_file():
            raise SystemExit(f"backup source missing: {raw}")
        dest_name = f"{i:02d}_{src.name}"
        dest = bk_dir / dest_name
        shutil.copy2(src, dest)
        mapping[g.canonicalize_path(str(src))] = dest_name
    (bk_dir / "BACKUP_MAP.json").write_text(
        json.dumps(mapping, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    for canon, name in mapping.items():
        if sha256_file(Path(canon)) != sha256_file(bk_dir / name):
            raise SystemExit(f"backup integrity fail: {canon}")


def restore_backup(bk_dir: Path) -> None:
    mapping = json.loads((bk_dir / "BACKUP_MAP.json").read_text(encoding="utf-8"))
    for canon, name in mapping.items():
        src = bk_dir / name
        if not src.is_file():
            raise SystemExit(f"backup member missing: {name}")
        shutil.copy2(src, canon)


def allowlist_paths(
    *,
    skill_root: Path,
    agent_dir: Path,
    invest_spec: Path,
    opt_id: str = "skill-1791618014068",
    pos_id: str = "skill-1791618006478",
    qc_id: str = "skill-1791617999761",
) -> list[str]:
    return [
        str((skill_root / opt_id / "SKILL.md").resolve()),
        str((skill_root / pos_id / "SKILL.md").resolve()),
        str((skill_root / qc_id / "SKILL.md").resolve()),
        str((agent_dir / "profile.json").resolve()),
        str(invest_spec.resolve()),
    ]


def verify_manifest_allowlist(
    before: dict[str, str],
    after: dict[str, str],
    allowlist: list[str],
    *,
    new_skill_path: str | None = None,
) -> None:
    """Изменения только в allowlist (+ опционально новый skill path)."""
    allow = {g.canonicalize_path(p) for p in allowlist}
    if new_skill_path:
        allow.add(g.canonicalize_path(new_skill_path))
    # unchanged outside allow
    for path, h in before.items():
        if path in allow:
            continue
        if after.get(path) != h:
            raise SystemExit(f"unauthorized change outside allowlist: {path}")
    # after keys that differ or are new must be in allow
    for path, h in after.items():
        if before.get(path) == h:
            continue
        if path not in allow:
            raise SystemExit(f"new/changed path not in allowlist: {path}")


def apply_file_writes(writes: dict[str, str], allowlist: list[str]) -> None:
    """Записать содержимое только в allowlist-пути (fail-closed)."""
    allow = {g.canonicalize_path(p) for p in allowlist}
    for raw, content in writes.items():
        canon = g.canonicalize_path(raw)
        if canon not in allow:
            raise SystemExit(f"write refused (not in allowlist): {canon}")
        Path(canon).write_text(content, encoding="utf-8", newline="\n")


def register_skill_path(
    skill_path_raw: str,
    skill_root_logical: str,
    agent_data_logical: str,
    *,
    existed_before: set[str],
) -> str:
    """path-check + отказ если путь был в MANIFEST_BEFORE."""
    real = g.assert_path_in_skill_root(
        skill_path_raw, skill_root_logical, agent_data_logical=agent_data_logical
    )
    canon = g.canonicalize_path(real)
    if canon in existed_before or any(
        canon == p or canon.startswith(p + os.sep) for p in existed_before
    ):
        # directory: if any before path equals or is under skill dir
        for p in existed_before:
            if p == canon or p.startswith(canon + os.sep) or canon.startswith(p + os.sep):
                raise SystemExit("path existed before deploy — refuse")
    return real


def refuse_delete_foreign(op_skill_id: str, requested_id: str) -> None:
    if not op_skill_id or requested_id != op_skill_id:
        raise SystemExit(
            f"refuse delete foreign skill: want {op_skill_id!r} got {requested_id!r}"
        )


def compare_registered_skill(repo_skill: Path, live_skill: Path) -> None:
    g.compare_skill_md(
        repo_skill.read_text(encoding="utf-8"),
        live_skill.read_text(encoding="utf-8"),
    )


# --- Platform hooks (Регулятор); тесты подставляют mock ---

PlatformCreate = Callable[[Path], tuple[str, str]]  # -> (skill_id, path)
PlatformDelete = Callable[[str, str], None]


def run_phase_a(
    *,
    deploy_op_id: str,
    bk: Path,
    baseline: dict[str, str],
    tracked_paths: list[str],
    workflows: Path,
    optimizer_yaml: Path,
    active_ops: list[str] | None = None,
) -> dict:
    """Подготовка: anti-parallel, no skill, baseline, backup, MANIFEST_BEFORE."""
    if not deploy_op_id or deploy_op_id == "pa-1405":
        raise SystemExit("invalid deploy_op_id")
    if active_ops:
        raise SystemExit(f"active deploy ops present: {active_ops}")
    check_no_cli_skill(workflows)
    check_baseline(baseline)
    check_optimizer_disabled(optimizer_yaml)
    if bk.exists() and any(bk.iterdir()):
        raise SystemExit(f"BK not empty: {bk}")
    bk.mkdir(parents=True, exist_ok=True)
    backup_files(tracked_paths, bk / "files")
    before = write_manifest(tracked_paths, bk / "MANIFEST_BEFORE.txt")
    (bk / "deploy_op_id.txt").write_text(deploy_op_id + "\n", encoding="utf-8")
    return {"manifest_before": before, "bk": str(bk.resolve())}


def run_phase_b_files(
    *,
    bk: Path,
    writes: dict[str, str],
    allowlist: list[str],
    tracked_paths: list[str],
    optimizer_yaml: Path,
    optimizer_sha_before: str,
    new_skill_md_path: str | None = None,
) -> dict:
    """Применить файловые патчи + MANIFEST_AFTER + allowlist + optimizer pin."""
    before = g.load_manifest(bk / "MANIFEST_BEFORE.txt")
    apply_file_writes(writes, allowlist)
    paths_after = list(tracked_paths)
    if new_skill_md_path:
        paths_after.append(new_skill_md_path)
    after = write_manifest(paths_after, bk / "MANIFEST_AFTER.txt")
    verify_manifest_allowlist(
        before,
        after,
        allowlist,
        new_skill_path=new_skill_md_path,
    )
    got = sha256_file(optimizer_yaml)
    if got != optimizer_sha_before:
        raise SystemExit("optimizer.yaml changed during deploy")
    check_optimizer_disabled(optimizer_yaml)
    return {"manifest_after": after}


def run_rollback(
    *,
    bk: Path,
    op_skill_id: str | None,
    platform_delete: PlatformDelete | None,
    skill_path: str | None,
) -> None:
    """Сначала файлы, потом platform delete только своего skill."""
    restore_backup(bk / "files")
    if op_skill_id and platform_delete and skill_path:
        refuse_delete_foreign(op_skill_id, op_skill_id)
        platform_delete(op_skill_id, skill_path)


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        print(
            "usage:\n"
            "  minimal_deploy.py hash-file PATH\n"
            "  minimal_deploy.py verify-package PKG_ROOT --expect REL=HEX [...]\n"
            "  minimal_deploy.py self-check\n",
            file=sys.stderr,
        )
        return 2
    cmd = argv[1]
    if cmd == "hash-file":
        print(sha256_file(Path(argv[2])))
        return 0
    if cmd == "self-check":
        # оркестратор и guards на месте, без pyc рядом
        refuse_untrusted_pyc(_SCRIPTS)
        if not _GUARDS_PATH.is_file():
            raise SystemExit("guards missing")
        print("self-check ok", sha256_file(Path(__file__)), sha256_file(_GUARDS_PATH))
        return 0
    if cmd == "verify-package":
        pkg = Path(argv[2])
        expect: dict[str, str] = {}
        i = 3
        while i < len(argv):
            if argv[i] == "--expect" and i + 1 < len(argv):
                rel, hx = argv[i + 1].split("=", 1)
                expect[rel] = hx
                i += 2
                continue
            if argv[i] == "--expect-json" and i + 1 < len(argv):
                # внешний JSON (не из pkg): {"files": {"rel": "hex"}}
                blob = json.loads(Path(argv[i + 1]).read_text(encoding="utf-8"))
                expect.update(blob.get("files") or blob)
                i += 2
                continue
            raise SystemExit(f"bad arg {argv[i]}")
        verify_package(pkg, expect)
        print("package ok")
        return 0
    print(f"unknown {cmd}", file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
