"""Тесты отчётов MD/JSON."""

from moex_portfolio.reporting import write_report


def test_write_report_creates_md_and_json(tmp_path, monkeypatch):
    monkeypatch.setattr("moex_portfolio.reporting.REPORTS_DIR", tmp_path)
    paths = write_report(
        run_id="testrun",
        title="Test report",
        payload={"weights": {"AAA": 1.0}, "success": True},
    )
    assert paths["json"].exists()
    assert paths["md"].exists()
    md = paths["md"].read_text(encoding="utf-8")
    assert "Test report" in md
    assert "AAA" in md
