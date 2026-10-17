"""Регрессия guards SAFE_DEPLOY (BL7–BL9, 4c): symlink/junction mock, fail-closed."""

from __future__ import annotations

import hashlib
import os
import re
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "safe_deploy_guards.py"
sys.path.insert(0, str(ROOT / "scripts"))
import safe_deploy_guards as g  # noqa: E402

_SD = ROOT / "docs" / "analyst_skill_patch" / "SAFE_DEPLOY.md"


def _sd_text() -> str:
    return g.read_text_no_universal_newlines(_SD)


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


def test_n41_orphan_indented_key_after_plain_scalar() -> None:
    """Indented key-like line after plain description must fail (N41)."""
    text = (
        "---\nname: cli-analyst-bundle\ndescription: x\n"
        "  allowed: all\n---\n\n# Body\n"
    )
    with pytest.raises(SystemExit, match="orphan indented"):
        g.split_skill_md(text)


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


def _env_for_validate(symlink_box: dict[str, Path], tmp_path: Path) -> dict[str, str]:
    agents = symlink_box["sand"] / "agents" / "5bda2f3d-a61a-48d6-8663-2441802d68de"
    agents.mkdir(parents=True, exist_ok=True)
    deploy = tmp_path / "deploy-root"
    deploy.mkdir(exist_ok=True)
    skill_real = str(symlink_box["workflows_real"].resolve())
    return {
        "BK": str(deploy.resolve()),
        "DEPLOY_ROOT": str(deploy.resolve()),
        "WF": skill_real,
        "SKILL_ROOT_REAL": skill_real,
        "SKILL_ROOT_LOGICAL": str(symlink_box["skill_root_logical"]),
        "AGENT_DATA_LOGICAL": str(symlink_box["agent_logical"]),
        "AGENT_REAL": str(agents.resolve()),
        "REPO_ROOT": str(ROOT),
    }


def test_n43_agent_real_root_rejected(
    symlink_box: dict[str, Path], tmp_path: Path
) -> None:
    env = _env_for_validate(symlink_box, tmp_path)
    env["AGENT_REAL"] = "/"
    with pytest.raises(SystemExit, match="unsafe|root|absolute|short"):
        g.validate_deploy_env(env, need_repo=True)


def test_n44_wf_must_equal_skill_root_real(
    symlink_box: dict[str, Path], tmp_path: Path
) -> None:
    env = _env_for_validate(symlink_box, tmp_path)
    env["WF"] = str(tmp_path / "other-wf")
    (tmp_path / "other-wf").mkdir()
    with pytest.raises(SystemExit, match="WF != SKILL_ROOT_REAL"):
        g.validate_deploy_env(env, need_repo=True)


def test_validate_env_ok(symlink_box: dict[str, Path], tmp_path: Path) -> None:
    env = _env_for_validate(symlink_box, tmp_path)
    g.validate_deploy_env(env, need_repo=True)


def test_n39_extract_safe_deploy_steps() -> None:
    blocks = g.extract_bash_steps(_sd_text())
    assert len(blocks) >= 6
    with_validate = [b for b in blocks if "validate-env" in b]
    assert len(with_validate) >= 5, f"expected validate-env in steps, got {len(with_validate)}"
    with_agent_case = [b for b in blocks if "AGENT_REAL" in b and '"/"' in b]
    assert with_agent_case, "SAFE_DEPLOY steps must case-reject AGENT_REAL=/"
    # BL11: каждый шаг с validate-env обязан export'ить или передавать BK= в env
    for b in with_validate:
        assert "export BK" in b or 'BK="$BK"' in b, "BL11: validate-env without env pass-through"
        assert "|| exit" in b


def test_n39_integrity_ok_on_real_sd() -> None:
    md = _sd_text()
    g.assert_safe_deploy_integrity(md)
    g.assert_safe_deploy_block_hashes(md)


