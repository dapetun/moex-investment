"""Дефолтные значения параметров с теоретическим обоснованием.

Все значения основаны на академической литературе и рыночных стандартах:
- Markowitz (1952) "Portfolio Selection"
- Sharpe (1966) "Mutual Fund Performance"
- Black & Litterman (1992) "Global Portfolio Optimization"
- Lopez de Prado (2016) "Building Diversified Portfolios that Outperform OOS"
- CFA Institute best practices
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class Defaults:
    """Все дефолтные значения параметров дашборда.

    Атрибуты сгруппированы по категориям.
    """

    # ─── Фильтрация данных ──────────────────────────────────
    corr_threshold: float = 0.25
    """Markowitz: низкая корреляция < 0.3-0.5 обеспечивает диверсификацию.
    0.25 — консервативный порог, гарантирующий слабую связь."""

    min_turnover_m: int = 50
    """50M RUB — минимум для MOEX акций с приемлемой ликвидностью.
    Ниже — проблемы с исполнением сделок."""

    min_observations: int = 500
    """~2 года торговых дней. Достаточно для статистически значимых
    оценок ковариации (Ledoit & Wolf, 2004)."""

    max_daily_change: float = 0.80
    """80% — фильтр аномалий (делистинг, ошибки данных).
    Реальные однодневные движения >50% крайне редки."""

    # ─── Оптимизация портфеля ───────────────────────────────
    max_weight: float = 0.30
    """30% — стандартное ограничение концентрации.
    CFA Institute рекомендует max 5-10%, но для small universe 30% допустимо."""

    risk_free_rate: float = 16.0
    """Текущая ключевая ставка ЦБ РФ (2024-2025 ~16%).
    Для long-only портфеля — альтернативная доходность OFZ."""

    cov_method: str = "ledoit_wolf"
    """Ledoit-Wolf (2004) — оптимальное сжатие ковариационной матрицы.
    Лучше sample при малом числе наблюдений/акций (N > T)."""

    mc_simulations: int = 10_000
    """10,000 — стандарт для Monte Carlo (Christoffersen 2011).
    Достаточно для стабильных квантилей VaR/CVaR."""

    # ─── Корреляционный анализ ───────────────────────────────
    ewma_span: int = 60
    """60 дней (~3 месяца) — баланс между чувствительностью
    к новым данным и стабильностью оценки (Engle 2009)."""

    rolling_window: int = 60
    """60 дней — стандартный rolling window для корреляций
    и беты (3-месячное окно, Barra best practices)."""

    # ─── Rebalancing ────────────────────────────────────────
    rebalance_freq_days: int = 21
    """21 день (~1 торговый месяц) — компромисс между
    следованием за целевыми весами и транзакционными издержками."""

    transaction_cost_bps: float = 10.0
    """10 bps (0.1%) — средние транзакционные издержки
    на MOEX для рыночных ордеров (без спреда)."""

    min_drift: float = 0.05
    """5% — порог отклонения весов от целевых для rebalancing.
    Ниже — rebalancing будет слишком частым и дорогим."""

    # ─── Black-Litterman ─────────────────────────────────────
    bl_tau: float = 0.05
    """5% —不确定度 views (Idzorek 2005).
    0.01-0.1 — типичный диапазон, 0.05 — центральное значение."""

    bl_n_views: int = 5
    """5 views — баланс между информативностью
    и стабильностью (Black-Litterman 1992)."""

    # ─── HRP ─────────────────────────────────────────────────
    hrp_method: str = "single"
    """Ward's method (single linkage) — стандарт для HRP
    (Lopez de Prado 2016)."""

    # ─── Кэширование ────────────────────────────────────────
    cache_max_age_hours: int = 24
    """24 часа — рыночные данные обновляются раз в день.
    Кэш старше 1 дня считается устаревшим."""


DEFAULTS = Defaults()


def get_defaults_dict() -> dict:
    """Возвращает словарь всех дефолтных значений."""
    return {
        "corr_threshold": DEFAULTS.corr_threshold,
        "min_turnover_m": DEFAULTS.min_turnover_m,
        "max_weight": DEFAULTS.max_weight,
        "risk_free_rate": DEFAULTS.risk_free_rate,
        "cov_method": DEFAULTS.cov_method,
        "mc_simulations": DEFAULTS.mc_simulations,
        "rebalance_freq_days": DEFAULTS.rebalance_freq_days,
        "transaction_cost_bps": DEFAULTS.transaction_cost_bps,
        "bl_tau": DEFAULTS.bl_tau,
        "bl_n_views": DEFAULTS.bl_n_views,
        "hrp_method": DEFAULTS.hrp_method,
        "ewma_span": DEFAULTS.ewma_span,
        "rolling_window": DEFAULTS.rolling_window,
        "min_drift": DEFAULTS.min_drift,
        "max_daily_change": DEFAULTS.max_daily_change,
        "min_observations": DEFAULTS.min_observations,
    }
