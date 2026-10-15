"""Регрессия guards SAFE_DEPLOY (BL7–BL9, 4c): symlink/junction mock, fail-closed."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "safe_deploy_guards.py"
sys.path.insert(0, str(ROOT / "scripts"))
import safe_deploy_guards as g  # noqa: E402


def _dir_link(link: Path, target: Path) -> None:
    """Создать symlink или Windows junction (без прав на symlink)."""
    link.parent.mkdir(parents=True, exist_ok=True)
    try:
        link.symlink_to(target, target_is_directory=True)
        return
    except OSError:
        if os.name != "nt":
            raise
    # junction не требует SeCreateSymbolicLinkPrivilege
    r = subprocess.run(
        ["cmd", "/c", "mklink", "/J", str(link), str(target)],
        check=False,
        capture_output=True,
        text=True,
    )
    if r.returncode != 0 or not link.exists():
        raise OSError(f"mklink /J failed: {r.stdout} {r.stderr}")


@pytest.fixture()
def symlink_box(tmp_path: Path) -> dict[str, Path]:
    """Макет /home/box/agent-data → sand-data (pa-1405)."""
    sand = tmp_path / "sand-data"
    workflows = sand / "workflows"
    workflows.mkdir(parents=True)
    (workflows / "skill-1791618014068").mkdir()
    (workflows / "skill-1791618014068" / "SKILL.md").write_text("opt\n", encoding="utf-8")
    box = tmp_path / "box"
    box.mkdir()
    agent_link = box / "agent-data"
    _dir_link(agent_link, sand)
    new_skill = workflows / "cli-analyst-bundle"
    new_skill.mkdir()
    (new_skill / "SKILL.md").write_text(
        "---\nname: cli-analyst-bundle\ndescription: >-\n  line\n---\n\n# Body\n",
        encoding="utf-8",
    )
    return {
        "sand": sand,
        "workflows_real": workflows,
        "agent_logical": agent_link,
        "skill_root_logical": agent_link / "workflows",
        "cli_logical": agent_link / "workflows" / "cli-analyst-bundle",
        "cli_real": new_skill,
        "escape": tmp_path / "outside",
    }


def test_bl7_platform_symlink_accepted(symlink_box: dict[str, Path]) -> None:
    out = g.assert_path_in_skill_root(
        str(symlink_box["cli_logical"]),
        str(symlink_box["skill_root_logical"]),
        agent_data_logical=str(symlink_box["agent_logical"]),
    )
    assert Path(out) == symlink_box["cli_real"].resolve()


def test_bl7_escape_symlink_rejected(symlink_box: dict[str, Path], tmp_path: Path) -> None:
    outside = tmp_path / "evil"
    outside.mkdir()
    trap = symlink_box["workflows_real"] / "trap"
    _dir_link(trap, outside)
    with pytest.raises(SystemExit, match="symlink escape|outside"):
        g.assert_path_in_skill_root(
            str(symlink_box["skill_root_logical"] / "trap"),
            str(symlink_box["skill_root_logical"]),
            agent_data_logical=str(symlink_box["agent_logical"]),
        )


def test_path_dotdot_rejected(symlink_box: dict[str, Path]) -> None:
    with pytest.raises(SystemExit, match=r"\.\."):
        g.assert_path_in_skill_root(
            str(symlink_box["skill_root_logical"] / ".." / "agents"),
            str(symlink_box["skill_root_logical"]),
            agent_data_logical=str(symlink_box["agent_logical"]),
        )


def test_path_outside_root_rejected(symlink_box: dict[str, Path], tmp_path: Path) -> None:
    with pytest.raises(SystemExit, match="outside"):
        g.assert_path_in_skill_root(
            str(tmp_path / "nope"),
            str(symlink_box["skill_root_logical"]),
            agent_data_logical=str(symlink_box["agent_logical"]),
        )


def test_4c_frontmatter_fold_ok_body_must_match() -> None:
    repo = """---
