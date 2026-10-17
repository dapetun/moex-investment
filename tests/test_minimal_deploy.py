"""Полная последовательность minimal_deploy на изолированном mock-box."""

from __future__ import annotations

import json
import os
import shutil
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import minimal_deploy as md  # noqa: E402


def _link(link: Path, target: Path) -> None:
    link.parent.mkdir(parents=True, exist_ok=True)
    try:
        link.symlink_to(target, target_is_directory=True)
    except OSError:
        if os.name != "nt":
            raise
        import subprocess

        subprocess.check_call(
            ["cmd", "/c", "mklink", "/J", str(link), str(target)],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )


@pytest.fixture
def box(tmp_path: Path) -> dict:
    sand = tmp_path / "sand-data"
    agent_id = md.AGENT_ID
    workflows = sand / "workflows"
    agents = sand / "agents" / agent_id
    workflows.mkdir(parents=True)
    agents.mkdir(parents=True)
    # existing skills
    for sid, body in [
        ("skill-1791618014068", "# OPT\nbaseline\n"),
        ("skill-1791618006478", "# POS\nbaseline\n"),
        ("skill-1791617999761", "# QC\nbaseline\n"),
    ]:
        d = workflows / sid
        d.mkdir()
        (d / "SKILL.md").write_text(body, encoding="utf-8", newline="\n")
    (agents / "profile.json").write_text(
        json.dumps({"description": "baseline profile"}, ensure_ascii=False),
        encoding="utf-8",
        newline="\n",
    )
    invest = tmp_path / "invest" / "portfolio"
    invest.mkdir(parents=True)
    (invest / "analysis_spec.md").write_text("# spec\n", encoding="utf-8", newline="\n")
    opt_yaml = invest / "optimizer" / "config" / "optimizer.yaml"
    opt_yaml.parent.mkdir(parents=True)
    opt_yaml.write_text("enabled: false\n", encoding="utf-8", newline="\n")

    agent_data = tmp_path / "agent-data"
    _link(agent_data, sand)

    # package copy (critical subset) — всегда LF (как git archive на Linux)
    pkg = tmp_path / "pkg"
    for rel in md.PACKAGE_CRITICAL:
        src = ROOT / rel
        if not src.is_file():
            continue
        dest = pkg / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        data = src.read_bytes().replace(b"\r\n", b"\n").replace(b"\r", b"\n")
        dest.write_bytes(data)

    skill_root_logical = agent_data / "workflows"
    return {
        "tmp": tmp_path,
        "sand": sand,
        "agent_data": agent_data,
        "workflows": skill_root_logical,
        "workflows_real": workflows,
        "agent": agents,
        "invest": invest,
        "opt_yaml": opt_yaml,
        "pkg": pkg,
        "allow": md.allowlist_paths(
            skill_root=workflows,
            agent_dir=agents,
            invest_spec=invest / "analysis_spec.md",
        ),
    }


def _baseline(box: dict) -> dict[str, str]:
    return {p: md.sha256_file(Path(p)) for p in box["allow"]}


def _expect_hashes(pkg: Path) -> dict[str, str]:
    out = {}
    for rel in md.PACKAGE_CRITICAL:
        p = pkg / rel
        if p.is_file():
            out[rel] = md.sha256_file(p, refuse_cr=True)
    return out


def _platform_store(box: dict) -> dict:
    return {"created": None}

def _make_create(box: dict, store: dict, *, fail: bool = False, weird_path: Path | None = None):
    def create(skill_md: Path) -> tuple[str, str]:
        if fail:
            raise SystemExit("platform create failed")
        sid = "skill-999000111222"
        dest_dir = weird_path or (box["workflows_real"] / sid)
        dest_dir.mkdir(parents=True, exist_ok=True)
        dest = dest_dir / "SKILL.md"
        shutil.copy2(skill_md, dest)
        store["created"] = (sid, str(dest_dir.resolve()))
        return sid, str(dest_dir.resolve())

    return create


def _make_delete(store: dict):
    def delete(skill_id: str, path: str) -> None:
        md.refuse_delete_foreign(store["created"][0], skill_id)
        p = Path(path)
        if p.is_dir():
            shutil.rmtree(p)
        store["created"] = None

    return delete


def test_verify_package_ok_and_rejects_bad_hash(box: dict) -> None:
    expect = _expect_hashes(box["pkg"])
    md.verify_package(box["pkg"], expect)
    bad = dict(expect)
    bad["scripts/minimal_deploy.py"] = "0" * 64
    with pytest.raises(SystemExit, match="hash mismatch"):
        md.verify_package(box["pkg"], bad)


def test_verify_package_rejects_empty_pin(box: dict) -> None:
    with pytest.raises(SystemExit, match="empty expect"):
        md.verify_package(box["pkg"], {})


