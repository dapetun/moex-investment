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
    assert re.search(r"skill draft v2\.[3-9]", skill_text)
    assert "skill draft v2.2" not in skill_text