def test_n39_block_hash_detects_any_step_mutation() -> None:
    """Любая правка критического bash-блока → drift hash (закрывает N1–N7)."""
    md = _sd_text()
    g.assert_safe_deploy_block_hashes(md)
    mutated = md.replace("4b ok", "4b ok MUTATED", 1)
    with pytest.raises(SystemExit, match="hash drift|document hash|fence"):
        g.assert_safe_deploy_block_hashes(mutated)
    # N2-style: comment out validate-env in 10a
    blocks = g.extract_bash_steps(md)
    step10a = next(b for b in blocks if 'cp -a "$BK/profile.json"' in b)
    import re as _re
    bad, nsub = _re.subn(
        r"python3[^\n]*validate-env",
        lambda m: ": # " + m.group(0),
        step10a,
        count=1,
    )
    assert nsub == 1
    with pytest.raises(SystemExit, match="hash drift|document hash|fence|missing validate"):
        g.assert_safe_deploy_block_hashes(md.replace(step10a, bad))
    # N6: 4c || true
    step4c = next(b for b in blocks if "skill-compare" in b and "LIVE_SKILL" in b)
    bad4c = step4c.replace("|| exit 1", "|| true")
    with pytest.raises(SystemExit, match="hash drift|document hash|fence"):
        g.assert_safe_deploy_block_hashes(md.replace(step4c, bad4c))


def test_n39_document_pin_catches_a1_a18_outside_critical_blocks() -> None:
    """A1–A3/A5/A6/A16–A18: мутации вне 9 named blocks → document/fence pin."""
    md = _sd_text()
    g.assert_safe_deploy_block_hashes(md)
    anchor = "## 4. Регистрация skill + патчи"
    assert anchor in md

    # A1: новый ```bash с rm -rf между шагами 3 и 4
    a1 = md.replace(
        anchor,
        "```bash\nrm -rf \"$WF/skill-1791618014068\"\n```\n\n" + anchor,
        1,
    )
    with pytest.raises(SystemExit, match="document hash|fence count"):
        g.assert_safe_deploy_block_hashes(a1)

    # A2: ```sh
    a2 = md.replace(
        anchor,
        "```sh\nrm -rf \"$WF/skill-1791618014068\"\n```\n\n" + anchor,
        1,
    )
    with pytest.raises(SystemExit, match="document hash|fence count"):
        g.assert_safe_deploy_block_hashes(a2)

    # A3: fence без языка
    a3 = md.replace(
        anchor,
        "```\nrm -rf \"$WF/skill-1791618014068\"\n```\n\n" + anchor,
        1,
    )
    with pytest.raises(SystemExit, match="document hash|fence count"):
        g.assert_safe_deploy_block_hashes(a3)

    # A5/A6: правка непрочитанного prose / хвост документа
    a5 = md + "\n<!-- injected -->\n"
    with pytest.raises(SystemExit, match="document hash"):
        g.assert_safe_deploy_block_hashes(a5)

    # A16: мутация порядка/содержимого fence (маркер в первом bash)
    a16 = md.replace("```bash\n", "```bash\n# reorder-marker\n", 1)
    with pytest.raises(SystemExit, match="document hash|fence"):
        g.assert_safe_deploy_block_hashes(a16)

    # A17: ложь в prose про fail-closed
    a17 = md.replace("fail-closed", "fail-open CONTINUE ON ERROR", 1)
    if a17 == md:
        a17 = md + "\n4c continues without confirmation.\n"
    with pytest.raises(SystemExit, match="document hash"):
        g.assert_safe_deploy_block_hashes(a17)

    # A18: убрать ключевое предупреждение
    assert "не выполнять без подтверждения" in md
    a18 = md.replace("не выполнять без подтверждения", "", 1)
    assert a18 != md
    with pytest.raises(SystemExit, match="document hash"):
        g.assert_safe_deploy_block_hashes(a18)

    # N49: CR в файле — отказ на read (не universal newlines Path.read_text)
    evil_path = Path(__file__).resolve().parent / "_tmp_sd_cr.md"
    evil_path.write_bytes(b"line1\r\nline2\n")
    try:
        with pytest.raises(SystemExit, match=r"CR"):
            g.read_text_no_universal_newlines(evil_path)
    finally:
        evil_path.unlink(missing_ok=True)

    # N47: expect-document / expect-fixture mismatch → rc≠0
    with pytest.raises(SystemExit, match="expect-document"):
        g.assert_safe_deploy_block_hashes(md, expect_document="0" * 64)
    fix = ROOT / "tests" / "fixtures" / "safe_deploy_block_hashes.json"
    with pytest.raises(SystemExit, match="expect-fixture"):
        g.assert_safe_deploy_block_hashes(md, fix, expect_fixture="0" * 64)
    g.assert_safe_deploy_block_hashes(
        md,
        fix,
        expect_document=g.document_sha256(md),
        expect_fixture=hashlib.sha256(fix.read_bytes()).hexdigest(),
    )