def test_verify_package_rejects_pyc(box: dict) -> None:
    evil = box["pkg"] / "scripts" / "__pycache__"
    evil.mkdir(parents=True)
    (evil / "x.pyc").write_bytes(b"\0")
    with pytest.raises(SystemExit, match="bytecode"):
        md.verify_package(box["pkg"], _expect_hashes(box["pkg"]))


def test_full_success_and_analyst_skill_visible(box: dict) -> None:
    md.verify_package(box["pkg"], _expect_hashes(box["pkg"]))
    bk = box["tmp"] / "bk"
    base = _baseline(box)
    opt_sha = md.sha256_file(box["opt_yaml"])
    md.run_phase_a(
        deploy_op_id="pa-20261017-2300",
        bk=bk,
        baseline=base,
        tracked_paths=box["allow"],
        workflows=box["workflows_real"],
        optimizer_yaml=box["opt_yaml"],
        active_ops=[],
    )
    store: dict = {}
    create = _make_create(box, store)
    skill_src = box["pkg"] / "docs/analyst_skill_patch/cli-analyst-bundle/SKILL.md"
    # ensure SKILL has proper frontmatter for compare
    if not skill_src.read_text(encoding="utf-8").startswith("---"):
        skill_src.write_text(
            "---\nname: cli-analyst-bundle\ndescription: demo\n---\n# body\n",
            encoding="utf-8",
            newline="\n",
        )
        # refresh pin not needed for this unit path after mutate — re-copy compare uses live
    sid, spath = create(skill_src)
    live_md = Path(spath) / "SKILL.md"
    before_paths = set(md.g.load_manifest(bk / "MANIFEST_BEFORE.txt"))
    real = md.register_skill_path(
        spath,
        str(box["workflows"]),
        str(box["agent_data"]),
        existed_before=before_paths,
    )
    md.compare_registered_skill(skill_src, live_md)
    writes = {
        box["allow"][0]: "# OPT\npatched\n",
        box["allow"][1]: "# POS\npatched\n",
        box["allow"][2]: "# QC\npatched\n",
        box["allow"][3]: json.dumps({"description": "patched"}, ensure_ascii=False),
        box["allow"][4]: "# spec\npatched\n",
    }
    md.run_phase_b_files(
        bk=bk,
        writes=writes,
        allowlist=box["allow"],
        tracked_paths=box["allow"],
        optimizer_yaml=box["opt_yaml"],
        optimizer_sha_before=opt_sha,
        new_skill_md_path=str(live_md.resolve()),
    )
    # skill visible under workflows
    assert (box["workflows_real"] / sid / "SKILL.md").is_file()
    assert md.sha256_file(box["opt_yaml"]) == opt_sha


def test_baseline_drift_stops(box: dict) -> None:
    base = _baseline(box)
    Path(box["allow"][0]).write_text("# OPT\ndrift\n", encoding="utf-8", newline="\n")
    with pytest.raises(SystemExit, match="baseline drift"):
        md.run_phase_a(
            deploy_op_id="pa-20261017-2301",
            bk=box["tmp"] / "bk2",
            baseline=base,
            tracked_paths=box["allow"],
            workflows=box["workflows_real"],
            optimizer_yaml=box["opt_yaml"],
        )


def test_preexisting_cli_skill_stops(box: dict) -> None:
    d = box["workflows_real"] / "skill-pre"
    d.mkdir()
    (d / "SKILL.md").write_text(
        "---\nname: cli-analyst-bundle\ndescription: x\n---\n#\n",
        encoding="utf-8",
        newline="\n",
    )
    with pytest.raises(SystemExit, match="already registered"):
        md.check_no_cli_skill(box["workflows_real"])


def test_platform_create_fail_no_file_changes(box: dict) -> None:
    md.verify_package(box["pkg"], _expect_hashes(box["pkg"]))
    bk = box["tmp"] / "bk3"
    base = _baseline(box)
    opt_sha = md.sha256_file(box["opt_yaml"])
    md.run_phase_a(
        deploy_op_id="pa-20261017-2302",
        bk=bk,
        baseline=base,
        tracked_paths=box["allow"],
        workflows=box["workflows_real"],
        optimizer_yaml=box["opt_yaml"],
    )
    store: dict = {}
    create = _make_create(box, store, fail=True)
    with pytest.raises(SystemExit, match="platform create"):
        create(box["pkg"] / "docs/analyst_skill_patch/cli-analyst-bundle/SKILL.md")
    # files unchanged vs baseline
    for p, h in base.items():
        assert md.sha256_file(Path(p)) == h
    assert md.sha256_file(box["opt_yaml"]) == opt_sha


