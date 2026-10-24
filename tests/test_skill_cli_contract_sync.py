"""Согласованность cli-analyst-bundle/SKILL.md с CLI-контрактом до deploy."""

from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SKILL = ROOT / "docs" / "analyst_skill_patch" / "cli-analyst-bundle" / "SKILL.md"
CLI = ROOT / "src" / "moex_portfolio" / "cli.py"
BUNDLE = ROOT / "src" / "moex_portfolio" / "analyst_bundle.py"
CONTRACT = ROOT / "docs" / "CLI_CONTRACT.md"
FLOW_FIXTURE = ROOT / "tests" / "fixtures" / "radar_events_cli_bundle_flow.json"


@pytest.fixture(scope="module")
def skill_text() -> str:
    return SKILL.read_text(encoding="utf-8")


def test_flow_fixture_exists_and_is_test_release():
    assert FLOW_FIXTURE.is_file()
    raw = FLOW_FIXTURE.read_text(encoding="utf-8")
    assert '"schema_version": "1.1"' in raw or '"schema_version":"1.1"' in raw
    assert '"is_test": true' in raw or '"is_test":true' in raw
    assert "TEST-EV-20261018-AAA-FLOW-001" in raw
    assert "TEST-EV-20261018-BBB-FLOW-001" in raw


def test_skill_documents_synthetic_smoke_fixture_and_forbids_live_news(skill_text: str):
    rel = "tests/fixtures/radar_events_cli_bundle_flow.json"
    assert rel in skill_text
    assert "ingest-events" in skill_text
    assert "--test-events" in skill_text
    assert "--source tests/fixtures/radar_events_cli_bundle_flow.json" in skill_text
    assert "/workspace/invest/news/events_latest.json" in skill_text
    assert "не читать" in skill_text.lower() or "**не читать**" in skill_text
    # в синтетическом smoke нельзя подменять события live news
    assert "Синтетический тест с событиями" in skill_text
    assert "Permission A" in skill_text


def test_skill_requires_run_ids_and_diagnostics_on_errors(skill_text: str):
    assert "--run-ids" in skill_text
    assert "RUN_IDS_REQUIRED" in skill_text
    assert "RUN_NOT_FOUND" in skill_text
    assert "неполный bundle" in skill_text
    assert "диагностик" in skill_text
    assert "--compare-json" in skill_text
    assert "--validation-json" in skill_text
    assert "--ingest-json" in skill_text
    assert "runs_count >= 2" in skill_text
    assert "events_count >= 2" in skill_text
    assert "TEST-EV-20261018-AAA-FLOW-001" in skill_text
    assert "TEST-EV-20261018-BBB-FLOW-001" in skill_text


def test_cli_contract_documents_run_id_error_codes():
    text = CONTRACT.read_text(encoding="utf-8")
    assert "RUN_IDS_REQUIRED" in text
    assert "RUN_NOT_FOUND" in text
    assert "build-analyst-bundle" in text


def test_cli_source_emits_run_id_error_codes():
    cli_src = CLI.read_text(encoding="utf-8")
    bun_src = BUNDLE.read_text(encoding="utf-8")
    assert "RUN_IDS_REQUIRED" in bun_src
    assert "RUN_NOT_FOUND" in bun_src
    assert "RUN_IDS_REQUIRED" in cli_src
    assert "RUN_NOT_FOUND" in cli_src
    assert 'code = "RUN_IDS_REQUIRED"' in cli_src or '"RUN_IDS_REQUIRED"' in cli_src


def test_skill_mentions_every_build_analyst_bundle_cli_flag(skill_text: str):
    """Флаги парсера build-analyst-bundle, критичные для smoke, есть в skill."""
    tree = ast.parse(CLI.read_text(encoding="utf-8"))
    flags: set[str] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        # p_bun.add_argument("--run-ids", ...)
        if not isinstance(node.func, ast.Attribute):
            continue
        if node.func.attr != "add_argument":
            continue
        if not node.args:
            continue
        arg0 = node.args[0]
        if isinstance(arg0, ast.Constant) and isinstance(arg0.value, str):
            if arg0.value.startswith("--"):
                flags.add(arg0.value)

    required = {
        "--run-ids",
        "--test-events",
        "--compare-json",
        "--validation-json",
        "--ingest-json",
        "--target",
        "--out-dir",
    }
    missing_in_parser = required - flags
    assert not missing_in_parser, f"parser missing flags: {missing_in_parser}"
    missing_in_skill = {f for f in required if f not in skill_text}
    assert not missing_in_skill, f"SKILL.md missing CLI flags: {missing_in_skill}"


def test_skill_version_bumped_past_v2_2(skill_text: str):
    assert re.search(r"^# CLI ↔ Аналитик портфеля \(skill draft v2\.5\)$", skill_text, re.M)
    assert "skill draft v2.2" not in skill_text
    assert "skill draft v2.3" not in skill_text
    assert "skill draft v2.4" not in skill_text


LIFECYCLE_REQUIRED = {
    "propose-portfolio": {"--prices", "--tickers"},
    "fund-plan": {"--weights-json", "--budget", "--currency"},
    "read-snapshot": {"--csv"},
    "estimate-weights": {"--snapshot-json", "--valuation-date"},
}


