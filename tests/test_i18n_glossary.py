"""Tests for i18n and glossary modules."""

import pytest

from moex_portfolio.glossary import get_all_terms, get_glossary_entry
from moex_portfolio.i18n import t


class TestI18n:
    def test_t_english(self):
        result = t("app_title", lang="en")
        assert "Portfolio Optimizer" in result

    def test_t_russian(self):
        result = t("app_title", lang="ru")
        assert "Оптимизатор" in result

    def test_t_with_format_args(self):
        result = t("found_shares", 42, lang="en")
        assert "42" in result

    def test_t_unknown_key(self):
        result = t("nonexistent_key_xyz", lang="en")
        assert result == "nonexistent_key_xyz"

    def test_t_fallback_to_english(self):
        result = t("app_title", lang="fr")
        assert "Portfolio Optimizer" in result

    def test_all_tab_keys_exist(self):
        tab_keys = [
            "tab_portfolio", "tab_frontier", "tab_mc", "tab_graphs", "tab_analysis",
            "tab_rebal", "tab_stress", "tab_bl", "tab_hrp", "tab_rolling",
            "tab_dividends", "tab_fundamental", "tab_bonds", "tab_merton",
            "tab_backtest", "tab_risk_budget", "tab_drawdowns", "tab_multi", "tab_benchmark",
        ]
        for key in tab_keys:
            assert t(key, lang="en") != key, f"Key '{key}' not translated"
            assert t(key, lang="ru") != key, f"Key '{key}' not translated to Russian"


class TestGlossary:
    def test_get_existing_term_en(self):
        result = get_glossary_entry("Sharpe Ratio", lang="en")
        assert result is not None
        assert "risk" in result.lower()

    def test_get_existing_term_ru(self):
        result = get_glossary_entry("Sharpe Ratio", lang="ru")
        assert result is not None
        assert "риск" in result.lower()

    def test_get_nonexistent_term(self):
        result = get_glossary_entry("FakeTerm")
        assert result is None

    def test_get_all_terms_en(self):
        terms = get_all_terms(lang="en")
        assert "Sharpe Ratio" in terms
        assert len(terms) > 20

    def test_get_all_terms_ru(self):
        terms = get_all_terms(lang="ru")
        assert "Sharpe Ratio" in terms
        assert len(terms) > 20

    def test_glossary_coverage(self):
        important_terms = [
            "Sharpe Ratio", "Sortino Ratio", "Annual Return", "Annual Volatility",
            "VaR (95%)", "CVaR (95%)", "Efficient Frontier", "Black-Litterman",
            "HRP", "Monte Carlo", "Drawdown", "Max Drawdown", "Beta",
            "Rebalancing", "Yield Curve", "Duration", "Convexity",
        ]
        for term in important_terms:
            assert get_glossary_entry(term, lang="en") is not None, f"Missing EN: {term}"
            assert get_glossary_entry(term, lang="ru") is not None, f"Missing RU: {term}"