def test_symlink_skill_root_accepted(box: dict) -> None:
    """agent-data → sand-data: path-check принимает путь под logical workflows."""
    store: dict = {}
    create = _make_create(box, store)
    skill_src = box["pkg"] / "docs/analyst_skill_patch/cli-analyst-bundle/SKILL.md"
    skill_src.write_text(
        "---\nname: cli-analyst-bundle\ndescription: demo\n---\n# body\n",
        encoding="utf-8",
        newline="\n",
    )
    sid, spath = create(skill_src)
    real = md.register_skill_path(
        spath,
        str(box["workflows"]),
        str(box["agent_data"]),
        existed_before=set(),
    )
    assert Path(real).is_dir()


def test_patch_failure_triggers_rollback(box: dict) -> None:
    md.verify_package(box["pkg"], _expect_hashes(box["pkg"]))
    bk = box["tmp"] / "bk4"
    base = _baseline(box)
    opt_sha = md.sha256_file(box["opt_yaml"])
    md.run_phase_a(
        deploy_op_id="pa-20261017-2303",
        bk=bk,
        baseline=base,
        tracked_paths=box["allow"],
        workflows=box["workflows_real"],
        optimizer_yaml=box["opt_yaml"],
    )
    store: dict = {}
    create = _make_create(box, store)
    skill_src = box["pkg"] / "docs/analyst_skill_patch/cli-analyst-bundle/SKILL.md"
    skill_src.write_text(
        "---\nname: cli-analyst-bundle\ndescription: demo\n---\n# body\n",
        encoding="utf-8",
        newline="\n",
    )
    sid, spath = create(skill_src)
    live_md = str((Path(spath) / "SKILL.md").resolve())
    # partial write then fail on unauthorized path
    md.apply_file_writes({box["allow"][0]: "# OPT\npartial\n"}, box["allow"])
    with pytest.raises(SystemExit, match="allowlist"):
        md.apply_file_writes({str(box["opt_yaml"]): "enabled: true\n"}, box["allow"])
    md.run_rollback(
        bk=bk,
        op_skill_id=sid,
        platform_delete=_make_delete(store),
        skill_path=spath,
    )
    assert md.sha256_file(Path(box["allow"][0])) == base[box["allow"][0]]
    assert store["created"] is None
    assert md.sha256_file(box["opt_yaml"]) == opt_sha
    assert not (box["workflows_real"] / sid).exists()


def test_refuse_delete_foreign_skill(box: dict) -> None:
    with pytest.raises(SystemExit, match="foreign"):
        md.refuse_delete_foreign("skill-AAA", "skill-BBB")


def test_manifest_detects_extra_file(box: dict) -> None:
    bk = box["tmp"] / "bk5"
    base = _baseline(box)
    md.run_phase_a(
        deploy_op_id="pa-20261017-2304",
        bk=bk,
        baseline=base,
        tracked_paths=box["allow"],
        workflows=box["workflows_real"],
        optimizer_yaml=box["opt_yaml"],
    )
    before = md.g.load_manifest(bk / "MANIFEST_BEFORE.txt")
    # sneak change outside allowlist
    outsider = box["sand"] / "workflows" / "skill-1791618014068" / "EXTRA.txt"
    outsider.write_text("x\n", encoding="utf-8")
    after = dict(before)
    after[md.g.canonicalize_path(str(outsider))] = md.sha256_file(outsider)
    with pytest.raises(SystemExit, match="allowlist"):
        md.verify_manifest_allowlist(before, after, box["allow"])


def test_active_op_blocks(box: dict) -> None:
    with pytest.raises(SystemExit, match="active deploy"):
        md.run_phase_a(
            deploy_op_id="pa-20261017-2305",
            bk=box["tmp"] / "bk6",
            baseline=_baseline(box),
            tracked_paths=box["allow"],
            workflows=box["workflows_real"],
            optimizer_yaml=box["opt_yaml"],
            active_ops=["pa-other"],
        )


def test_unexpected_skill_id_path_still_path_checked(box: dict) -> None:
    store: dict = {}
    weird = box["workflows_real"] / "skill-unexpected-name"
    create = _make_create(box, store, weird_path=weird)
    skill_src = box["pkg"] / "docs/analyst_skill_patch/cli-analyst-bundle/SKILL.md"
    skill_src.write_text(
        "---\nname: cli-analyst-bundle\ndescription: demo\n---\n# body\n",
        encoding="utf-8",
        newline="\n",
    )
    sid, spath = create(skill_src)
    assert sid == "skill-999000111222"
    assert "unexpected" in spath
    real = md.register_skill_path(
        spath, str(box["workflows"]), str(box["agent_data"]), existed_before=set()
    )
    assert Path(real).exists()


def test_exit_nonzero_on_hash_mismatch_cli(box: dict) -> None:
    import subprocess

    script = ROOT / "scripts" / "minimal_deploy.py"
    r = subprocess.run(
        [
            sys.executable,
            str(script),
            "verify-package",
            str(box["pkg"]),
            "--expect",
            "scripts/minimal_deploy.py=" + ("0" * 64),
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert r.returncode != 0