def _required_flags_by_command(source: str) -> dict[str, set[str]]:
    tree = ast.parse(source)
    build = next(
        node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == "build_parser"
    )
    command_by_parser: dict[str, str] = {}
    found: dict[str, set[str]] = {name: set() for name in LIFECYCLE_REQUIRED}
    for stmt in build.body:
        if isinstance(stmt, ast.Assign) and len(stmt.targets) == 1 and isinstance(stmt.targets[0], ast.Name):
            call = stmt.value
            if (
                isinstance(call, ast.Call)
                and isinstance(call.func, ast.Attribute)
                and call.func.attr == "add_parser"
                and call.args
                and isinstance(call.args[0], ast.Constant)
                and isinstance(call.args[0].value, str)
            ):
                command_by_parser[stmt.targets[0].id] = call.args[0].value
        if not isinstance(stmt, ast.Expr) or not isinstance(stmt.value, ast.Call):
            continue
        call = stmt.value
        if not isinstance(call.func, ast.Attribute) or call.func.attr != "add_argument":
            continue
        if not isinstance(call.func.value, ast.Name):
            continue
        command = command_by_parser.get(call.func.value.id)
        if command not in LIFECYCLE_REQUIRED or not call.args:
            continue
        flag = call.args[0]
        if not isinstance(flag, ast.Constant) or not isinstance(flag.value, str):
            continue
        required = any(
            kw.arg == "required" and isinstance(kw.value, ast.Constant) and kw.value.value is True
            for kw in call.keywords
        )
        if required:
            found[command].add(flag.value)
    return found


def test_skill_documents_lifecycle_commands_and_required_args(skill_text: str):
    found = _required_flags_by_command(CLI.read_text(encoding="utf-8"))
    assert found == LIFECYCLE_REQUIRED
    for command, flags in LIFECYCLE_REQUIRED.items():
        assert command in skill_text
        missing = {flag for flag in flags if flag not in skill_text}
        assert not missing, f"{command} missing in skill: {missing}"
    for marker in (
        "proposed",
        "funded",
        "actual",
        "estimated: true",
        "estimation_method: relative_returns",
        "--price-return-only",
        "--corporate-actions",
        "--cash-return",
        "Permission A",
        "Permission B",
        "last_target",
        "moex_analyst_bundle.v1",
        "не вход solver",
    ):
        assert marker in skill_text
    contract = CONTRACT.read_text(encoding="utf-8")
    for command in LIFECYCLE_REQUIRED:
        assert command in contract
    profile = (ROOT / "docs/analyst_skill_patch/live_patches/PROFILE_DESCRIPTION.patch.md").read_text(
        encoding="utf-8"
    )
    assert "## Изменение 1 — D04" in profile
    assert "## Изменение 4 — вставка после блока «Оптимизатор»" in profile
    assert "Изменение 5" in profile
    assert "bundle не заменяет вход радара" in profile
    for command in LIFECYCLE_REQUIRED:
        assert command in profile


def test_n1_proposed_weights_are_not_optimize_target(skill_text: str):
    assert "project_not_holdings" in skill_text
    assert "execution_recommendation: false" in skill_text
    assert "preferred_strategy: null" in skill_text
    assert "model_estimate: true" in skill_text
    assert "Стадии портфеля (не целевые веса)" in skill_text
    assert "не является `optimize --allow-optimize`" in skill_text
    assert "Самостоятельный `propose-portfolio`" in skill_text
    assert "она не блокирует" in skill_text
    assert "явная фраза" in skill_text
    assert "Запрос на стадию не разрешает optimize" in skill_text
    profile = (ROOT / "docs/analyst_skill_patch/live_patches/PROFILE_DESCRIPTION.patch.md").read_text(
        encoding="utf-8"
    )
    opt = (ROOT / "docs/analyst_skill_patch/live_patches/OPT_SKILL.patch.md").read_text(encoding="utf-8")
    pos = (ROOT / "docs/analyst_skill_patch/live_patches/POS_SKILL.patch.md").read_text(encoding="utf-8")
    contract = CONTRACT.read_text(encoding="utf-8")
    for text in (profile, opt, pos, skill_text):
        assert "Стадии портфеля (не целевые веса)" in text
        assert "last_target" in text
    assert "last_target" in contract
    assert "Изменение 6" in opt
    assert "Изменение 4" in pos
    assert "project_not_holdings" in contract
    assert "не holdings и не target" in contract


def test_n3_test_events_flag_is_not_universal(skill_text: str):
    assert "общим требованием не является" in skill_text
    assert "Обычная сборка без нового импорта" in skill_text
    assert "Синтетический тест событий" in skill_text
    assert "Production-события" in skill_text
    assert "processed/events_test" in skill_text
    assert "events_count=0" in skill_text
    assert "RUN_IDS_REQUIRED" in skill_text
    assert "RUN_NOT_FOUND" in skill_text
    assert "TEST-EV-" in skill_text
    forbidden = "`--run-ids`, `--test-events` и приёмка bundle остаются обязательными"
    assert forbidden not in skill_text
    contract = CONTRACT.read_text(encoding="utf-8")
    assert "EVENT_TEST_MODE_REQUIRED" in contract
    assert "EVENT_PROD_IN_TEST_MODE" in contract
    assert "`--test-events` у этой команды не обязателен" in contract