def test_n39_mutations_m1_m4_detected() -> None:
    """Мутации M1–M4 из review Песочницы должны валить integrity (N39)."""
    md = _sd_text()
    g.assert_safe_deploy_integrity(md)

    # M1: вырезать validate-env и case AGENT_REAL только из блока 10a
    blocks = g.extract_bash_steps(md)
    step10a = next(b for b in blocks if 'cp -a "$BK/profile.json"' in b)
    bad10a = step10a.replace("validate-env", "GONE").replace(
        'case "$AGENT_REAL"', 'case "$NOT_AGENT"'
    )
    mut1 = md.replace(step10a, bad10a)
    with pytest.raises(SystemExit, match="step10a"):
        g.assert_safe_deploy_integrity(mut1)

    # M2: вырезать guards из шага 3
    step3 = next(b for b in blocks if "MANIFEST_BEFORE" in b and "noclobber" in b)
    bad3 = "\n".join(
        ln
        for ln in step3.splitlines()
        if "validate-env" not in ln and "export BK" not in ln and "case" not in ln
    )
    mut2 = md.replace(step3, bad3)
    with pytest.raises(SystemExit, match="step3"):
        g.assert_safe_deploy_integrity(mut2)

    # M3: убрать || exit 1 после path-check в 4b
    step4b = next(b for b in blocks if "4b ok" in b)
    bad4b = re.sub(
        r"(path-check[\s\S]{0,200}?)\|\|\s*exit\s+1",
        r"\1",
        step4b,
        count=1,
    )
    mut3 = md.replace(step4b, bad4b)
    with pytest.raises(SystemExit, match="path-check missing"):
        g.assert_safe_deploy_integrity(mut3)

    # M4: добавить чужой skill в allowlist
    step6 = next(b for b in blocks if "allowed_exact" in b and "MANIFEST_AFTER" in b)
    bad6 = step6.replace(
        'g.canonicalize_path("/workspace/invest/portfolio/analysis_spec.md"),',
        'g.canonicalize_path("/workspace/invest/portfolio/analysis_spec.md"),\n'
        '    g.canonicalize_path("/home/box/agent-data/workflows/skill-1791457276248/SKILL.md"),',
    )
    mut4 = md.replace(step6, bad6)
    with pytest.raises(SystemExit, match="allowlist mismatch"):
        g.assert_safe_deploy_integrity(mut4)

    # M5: убрать export из шага 2
    step2 = next(b for b in blocks if "BEFORE_MARKER" in b)
    bad2 = "\n".join(ln for ln in step2.splitlines() if "export BK" not in ln)
    mut5 = md.replace(step2, bad2)
    with pytest.raises(SystemExit, match="missing export BK"):
        g.assert_safe_deploy_integrity(mut5)

    # M6: || true вместо || exit
    bad10a_true = step10a.replace("|| exit 1", "|| true")
    mut6 = md.replace(step10a, bad10a_true)
    with pytest.raises(SystemExit, match=r"\|\| exit"):
        g.assert_safe_deploy_integrity(mut6)

    # M8: отключить сравнение хешей
    bad6_false = step6.replace("before.get(f) != h", "False")
    mut8 = md.replace(step6, bad6_false)
    with pytest.raises(SystemExit, match="before.get"):
        g.assert_safe_deploy_integrity(mut8)

    # M9: set +e
    bad4b_sete = step4b.replace("set -euo pipefail", "set +e", 1)
    mut9 = md.replace(step4b, bad4b_sete)
    with pytest.raises(SystemExit, match="set -euo pipefail"):
        g.assert_safe_deploy_integrity(mut9)




