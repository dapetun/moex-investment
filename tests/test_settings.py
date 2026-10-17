"""Тесты конфигурации окружения (гейт ISS)."""

from moex_portfolio.settings import get_data_source_name, iss_enabled


def test_iss_disabled_by_default(monkeypatch):
    monkeypatch.delenv("MOEX_ISS_ENABLED", raising=False)
    assert iss_enabled() is False


def test_iss_enabled_true(monkeypatch):
    monkeypatch.setenv("MOEX_ISS_ENABLED", "true")
    assert iss_enabled() is True


def test_default_source_is_fixture(monkeypatch):
    monkeypatch.delenv("MOEX_ISS_ENABLED", raising=False)
    monkeypatch.delenv("MOEX_DATA_SOURCE", raising=False)
    assert get_data_source_name() == "fixture"