name: cli-analyst-bundle
description: >
  Даниила: читать moex_analyst_bundle.v1 и/или запускать разрешённую цепочку
  CLI moex_portfolio. Глобальная библиотека skills: в любом другом агенте —
  отказ. Не optimizer.yaml, не ISS в CLI, не cron.

---

# Body

Rule A
"""
    live = """---
name: cli-analyst-bundle
description: >-
  Даниила: читать moex_analyst_bundle.v1 и/или запускать разрешённую цепочку CLI
  moex_portfolio. Глобальная библиотека skills: в любом другом агенте — отказ.
  Не optimizer.yaml, не ISS в CLI, не cron.
---
# Body

Rule A
"""
    g.compare_skill_md(repo, live)


def test_4c_body_change_fails() -> None:
    repo = "---\nname: cli-analyst-bundle\ndescription: x\n---\n\n# Body\nA\n"
    live = "---\nname: cli-analyst-bundle\ndescription: x\n---\n\n# Body\nB\n"
    with pytest.raises(SystemExit, match="body"):
        g.compare_skill_md(repo, live)


def test_4c_name_mismatch_fails() -> None:
    repo = "---\nname: cli-analyst-bundle\ndescription: x\n---\n\n# Body\n"
    live = "---\nname: other\ndescription: x\n---\n\n# Body\n"
    with pytest.raises(SystemExit, match="name"):
        g.compare_skill_md(repo, live)


def test_4c_extra_frontmatter_key_fails() -> None:
    repo = "---\nname: cli-analyst-bundle\ndescription: x\n---\n\n# Body\n"
    live = (
        "---\nname: cli-analyst-bundle\ndescription: x\n"
        "allowed-agents: all\n---\n\n# Body\n"
    )
    with pytest.raises(SystemExit, match="unexpected frontmatter"):
        g.compare_skill_md(repo, live)


def test_n34_missing_path_rejected(symlink_box: dict[str, Path]) -> None:
    missing = symlink_box["skill_root_logical"] / "no-such-skill"
    with pytest.raises(SystemExit, match="does not exist|outside"):
        g.assert_path_in_skill_root(
            str(missing),
            str(symlink_box["skill_root_logical"]),
            agent_data_logical=str(symlink_box["agent_logical"]),
        )


def test_bl9_manifest_keys_canonical(symlink_box: dict[str, Path], tmp_path: Path) -> None:
    logical = str(
        symlink_box["agent_logical"] / "workflows" / "skill-1791618014068" / "SKILL.md"
    )
    real = str(
        (symlink_box["workflows_real"] / "skill-1791618014068" / "SKILL.md").resolve()
    )
    man = tmp_path / "m.txt"
    h = "a" * 64
    man.write_text(f"{h}  {logical}\n", encoding="utf-8")
    loaded = g.load_manifest(man)
    assert real in loaded
    assert loaded[real] == h


def test_cli_path_check_exit_codes(symlink_box: dict[str, Path]) -> None:
    ok = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "path-check",
            str(symlink_box["cli_logical"]),
            str(symlink_box["skill_root_logical"]),
            str(symlink_box["agent_logical"]),
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert ok.returncode == 0, ok.stderr + ok.stdout
    bad = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "path-check",
            str(symlink_box["escape"]),
            str(symlink_box["skill_root_logical"]),
            str(symlink_box["agent_logical"]),
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert bad.returncode != 0


def test_rollback_path_guard_rejects_escape(
    symlink_box: dict[str, Path], tmp_path: Path
) -> None:
    """10b: path-check перед delete должен отказать на escape (exit != 0)."""
    outside = tmp_path / "evil-rb"
    outside.mkdir()
    trap = symlink_box["workflows_real"] / "trap-rb"
    _dir_link(trap, outside)
    bad = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "path-check",
            str(symlink_box["skill_root_logical"] / "trap-rb"),
            str(symlink_box["skill_root_logical"]),
            str(symlink_box["agent_logical"]),
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert bad.returncode != 0