def test_n49_check_hashes_cli_rejects_crlf_file(tmp_path: Path) -> None:
    """N54: check-hashes на файле с CR → rc≠0 (не через read_text)."""
    raw = _SD.read_bytes()
    evil = tmp_path / "sd_crlf.md"
    evil.write_bytes(raw.replace(b"\n", b"\r\n"))
    fix = ROOT / "tests" / "fixtures" / "safe_deploy_block_hashes.json"
    r = subprocess.run(
        [sys.executable, str(SCRIPT), "check-hashes", str(evil), str(fix)],
        check=False,
        capture_output=True,
        text=True,
    )
    assert r.returncode != 0, r.stdout + r.stderr
    assert "CR" in (r.stderr + r.stdout)


def test_n55_missing_final_lf_changes_document_hash() -> None:
    md = _sd_text()
    assert md.endswith("\n")
    assert g.document_sha256(md) != g.document_sha256(md[:-1])

def test_n45_rejects_agents_under_workflows(
    symlink_box: dict[str, Path], tmp_path: Path
) -> None:
    """workflows/agents/<id> не должен проходить (N45 parent check)."""
    env = _env_for_validate(symlink_box, tmp_path)
    fake = (
        symlink_box["workflows_real"]
        / "agents"
        / "5bda2f3d-a61a-48d6-8663-2441802d68de"
    )
    fake.mkdir(parents=True)
    env["AGENT_REAL"] = str(fake.resolve())
    with pytest.raises(SystemExit, match="parent must be"):
        g.validate_deploy_env(env, need_repo=True)


def test_n39_execute_step2_preamble_from_sd(
    symlink_box: dict[str, Path], tmp_path: Path
) -> None:
    """Прогнать preamble шага 2 из реального SAFE_DEPLOY.md (не копию)."""
    md = _sd_text()
    step2 = next(b for b in g.extract_bash_steps(md) if "BEFORE_MARKER" in b)
    # только guard до touch
    preamble = step2.split("touch")[0]
    assert "validate-env" in preamble
    env = _env_for_validate(symlink_box, tmp_path)
    # успех
    r = subprocess.run(
        [sys.executable, str(SCRIPT), "validate-env", "--need-repo"],
        check=False,
        capture_output=True,
        text=True,
        env={**os.environ, **env},
    )
    assert r.returncode == 0, r.stderr + r.stdout
    # AGENT_REAL=/ как в SD case + validate
    bad = dict(env)
    bad["AGENT_REAL"] = "/"
    r2 = subprocess.run(
        [sys.executable, str(SCRIPT), "validate-env", "--need-repo"],
        check=False,
        capture_output=True,
        text=True,
        env={**os.environ, **bad},
    )
    assert r2.returncode != 0


def test_n45_agent_real_must_be_under_agents(
    symlink_box: dict[str, Path], tmp_path: Path
) -> None:
    env = _env_for_validate(symlink_box, tmp_path)
    env["AGENT_REAL"] = str(symlink_box["sand"].resolve())  # корень agent-data real
    with pytest.raises(SystemExit, match="parent must be"):
        g.validate_deploy_env(env, need_repo=True)
    agents_only = symlink_box["sand"] / "agents"
    agents_only.mkdir(exist_ok=True)
    env["AGENT_REAL"] = str(agents_only.resolve())
    with pytest.raises(SystemExit, match="parent must be|unexpected agent id"):
        g.validate_deploy_env(env, need_repo=True)
    wrong = symlink_box["sand"] / "agents" / "00000000-0000-0000-0000-000000000000"
    wrong.mkdir(exist_ok=True)
    env["AGENT_REAL"] = str(wrong.resolve())
    with pytest.raises(SystemExit, match="unexpected agent id"):
        g.validate_deploy_env(env, need_repo=True)


def test_bl11_validate_env_missing_without_export() -> None:
    """Без переменных в environ validate-env обязан упасть (BL11)."""
    clean = {k: v for k, v in os.environ.items() if k not in {
        "BK", "WF", "AGENT_REAL", "DEPLOY_ROOT", "SKILL_ROOT_REAL",
        "SKILL_ROOT_LOGICAL", "AGENT_DATA_LOGICAL", "REPO_ROOT",
    }}
    r = subprocess.run(
        [sys.executable, str(SCRIPT), "validate-env", "--need-repo"],
        check=False,
        capture_output=True,
        text=True,
        env=clean,
    )
    assert r.returncode != 0
    assert "missing" in (r.stderr + r.stdout).lower() or r.returncode != 0
