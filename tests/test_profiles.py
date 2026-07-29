"""Тесты модуля profiles."""


from moex_portfolio.profiles import (
    delete_profile,
    list_profiles,
    load_profile,
    save_profile,
)


def test_save_and_load_profile(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "moex_portfolio.profiles.PROFILES_DIR", tmp_path
    )
    clique = ["SBER", "GAZP", "LKOH"]
    weights = {"SBER": 0.4, "GAZP": 0.3, "LKOH": 0.3}
    metrics = {"return": 0.15, "volatility": 0.20, "sharpe": 0.75}

    path = save_profile("test_port", clique, weights, metrics)
    assert path.exists()

    loaded = load_profile("test_port")
    assert loaded["name"] == "test_port"
    assert loaded["clique"] == clique
    assert loaded["weights"] == weights
    assert loaded["metrics"]["return"] == 0.15


def test_list_profiles(tmp_path, monkeypatch):
    monkeypatch.setattr("moex_portfolio.profiles.PROFILES_DIR", tmp_path)
    save_profile("alpha", ["A"], {"A": 1.0})
    save_profile("beta", ["B"], {"B": 1.0})

    profiles = list_profiles()
    assert "alpha" in profiles
    assert "beta" in profiles


def test_delete_profile(tmp_path, monkeypatch):
    monkeypatch.setattr("moex_portfolio.profiles.PROFILES_DIR", tmp_path)
    save_profile("to_delete", ["X"], {"X": 1.0})
    assert delete_profile("to_delete") is True
    assert delete_profile("to_delete") is False


def test_load_nonexistent_profile(tmp_path, monkeypatch):
    import pytest
    monkeypatch.setattr("moex_portfolio.profiles.PROFILES_DIR", tmp_path)
    with pytest.raises(FileNotFoundError):
        load_profile("does_not_exist")


def test_profile_with_none_metrics(tmp_path, monkeypatch):
    monkeypatch.setattr("moex_portfolio.profiles.PROFILES_DIR", tmp_path)
    save_profile("null_metrics", ["A"], {"A": 1.0}, metrics={"sharpe": None})
    loaded = load_profile("null_metrics")
    assert loaded["metrics"]["sharpe"] is None
