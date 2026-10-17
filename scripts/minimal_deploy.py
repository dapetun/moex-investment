"""Минимальный deploy Permission A (вариант B).

Один оркестратор: verify-package → phase-a → (platform create вне процесса) →
phase-b → verify-after → rollback при сбое.

Не доверяет pin внутри архива: ожидаемые хэши и EXPECT_HEAD передаются
снаружи (текст задания Permission A / handoff). Platform create/delete —
внешние колбэки (Регулятор); в тестах — mock.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import sys
import tempfile
from collections.abc import Callable
from pathlib import Path

_SCRIPTS = Path(__file__).resolve().parent
_GUARDS_PATH = _SCRIPTS / "safe_deploy_guards.py"
_g = None  # ленивая загрузка после verify (N-7)


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


def g():
    """Guards-модуль (лениво)."""
    global _g
    if _g is None:
        _g = _load_guards()
    return _g


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


def load_expect_json(path: Path, *, pkg_root: Path | None = None) -> dict:
    """Загрузить внешний pin. Отказ, если файл лежит внутри PKG (N-4)."""
    path = path.resolve()
    if pkg_root is not None:
        pkg = pkg_root.resolve()
        try:
            path.relative_to(pkg)
            raise SystemExit(
                f"expect-json must be outside package root: {path} under {pkg}"
            )
        except ValueError:
            pass
    blob = json.loads(path.read_text(encoding="utf-8"))
    files = blob.get("files") or {}
    if not isinstance(files, dict) or not files:
        raise SystemExit("expect-json missing files map")
    return {
        "expect_head": blob.get("expect_head") or blob.get("EXPECT_HEAD") or "",
        "files": {str(k): str(v) for k, v in files.items()},
    }


def verify_package(
    pkg_root: Path,
    expect_hashes: dict[str, str],
    *,
    expect_head: str = "",
    archive_commit_id: str = "",
    require_commit: bool = True,
) -> None:
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
    if not require_commit:
        return
    if not expect_head or len(expect_head) != 40 or any(
        c not in "0123456789abcdef" for c in expect_head.lower()
    ):
        raise SystemExit("expect_head required: full 40-hex commit SHA (R-4)")
    if not archive_commit_id:
        raise SystemExit("archive_commit_id required (git get-tar-commit-id) (R-4)")
    if archive_commit_id.lower() != expect_head.lower():
        raise SystemExit(
            f"archive commit {archive_commit_id!r} != expect_head {expect_head!r}"
        )


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


def map_audit_baseline_to_paths(
    audit_names: dict[str, str],
    *,
    profile: Path,
    opt: Path,
    pos: Path,
    qc: Path,
    optimizer_yaml: Path,
    spec: Path,
) -> dict[str, str]:
    """Имена AUDIT_BASELINE → абсолютные пути (fail-closed при дыре)."""
    key_map = {
        "profile.json": profile,
        "OPT SKILL.md (`skill-1791618014068`)": opt,
        "POS SKILL.md (`skill-1791618006478`)": pos,
        "QC SKILL.md (`skill-1791617999761`)": qc,
        "optimizer.yaml": optimizer_yaml,
        "analysis_spec.md": spec,
    }
    out: dict[str, str] = {}
    for name, path in key_map.items():
        if name not in audit_names:
            raise SystemExit(f"AUDIT_BASELINE missing key: {name}")
        out[str(path.resolve())] = audit_names[name]
    return out


def check_baseline(path_to_expected_sha: dict[str, str]) -> None:
    """Fail-closed: каждый путь существует и sha совпадает. Пустой → отказ (N-6)."""
    if not path_to_expected_sha:
        raise SystemExit("empty baseline refused")
    for raw, want in path_to_expected_sha.items():
        p = Path(raw)
        if not p.is_file():
            raise SystemExit(f"baseline missing file: {raw}")
        got = sha256_file(p)
        if got != want:
            raise SystemExit(f"baseline drift: {raw}: got {got} want {want}")


def check_optimizer_disabled(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    top = [
        ln.strip()
        for ln in text.splitlines()
        if ln.strip() and not ln.startswith(" ") and not ln.startswith("\t")
    ]
    enabled_lines = [ln for ln in top if ln.startswith("enabled:")]
    if len(enabled_lines) != 1:
        raise SystemExit(
            f"optimizer.yaml must have exactly one top-level enabled:, got {enabled_lines!r}"
        )
    enabled = enabled_lines[0].split(":", 1)[1].strip().lower()
    if enabled != "false":
        raise SystemExit(f"optimizer.yaml enabled must be false, got {enabled!r}")


def check_no_cli_skill(workflows_dir: Path) -> None:
    """Отказ, если уже есть каталог skill с name cli-analyst-bundle в SKILL.md."""
    if not workflows_dir.is_dir():
        raise SystemExit(f"workflows missing: {workflows_dir}")
    for skill_md in workflows_dir.glob("*/SKILL.md"):
        try:
            fields, _ = g().split_skill_md(skill_md.read_text(encoding="utf-8"))
        except SystemExit:
            continue
        name = (fields.get("name") or "").strip().lower().replace(" ", "")
        if name == SKILL_NAME.lower():
            raise SystemExit(f"cli-analyst-bundle already registered at {skill_md.parent}")


_TREE_SKIP_NAMES = frozenset(
    {
        "store.db",
        "store.db-wal",
        "store.db-shm",
    }
)
_TREE_SKIP_DIR_NAMES = frozenset({"assets", "attachments", "__pycache__"})


def _skip_tree_path(p: Path) -> bool:
    """Исключения для tree-manifest (R-1): не трогать секреты/БД/медиа."""
    name = p.name
    if name in _TREE_SKIP_NAMES or name.endswith("-secrets.json"):
        return True
    if name.endswith(".pyc"):
        return True
    for part in p.parts:
        if part in _TREE_SKIP_DIR_NAMES:
            return True
    return False


def collect_tree_files(*roots: Path) -> list[str]:
    """Файлы под корнями для детекции drift (не для BK/restore)."""
    out: list[str] = []
    for root in roots:
        root = root.resolve()
        if not root.exists():
            raise SystemExit(f"tree root missing: {root}")
        if root.is_file():
            if not _skip_tree_path(root):
                out.append(str(root))
            continue
        for p in sorted(root.rglob("*")):
            if not p.is_file() or p.is_symlink():
                continue
            if _skip_tree_path(p):
                continue
            out.append(str(p.resolve()))
    return out


def write_manifest(paths: list[str], out: Path) -> dict[str, str]:
    """MANIFEST: sha256 + canonical path per line."""
    rows: dict[str, str] = {}
    lines: list[str] = []
    for raw in paths:
        p = Path(raw)
        if not p.exists():
            raise SystemExit(f"manifest path missing: {raw}")
        canon = g().canonicalize_path(str(p))
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
    mapping: dict[str, dict[str, str]] = {}
    for i, raw in enumerate(paths):
        src = Path(raw)
        if not src.is_file():
            raise SystemExit(f"backup source missing: {raw}")
        dest_name = f"{i:02d}_{src.name}"
        dest = bk_dir / dest_name
        shutil.copy2(src, dest)
        h = sha256_file(src)
        if h != sha256_file(dest):
            raise SystemExit(f"backup integrity fail: {raw}")
        mapping[g().canonicalize_path(str(src))] = {"file": dest_name, "sha256": h}
    (bk_dir / "BACKUP_MAP.json").write_text(
        json.dumps(mapping, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )


def restore_backup(bk_dir: Path, *, manifest_before: dict[str, str] | None = None) -> None:
    """Атомарный restore: проверить все члены, затем tmp+replace, затем сверка (N-3)."""
    mapping = json.loads((bk_dir / "BACKUP_MAP.json").read_text(encoding="utf-8"))
    # 1) preflight: все члены на месте и sha совпадает с картой
    for canon, meta in mapping.items():
        if isinstance(meta, str):
            name, want = meta, None
        else:
            name, want = meta["file"], meta.get("sha256")
        src = bk_dir / name
        if not src.is_file():
            raise SystemExit(f"backup member missing: {name}")
        got = sha256_file(src)
        if want and got != want:
            raise SystemExit(f"backup member corrupted: {name}")
    # 2) copy via tmp + replace
    for canon, meta in mapping.items():
        name = meta if isinstance(meta, str) else meta["file"]
        src = bk_dir / name
        dest = Path(canon)
        dest.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp_name = tempfile.mkstemp(
            dir=str(dest.parent), prefix=".md_restore_", suffix=".tmp"
        )
        os.close(fd)
        tmp = Path(tmp_name)
        try:
            shutil.copy2(src, tmp)
            os.replace(tmp, dest)
        finally:
            if tmp.exists():
                tmp.unlink(missing_ok=True)
    # 3) verify against MANIFEST_BEFORE
    if manifest_before is None and (bk_dir.parent / "MANIFEST_BEFORE.txt").is_file():
        manifest_before = g().load_manifest(bk_dir.parent / "MANIFEST_BEFORE.txt")
    if manifest_before:
        for canon, want in manifest_before.items():
            if canon not in mapping:
                continue
            got = sha256_file(Path(canon))
            if got != want:
                raise SystemExit(f"restore verify fail: {canon}")


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
    allow = {g().canonicalize_path(p) for p in allowlist}
    if new_skill_path:
        allow.add(g().canonicalize_path(new_skill_path))
    for path, h in before.items():
        if path in allow:
            continue
        if after.get(path) != h:
            raise SystemExit(f"unauthorized change outside allowlist: {path}")
    for path, h in after.items():
        if before.get(path) == h:
            continue
        if path not in allow:
            raise SystemExit(f"new/changed path not in allowlist: {path}")


def apply_file_writes(
    writes: dict[str, str],
    allowlist: list[str],
    *,
    expected_after_sha: dict[str, str] | None = None,
) -> None:
    """Записать содержимое только в allowlist-пути; сверить sha «после» (N-6/R-2/R-8)."""
    if not writes:
        raise SystemExit("empty writes refused")
    allow = {g().canonicalize_path(p) for p in allowlist}
    exp: dict[str, str] | None = None
    if expected_after_sha is not None:
        exp = {g().canonicalize_path(k): v for k, v in expected_after_sha.items()}
        for raw in writes:
            if g().canonicalize_path(raw) not in exp:
                raise SystemExit(f"missing expected_after_sha for {raw}")
    for raw, content in writes.items():
        canon = g().canonicalize_path(raw)
        if Path(canon).name == "optimizer.yaml":
            raise SystemExit("write refused: optimizer.yaml never writable")
        if canon not in allow:
            raise SystemExit(f"write refused (not in allowlist): {canon}")
        if not content:
            raise SystemExit(f"empty write refused: {canon}")
        if Path(canon).name == "profile.json":
            try:
                obj = json.loads(content)
            except json.JSONDecodeError as e:
                raise SystemExit(f"profile.json must be valid JSON: {e}") from e
            if not isinstance(obj, dict) or "description" not in obj:
                raise SystemExit("profile.json must be object with description")
        if Path(canon).name == "SKILL.md" and not content.lstrip().startswith("---"):
            raise SystemExit(f"SKILL.md must have frontmatter: {canon}")
        Path(canon).write_text(content, encoding="utf-8", newline="\n")
        if exp is not None:
            got = sha256_file(Path(canon))
            want = exp[canon]
            if got != want:
                raise SystemExit(
                    f"expected_after_sha mismatch {canon}: got {got} want {want}"
                )


def register_skill_path(
    skill_path_raw: str,
    skill_root_logical: str,
    agent_data_logical: str,
    *,
    existed_before: set[str],
) -> str:
    """path-check + отказ если каталог/файлы skill уже были до create (N-5)."""
    real = g().assert_path_in_skill_root(
        skill_path_raw, skill_root_logical, agent_data_logical=agent_data_logical
    )
    canon = g().canonicalize_path(real)
    # каталог skill уже содержал файлы из MANIFEST_BEFORE
    if any(p == canon or p.startswith(canon + os.sep) for p in existed_before):
        raise SystemExit("path existed before deploy — refuse")
    return real


def refuse_delete_foreign(op_skill_id: str, requested_id: str) -> None:
    if not op_skill_id or requested_id != op_skill_id:
        raise SystemExit(
            f"refuse delete foreign skill: want {op_skill_id!r} got {requested_id!r}"
        )


def compare_registered_skill(repo_skill: Path, live_skill: Path) -> None:
    g().compare_skill_md(
        repo_skill.read_text(encoding="utf-8"),
        live_skill.read_text(encoding="utf-8"),
    )


def assert_recorded_skill_path(
    skill_id: str,
    skill_path: str,
    *,
    skill_root_logical: str,
    agent_data_logical: str,
    existed_before: set[str],
) -> str:
    """R-6: path под workflows, id в basename, name=cli-analyst-bundle."""
    real = register_skill_path(
        skill_path,
        skill_root_logical,
        agent_data_logical,
        existed_before=existed_before,
    )
    if Path(real).name != skill_id and skill_id not in Path(real).name:
        # basename каталога должен совпадать с id
        if Path(real).name != skill_id:
            raise SystemExit(
                f"skill_path basename {Path(real).name!r} != skill_id {skill_id!r}"
            )
    live_md = Path(real) / "SKILL.md"
    if not live_md.is_file():
        raise SystemExit(f"recorded skill missing SKILL.md: {live_md}")
    fields, _ = g().split_skill_md(live_md.read_text(encoding="utf-8"))
    if fields.get("name") != SKILL_NAME:
        raise SystemExit(f"recorded skill name != {SKILL_NAME}")
    return real


def record_created_skill(
    bk: Path,
    skill_id: str,
    skill_path: str,
    *,
    skill_root_logical: str | None = None,
    agent_data_logical: str | None = None,
    existed_before: set[str] | None = None,
) -> None:
    """Зафиксировать skill этой операции в BK (noclobber) — N-1/R-6."""
    if not skill_id or not skill_path:
        raise SystemExit("record_created_skill: empty id/path")
    if skill_root_logical and agent_data_logical is not None:
        skill_path = assert_recorded_skill_path(
            skill_id,
            skill_path,
            skill_root_logical=skill_root_logical,
            agent_data_logical=agent_data_logical,
            existed_before=existed_before or set(),
        )
    sid_f = bk / "skill_id.txt"
    path_f = bk / "skill_path.txt"
    if sid_f.exists() or path_f.exists():
        raise SystemExit("skill_id/path already recorded (noclobber)")
    sid_f.write_text(skill_id + "\n", encoding="utf-8")
    path_f.write_text(skill_path + "\n", encoding="utf-8")


def load_recorded_skill(bk: Path) -> tuple[str, str]:
    sid = (bk / "skill_id.txt").read_text(encoding="utf-8").strip()
    path = (bk / "skill_path.txt").read_text(encoding="utf-8").strip()
    if not sid or not path:
        raise SystemExit("recorded skill_id/path empty")
    return sid, path


PlatformCreate = Callable[[Path], tuple[str, str]]
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
    tree_roots: list[Path] | None = None,
) -> dict:
    """Подготовка: anti-parallel, no skill, baseline, backup, MANIFEST_BEFORE."""
    if not deploy_op_id or deploy_op_id == "pa-1405":
        raise SystemExit("invalid deploy_op_id")
    if active_ops:
        raise SystemExit(f"active deploy ops present: {active_ops}")
    if not baseline:
        raise SystemExit("empty baseline refused")
    check_no_cli_skill(workflows)
    check_baseline(baseline)
    check_optimizer_disabled(optimizer_yaml)
    if bk.exists() and any(bk.iterdir()):
        raise SystemExit(f"BK not empty: {bk}")
    bk.mkdir(parents=True, exist_ok=True)
    # R-1: BK/restore только allowlist∪baseline; tree — только детекция
    backup_set = sorted(set(tracked_paths) | set(baseline.keys()))
    backup_files(backup_set, bk / "files")
    manifest_paths = list(tracked_paths)
    if tree_roots:
        # дерево для детекции; BK не расширяем store.db и т.п.
        tree_paths = collect_tree_files(*tree_roots)
        manifest_paths = sorted(set(manifest_paths) | set(tree_paths))
        (bk / "tree_roots.json").write_text(
            json.dumps([str(p) for p in tree_roots], indent=2) + "\n",
            encoding="utf-8",
        )
    before = write_manifest(manifest_paths, bk / "MANIFEST_BEFORE.txt")
    (bk / "deploy_op_id.txt").write_text(deploy_op_id + "\n", encoding="utf-8")
    (bk / "allowlist.json").write_text(
        json.dumps(tracked_paths, indent=2) + "\n", encoding="utf-8"
    )
    return {
        "manifest_before": before,
        "bk": str(bk.resolve()),
        "tracked": tracked_paths,
        "manifest_paths": manifest_paths,
    }


def run_phase_b_files(
    *,
    bk: Path,
    writes: dict[str, str],
    allowlist: list[str],
    tracked_paths: list[str],
    optimizer_yaml: Path,
    optimizer_sha_before: str,
    new_skill_md_path: str | None = None,
    expected_after_sha: dict[str, str] | None = None,
) -> dict:
    """Применить файловые патчи + MANIFEST_AFTER + allowlist + optimizer pin."""
    if expected_after_sha is None:
        raise SystemExit("expected_after_sha required (N-6)")
    # R-2: allowlist только из BK (зафиксирован в phase-a), не из произвольного config
    allow_f = bk / "allowlist.json"
    if allow_f.is_file():
        fixed = json.loads(allow_f.read_text(encoding="utf-8"))
        if {g().canonicalize_path(p) for p in allowlist} != {
            g().canonicalize_path(p) for p in fixed
        }:
            raise SystemExit("allowlist drift vs BK/allowlist.json (R-2)")
        allowlist = fixed
    before = g().load_manifest(bk / "MANIFEST_BEFORE.txt")
    apply_file_writes(writes, allowlist, expected_after_sha=expected_after_sha)
    # R-3: пересобрать дерево если корни сохранены
    paths_after = list(before.keys())
    tree_f = bk / "tree_roots.json"
    if tree_f.is_file():
        roots = [Path(p) for p in json.loads(tree_f.read_text(encoding="utf-8"))]
        paths_after = collect_tree_files(*roots)
        # allowlist-файлы всегда в манифесте
        paths_after = sorted(set(paths_after) | {g().canonicalize_path(p) for p in allowlist})
    if new_skill_md_path:
        paths_after = list(paths_after) + [new_skill_md_path]
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
    requested_skill_id: str | None,
    platform_delete: PlatformDelete | None,
) -> None:
    """Файлы из BK + delete только skill, записанного в BK (N-1, N-3)."""
    errors: list[str] = []
    try:
        restore_backup(bk / "files")
    except (SystemExit, OSError) as e:
        errors.append(f"files: {e}")
    sid_f = bk / "skill_id.txt"
    if sid_f.is_file() and platform_delete:
        try:
            recorded_id, recorded_path = load_recorded_skill(bk)
            if not requested_skill_id:
                raise SystemExit("requested_skill_id required when skill was recorded")
            refuse_delete_foreign(recorded_id, requested_skill_id)
            # R-6: basename path == id
            if Path(recorded_path).name != recorded_id:
                raise SystemExit(
                    f"recorded path basename {Path(recorded_path).name!r} != id"
                )
            live_md = Path(recorded_path) / "SKILL.md"
            if live_md.is_file():
                fields, _ = g().split_skill_md(live_md.read_text(encoding="utf-8"))
                if fields.get("name") != SKILL_NAME:
                    raise SystemExit("delete refused: skill name mismatch")
            platform_delete(recorded_id, recorded_path)
        except (SystemExit, OSError) as e:
            errors.append(f"delete: {e}")
    elif requested_skill_id and platform_delete and not sid_f.is_file():
        errors.append("delete: skill_id.txt missing — refuse delete without BK record")
    if errors:
        raise SystemExit("; ".join(errors))


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        print(
            "usage:\n"
            "  minimal_deploy.py hash-file PATH\n"
            "  minimal_deploy.py verify-package PKG_ROOT --expect-json PATH [--expect-head SHA]\n"
            "  minimal_deploy.py self-check\n"
            "  minimal_deploy.py phase-a --config JSON\n"
            "  minimal_deploy.py phase-b --config JSON\n"
            "  minimal_deploy.py rollback --config JSON\n",
            file=sys.stderr,
        )
        return 2
    cmd = argv[1]
    if cmd == "hash-file":
        print(sha256_file(Path(argv[2])))
        return 0
    if cmd == "self-check":
        refuse_untrusted_pyc(_SCRIPTS)
        if not _GUARDS_PATH.is_file():
            raise SystemExit("guards missing")
        print("self-check ok", sha256_file(Path(__file__)), sha256_file(_GUARDS_PATH))
        return 0
    if cmd == "verify-package":
        pkg = Path(argv[2])
        expect: dict[str, str] = {}
        expect_head = ""
        archive_commit = ""
        i = 3
        while i < len(argv):
            if argv[i] == "--expect" and i + 1 < len(argv):
                rel, hx = argv[i + 1].split("=", 1)
                expect[rel] = hx
                i += 2
                continue
            if argv[i] == "--expect-json" and i + 1 < len(argv):
                loaded = load_expect_json(Path(argv[i + 1]), pkg_root=pkg)
                expect.update(loaded["files"])
                expect_head = expect_head or loaded["expect_head"]
                i += 2
                continue
            if argv[i] == "--expect-head" and i + 1 < len(argv):
                expect_head = argv[i + 1]
                i += 2
                continue
            if argv[i] == "--archive-commit" and i + 1 < len(argv):
                archive_commit = argv[i + 1]
                i += 2
                continue
            raise SystemExit(f"bad arg {argv[i]}")
        verify_package(
            pkg,
            expect,
            expect_head=expect_head,
            archive_commit_id=archive_commit,
            require_commit=True,
        )
        print("package ok")
        return 0
    if cmd in {"phase-a", "phase-b", "rollback"}:
        if "--config" not in argv:
            raise SystemExit(f"{cmd} requires --config JSON")
        try:
            cfg_path = Path(argv[argv.index("--config") + 1])
            cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
        except (IndexError, json.JSONDecodeError, OSError) as e:
            raise SystemExit(f"bad --config: {e}") from e
        try:
            if cmd == "phase-a":
                # R-2: allowlist строится в коде, не из произвольного списка
                allow = allowlist_paths(
                    skill_root=Path(cfg["workflows"]),
                    agent_dir=Path(cfg["agent_dir"]),
                    invest_spec=Path(cfg["invest_spec"]),
                )
                run_phase_a(
                    deploy_op_id=cfg["deploy_op_id"],
                    bk=Path(cfg["bk"]),
                    baseline=cfg["baseline"],
                    tracked_paths=allow,
                    workflows=Path(cfg["workflows"]),
                    optimizer_yaml=Path(cfg["optimizer_yaml"]),
                    active_ops=cfg.get("active_ops") or [],
                    tree_roots=[
                        Path(cfg["workflows"]),
                        Path(cfg["agent_dir"]),
                        Path(cfg["invest_spec"]).parent,
                    ],
                )
                print("phase-a ok")
                return 0
            if cmd == "phase-b":
                allow = json.loads(
                    (Path(cfg["bk"]) / "allowlist.json").read_text(encoding="utf-8")
                )
                run_phase_b_files(
                    bk=Path(cfg["bk"]),
                    writes=cfg["writes"],
                    allowlist=allow,
                    tracked_paths=allow,
                    optimizer_yaml=Path(cfg["optimizer_yaml"]),
                    optimizer_sha_before=cfg["optimizer_sha_before"],
                    new_skill_md_path=cfg.get("new_skill_md_path"),
                    expected_after_sha=cfg["expected_after_sha"],
                )
                print("phase-b ok")
                return 0
            bk = Path(cfg["bk"])
            file_err = None
            try:
                restore_backup(bk / "files")
            except (SystemExit, OSError) as e:
                file_err = str(e)
            if (bk / "skill_id.txt").is_file():
                sid, spath = load_recorded_skill(bk)
                req = cfg.get("requested_skill_id") or sid
                refuse_delete_foreign(sid, req)
                print(f"ROLLBACK_DELETE_CANDIDATE id={sid} path={spath}")
            if file_err:
                raise SystemExit(f"rollback-files failed: {file_err}")
            print("rollback-files ok")
            return 0
        except KeyError as e:
            raise SystemExit(f"config missing key: {e}") from e
    print(f"unknown {cmd}", file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
