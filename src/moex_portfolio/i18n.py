"""Internationalization — переводы интерфейса на русский и английский."""

from __future__ import annotations

_TRANSLATIONS: dict[str, dict[str, str]] = {
    # ─── General ───────────────────────────────────────────
    "app_title": {"ru": "Оптимизатор портфеля MOEX", "en": "MOEX Portfolio Optimizer"},
    "app_subtitle": {
        "ru": "Автоматический подбор оптимального инвестиционного портфеля акций MOEX",
        "en": "Automated optimal MOEX stock portfolio builder",
    },
    "language": {"ru": "Язык", "en": "Language"},
    "run_optimization": {"ru": "Запустить оптимизацию", "en": "Run Optimization"},
    "sidebar_params": {"ru": "Параметры", "en": "Parameters"},
    "export_results": {"ru": "Экспорт результатов", "en": "Export Results"},
    "profiles": {"ru": "Профили портфелей", "en": "Portfolio Profiles"},

    # ─── Sidebar ───────────────────────────────────────────
    "corr_threshold": {"ru": "Порог корреляции", "en": "Correlation threshold"},
    "min_turnover": {"ru": "Мин. дневной оборот (Млн ₽)", "en": "Min daily turnover (M RUB)"},
    "max_weight": {"ru": "Макс. вес актива (%)", "en": "Max weight per asset (%)"},
    "risk_free": {"ru": "Безрисковая ставка (год., %)", "en": "Risk-free rate (annual, %)"},
    "cov_method": {"ru": "Метод ковариации", "en": "Covariance method"},
    "mc_sims": {"ru": "Симуляций Монте-Карло", "en": "Monte Carlo simulations"},
    "rebal_freq": {"ru": "Частота ребалансировки (дни)", "en": "Rebalance frequency (days)"},
    "trans_cost": {"ru": "Транзакционные издержки (bps)", "en": "Transaction cost (bps)"},
    "bl_tau": {"ru": "Black-Litterman tau", "en": "Black-Litterman tau"},
    "bl_views": {"ru": "BL: кол-во авто-views", "en": "BL: auto-views count"},
    "hrp_method": {"ru": "HRP кластеризация", "en": "HRP clustering"},
    "use_cache": {"ru": "Использовать кэш данных", "en": "Use cached data"},

    # ─── Status messages ───────────────────────────────────
    "loading_shares": {"ru": "Загрузка списка акций MOEX...", "en": "Loading stock list from MOEX..."},
    "found_shares": {"ru": "Найдено акций на MOEX: {}", "en": "Found {} stocks on MOEX"},
    "loading_prices": {"ru": "Загрузка цен...", "en": "Loading price data..."},
    "filtering": {"ru": "Фильтрация и расчёт доходностей...", "en": "Filtering and computing returns..."},
    "after_filter": {"ru": "После фильтрации: {} акций, {} периодов", "en": "After filtering: {} stocks, {} periods"},
    "found_clique": {"ru": "Найдена клика из {} акций: {}", "en": "Found clique with {} stocks: {}"},
    "no_clique": {"ru": "Клика не найдена. Попробуйте увеличить порог корреляции.", "en": "No clique found. Try increasing the correlation threshold."},
    "configure_hint": {
        "ru": "Настройте параметры в боковой панели и нажмите **Запустить оптимизацию**.",
        "en": "Configure parameters in the sidebar and click **Run Optimization** to start.",
    },

    # ─── Tabs ──────────────────────────────────────────────
    "tab_portfolio": {"ru": "Портфель", "en": "Portfolio"},
    "tab_frontier": {"ru": "Граница эффективности", "en": "Efficient Frontier"},
    "tab_mc": {"ru": "Монте-Карло", "en": "Monte Carlo"},
    "tab_graphs": {"ru": "Граф анализ", "en": "Graph Analysis"},
    "tab_analysis": {"ru": "Детальный анализ", "en": "Detailed Analysis"},
    "tab_rebal": {"ru": "Ребалансировка", "en": "Rebalancing"},
    "tab_stress": {"ru": "Стресс-тест", "en": "Stress Test"},
    "tab_bl": {"ru": "Black-Litterman", "en": "Black-Litterman"},
    "tab_hrp": {"ru": "HRP", "en": "HRP"},
    "tab_rolling": {"ru": "Скользящая корреляция", "en": "Rolling Correlation"},
    "tab_dividends": {"ru": "Дивиденды", "en": "Dividends"},
    "tab_fundamental": {"ru": "Фундаментальный анализ", "en": "Fundamental Analysis"},
    "tab_bonds": {"ru": "Облигации", "en": "Bonds"},
    "tab_merton": {"ru": "Модель Мертона", "en": "Merton Model"},
    "tab_backtest": {"ru": "Бэктестинг", "en": "Backtesting"},
    "tab_risk_budget": {"ru": "Бюджет риска", "en": "Risk Budget"},
    "tab_drawdowns": {"ru": "Просадки", "en": "Drawdowns"},
    "tab_multi": {"ru": "Мульти-активный", "en": "Multi-Asset"},
    "tab_benchmark": {"ru": "Бенчмарк", "en": "Benchmark"},

    # ─── Portfolio tab ─────────────────────────────────────
    "opt_portfolio": {"ru": "Оптимальный портфель (Макс. Sharpe)", "en": "Optimal Portfolio (Max Sharpe)"},
    "ann_return": {"ru": "Годовая доходность", "en": "Annual Return"},
    "ann_vol": {"ru": "Годовая волатильность", "en": "Annual Volatility"},
    "sharpe": {"ru": "Коэффициент Шарпа", "en": "Sharpe Ratio"},
    "rf_rate": {"ru": "Безрисковая ставка", "en": "Risk-free Rate"},
    "var_95": {"ru": "VaR (95%)", "en": "VaR (95%)"},
    "cvar_95": {"ru": "CVaR (95%)", "en": "CVaR (95%)"},
    "sortino": {"ru": "Коэффициент Сортино", "en": "Sortino Ratio"},
    "cov_method_label": {"ru": "Метод ковариации", "en": "Cov Method"},
    "portfolio_growth": {"ru": "Рост капитала портфеля", "en": "Portfolio Growth"},
    "min_var_portfolio": {"ru": "Портфель минимальной дисперсии", "en": "Min Variance Portfolio"},
    "min_var_weights": {"ru": "Веса мин. дисперсии", "en": "Min Variance Weights"},

    # ─── Frontier tab ──────────────────────────────────────
    "frontier_title": {"ru": "Граница эффективности", "en": "Efficient Frontier"},

    # ─── Monte Carlo tab ───────────────────────────────────
    "mc_title": {"ru": "Симуляция Монте-Карло", "en": "Monte Carlo Simulation"},
    "mc_mean_return": {"ru": "Средняя доходность", "en": "Mean Return"},
    "mc_mean_vol": {"ru": "Средняя волатильность", "en": "Mean Volatility"},
    "mc_mean_dd": {"ru": "Средняя макс. просадка", "en": "Mean Max DD"},
    "mc_sims_label": {"ru": "Симуляций", "en": "Simulations"},
    "mc_confidence": {"ru": "Доверительные интервалы", "en": "Confidence Intervals"},

    # ─── Graph Analysis tab ────────────────────────────────
    "graph_title": {"ru": "Анализ графа корреляций", "en": "Correlation Graph Analysis"},

    # ─── Analysis tab ──────────────────────────────────────
    "analysis_title": {"ru": "Анализ отдельных акций", "en": "Individual Stock Analysis"},
    "returns_stats": {"ru": "Статистика доходностей", "en": "Returns Statistics"},

    # ─── Rebalancing tab ──────────────────────────────────
    "rebal_title": {"ru": "Симуляция ребалансировки", "en": "Rebalancing Simulation"},
    "rebal_return": {"ru": "Доходность ребаланс.", "en": "Rebalancing Return"},
    "rebal_sharpe": {"ru": "Sharpe ребаланс.", "en": "Rebalancing Sharpe"},
    "rebal_cost": {"ru": "Общие издержки", "en": "Total Cost"},
    "rebal_count": {"ru": "Ребалансировок", "en": "Rebalances"},
    "bh_return": {"ru": "Доходность B&H", "en": "B&H Return"},
    "bh_sharpe": {"ru": "Sharpe B&H", "en": "B&H Sharpe"},
    "bh_maxdd": {"ru": "Макс. просадка B&H", "en": "B&H Max DD"},
    "rebal_maxdd": {"ru": "Макс. просадка ребаланс.", "en": "Rebalancing Max DD"},
    "strategy_comp": {"ru": "Сравнение стратегий", "en": "Strategy Comparison"},

    # ─── Stress Test tab ──────────────────────────────────
    "stress_title": {"ru": "Стресс-тестирование на исторических кризисах", "en": "Stress Testing on Historical Crises"},
    "stress_details": {"ru": "Детали сценария", "en": "Scenario Details"},
    "stress_return": {"ru": "Доходность портфеля", "en": "Portfolio Return"},
    "stress_worst": {"ru": "Худший день", "en": "Worst Day"},
    "stress_recovery": {"ru": "Восстановление", "en": "Recovery"},

    # ─── Black-Litterman tab ──────────────────────────────
    "bl_title": {"ru": "Модель Black-Litterman", "en": "Black-Litterman Model"},
    "bl_desc": {
        "ru": "Объединяет рыночное равновесие с ожиданиями инвестора для более стабильных весов.",
        "en": "Combines market equilibrium with investor views for more stable portfolio weights.",
    },
    "bl_views_count": {"ru": "Использовано views", "en": "Views Used"},
    "bl_views_matrix": {"ru": "Матрица views (P)", "en": "Views Matrix (P)"},
    "bl_view_returns": {"ru": "Ожидаемые доходности views (Q)", "en": "View Returns (Q)"},
    "bl_comparison": {"ru": "Сравнение: Markowitz vs Black-Litterman", "en": "Comparison: Markowitz vs Black-Litterman"},

    # ─── HRP tab ──────────────────────────────────────────
    "hrp_title": {"ru": "Иерархический риск-паритет (HRP)", "en": "Hierarchical Risk Parity (HRP)"},
    "hrp_desc": {
        "ru": "Кластерное распределение активов — не требует обращения матрицы ковариации.",
        "en": "Clustering-based portfolio allocation — no need for matrix inversion.",
    },
    "hrp_weight_dist": {"ru": "Распределение весов", "en": "Weight Distribution"},
    "hrp_strategy_comp": {"ru": "Сравнение стратегий", "en": "Strategy Comparison"},
    "hrp_method_label": {"ru": "Метод", "en": "Method"},

    # ─── Rolling tab ──────────────────────────────────────
    "rolling_title": {"ru": "Анализ скользящей корреляции", "en": "Rolling Correlation Analysis"},
    "rolling_window": {"ru": "Скользящее окно (дни)", "en": "Rolling window (days)"},
    "rolling_beta": {"ru": "Скользящая бета", "en": "Rolling Beta"},

    # ─── Dividends tab ────────────────────────────────────
    "div_title": {"ru": "Дивидендные стратегии", "en": "Dividend Strategies"},
    "div_desc": {
        "ru": "Dogs of the Dow, High Dividend Yield и Equal Weight — на основе реальных данных MOEX.",
        "en": "Dogs of the Dow, High Dividend Yield, and Equal Weight — using real MOEX dividend data.",
    },
    "div_dogs_n": {"ru": "Dogs of the Dow: N акций", "en": "Dogs of the Dow: N stocks"},
    "div_hd_pct": {"ru": "High Div: процентиль", "en": "High Div: percentile"},

    # ─── Fundamental tab ──────────────────────────────────
    "fund_title": {"ru": "Фундаментальный анализ", "en": "Fundamental Analysis"},
    "fund_desc": {
        "ru": "Рейтинг акций с реальными данными MOEX (P/E, P/B, капитализация) + метрики доходности.",
        "en": "Stock ranking with real MOEX data (P/E, P/B, Market Cap) + returns-based metrics.",
    },
    "fund_composite": {"ru": "Композитный рейтинг", "en": "Composite Ranking"},
    "fund_top_n": {"ru": "Топ N акций по скору", "en": "Top N stocks by score"},

    # ─── Bonds tab ────────────────────────────────────────
    "bonds_title": {"ru": "Анализ облигаций (ОФЗ)", "en": "Bond Analysis (OFZ)"},
    "bonds_desc": {
        "ru": "Кривая доходности, дюрация, конвексити — на основе данных MOEX ISS.",
        "en": "Yield curve, duration, convexity — based on MOEX ISS bond data.",
    },
    "bonds_yield_curve": {"ru": "Кривая доходности (ОФЗ)", "en": "Yield Curve (OFZ)"},
    "bonds_interp": {"ru": "Интерполированная кривая доходности", "en": "Interpolated Yield Curve"},
    "bonds_shape": {"ru": "Форма", "en": "Shape"},
    "bonds_short": {"ru": "Краткосрочная доходность", "en": "Short Yield"},
    "bonds_long": {"ru": "Долгосрочная доходность", "en": "Long Yield"},
    "bonds_spread": {"ru": "Терм. спред", "en": "Term Spread"},

    # ─── Merton tab ──────────────────────────────────────
    "merton_title": {"ru": "Структурная модель кредитного риска Мертона", "en": "Merton Structural Credit Risk Model"},
    "merton_desc": {
        "ru": "Оценка вероятности дефолта с помощью фреймворка Black-Scholes.",
        "en": "Estimate probability of default using Black-Scholes framework.",
    },
    "merton_eq": {"ru": "Стоимость капитала (Млн ₽)", "en": "Equity Value (M RUB)"},
    "merton_debt": {"ru": "Номинал долга (Млн ₽)", "en": "Debt Face Value (M RUB)"},
    "merton_vol": {"ru": "Волатильность капитала (%)", "en": "Equity Volatility (%)"},
    "merton_rf": {"ru": "Безрисковая ставка (%)", "en": "Risk-Free Rate (%)"},
    "merton_ttm": {"ru": "Срок до погашения (лет)", "en": "Time to Maturity (years)"},
    "merton_run": {"ru": "Запустить анализ Мертона", "en": "Run Merton Analysis"},
    "merton_dd": {"ru": "Расстояние до дефолта", "en": "Distance to Default"},
    "merton_pd": {"ru": "Вероятность дефолта", "en": "Probability of Default"},
    "merton_spread": {"ru": "Кредитный спред", "en": "Credit Spread"},
    "merton_recovery": {"ru": "Ставка восстановления", "en": "Recovery Rate"},
    "merton_implied": {"ru": "Подразумеваемые активы", "en": "Implied Assets"},
    "merton_vol_a": {"ru": "Волатильность активов", "en": "Assets Volatility"},
    "merton_leverage": {"ru": "Плечо", "en": "Leverage"},
    "merton_model_eq": {"ru": "Модельный капитал", "en": "Model Equity"},

    # ─── Backtesting tab ──────────────────────────────────
    "bt_title": {"ru": "Walk-Forward бэктестинг", "en": "Walk-Forward Backtesting"},
    "bt_desc": {
        "ru": "Переоптимизация портфеля с оценкой out-of-sample доходности.",
        "en": "Re-optimizes portfolio periodically and evaluates out-of-sample performance.",
    },
    "bt_lookback": {"ru": "Окно просмотра (дни)", "en": "Lookback window (days)"},
    "bt_rebal_freq": {"ru": "Частота ребалансировки (дни)", "en": "Rebalance frequency (days)"},
    "bt_optimizer": {"ru": "Оптимизатор", "en": "Optimizer"},
    "bt_run": {"ru": "Запустить бэктест", "en": "Run Backtest"},
    "bt_total_ret": {"ru": "Общая доходность", "en": "Total Return"},
    "bt_ann_ret": {"ru": "Годовая доходность", "en": "Annual Return"},
    "bt_sharpe": {"ru": "Sharpe", "en": "Sharpe"},
    "bt_maxdd": {"ru": "Макс. просадка", "en": "Max Drawdown"},
    "bt_rebalances": {"ru": "Ребалансировок", "en": "Rebalances"},
    "bt_turnover": {"ru": "Средний тёрновер", "en": "Avg Turnover"},
    "bt_growth": {"ru": "Рост капитала", "en": "Portfolio Growth"},
    "bt_comparison": {"ru": "Таблица сравнения", "en": "Comparison Table"},

    # ─── Risk Budget tab ──────────────────────────────────
    "rb_title": {"ru": "Бюджетирование риска", "en": "Risk Budgeting"},
    "rb_desc": {
        "ru": "Какие активы вносят наибольший вклад в риск портфеля?",
        "en": "Which assets contribute most to portfolio risk?",
    },
    "rb_port_vol": {"ru": "Волатильность портфеля", "en": "Portfolio Volatility"},
    "rb_max_contrib": {"ru": "Макс. вкладчик в риск", "en": "Max Risk Contributor"},
    "rb_max_pct": {"ru": "Макс. % риска", "en": "Max Risk %"},
    "rb_erc_title": {"ru": "Равный риск-вклад (ERC)", "en": "Equal Risk Contribution (ERC)"},

    # ─── Drawdowns tab ────────────────────────────────────
    "dd_title": {"ru": "Анализ просадок", "en": "Drawdown Analysis"},
    "dd_desc": {
        "ru": "Детальный анализ просадок портфеля — худшие периоды, время восстановления.",
        "en": "Detailed analysis of portfolio drawdowns — worst periods, recovery times.",
    },
    "dd_max": {"ru": "Макс. просадка", "en": "Max Drawdown"},
    "dd_avg": {"ru": "Средняя просадка", "en": "Avg Drawdown"},
    "dd_recovery": {"ru": "Среднее восст. (дни)", "en": "Avg Recovery (days)"},
    "dd_periods": {"ru": "Периоды просадок", "en": "Drawdown Periods"},
    "dd_worst": {"ru": "Худшая просадка", "en": "Worst Drawdown"},
    "dd_peak": {"ru": "Дата пика", "en": "Peak Date"},
    "dd_trough": {"ru": "Дата дна", "en": "Trough Date"},
    "dd_recovery_date": {"ru": "Восстановление", "en": "Recovery"},
    "dd_underwater": {"ru": "Underwater-график", "en": "Underwater Chart"},
    "dd_top_periods": {"ru": "Топ периодов просадок", "en": "Top Drawdown Periods"},

    # ─── Multi-Asset tab ──────────────────────────────────
    "ma_title": {"ru": "Мульти-активный портфель (акции + облигации)", "en": "Multi-Asset Portfolio (Stocks + Bonds)"},
    "ma_desc": {
        "ru": "Комбинирование акций и облигаций в одном оптимизированном портфеле для лучшей диверсификации.",
        "en": "Combine stocks and bonds in one optimized portfolio for better diversification.",
    },
    "ma_bond_alloc": {"ru": "Доля облигаций", "en": "Bond Allocation"},
    "ma_ofz_use": {"ru": "Использовать кривую доходности ОФЗ как доходность облигаций", "en": "Use OFZ yield curve as bond returns"},
    "ma_constraints": {"ru": "Ограничения распределения активов", "en": "Asset Allocation Constraints"},
    "ma_max_stock": {"ru": "Макс. доля акций (%)", "en": "Max stock allocation (%)"},
    "ma_min_bond": {"ru": "Мин. доля облигаций (%)", "en": "Min bond allocation (%)"},
    "ma_run": {"ru": "Запустить мульти-активную оптимизацию", "en": "Run Multi-Asset Optimization"},
    "ma_stock_bond": {"ru": "Акции/Облигации", "en": "Stock/Bond"},

    # ─── Benchmark tab ────────────────────────────────────
    "bm_title": {"ru": "Сравнение с бенчмарком", "en": "Benchmark Comparison"},
    "bm_desc": {
        "ru": "Сравнение вашего портфеля с индексом MOEX (IMOEX) или гос. облигациями (RGBI).",
        "en": "Compare your portfolio against MOEX index (IMOEX) or government bonds (RGBI).",
    },
    "bm_index": {"ru": "Индекс-бенчмарк", "en": "Benchmark Index"},
    "bm_port_ret": {"ru": "Доходность портфеля", "en": "Portfolio Return"},
    "bm_index_ret": {"ru": "Доходность индекса", "en": "Index Return"},
    "bm_excess": {"ru": "Избыточная доходность", "en": "Excess Return"},
    "bm_te": {"ru": "Трекинг-ошибка", "en": "Tracking Error"},
    "bm_ir": {"ru": "Коэффициент информационности", "en": "Information Ratio"},
    "bm_r2": {"ru": "R²", "en": "R²"},
    "bm_beta": {"ru": "Бета", "en": "Beta"},
    "bm_alpha": {"ru": "Альфа Дженсена", "en": "Jensen's Alpha"},
    "bm_full_table": {"ru": "Полная таблица сравнения", "en": "Full Comparison Table"},
    "bm_cumulative": {"ru": "Накопленная доходность", "en": "Cumulative Returns"},
    "bm_active": {"ru": "Активная доходность (портфель - бенчмарк)", "en": "Active Returns (Portfolio - Benchmark)"},
    "bm_rolling_ir": {"ru": "Скользящий IR (60д)", "en": "Rolling Information Ratio (60d)"},

    # ─── Export ────────────────────────────────────────────
    "export_excel": {"ru": "Скачать Excel-отчёт", "en": "Download Excel Report"},
    "export_pdf": {"ru": "Скачать PDF-отчёт", "en": "Download PDF Report"},

    # ─── Profiles ─────────────────────────────────────────
    "profile_name": {"ru": "Название профиля", "en": "Profile name"},
    "profile_save": {"ru": "Сохранить профиль", "en": "Save Profile"},
    "profile_saved": {"ru": "Профиль '{}' сохранён!", "en": "Profile '{}' saved!"},
    "profile_load": {"ru": "Загрузить профиль", "en": "Load profile"},
    "profile_load_btn": {"ru": "Загрузить", "en": "Load Profile"},
    "profile_none": {"ru": "Нет сохранённых профилей.", "en": "No saved profiles yet."},

    # ─── How it works ─────────────────────────────────────
    "how_title": {"ru": "Как это работает", "en": "How it works"},
    "how_step1": {"ru": "**Загрузка данных**: Скачивает историю цен всех акций MOEX через ISS API", "en": "**Data Loading**: Downloads price history for all MOEX stocks via ISS API"},
    "how_step2": {"ru": "**Фильтрация**: Убирает неликвидные акции и аномальные данные", "en": "**Filtering**: Removes illiquid stocks and anomalous data"},
    "how_step3": {"ru": "**Граф корреляций**: Строит граф, где рёбра соединяют слабо коррелирующие акции", "en": "**Correlation Graph**: Builds a graph where edges connect weakly correlated stocks"},
    "how_step4": {"ru": "**Поиск клики**: Находит максимальную группу взаимно некоррелированных акций", "en": "**Clique Detection**: Finds the largest group of mutually uncorrelated stocks"},
    "how_step5": {"ru": "**Оптимизация**: Markowitz Mean-Variance со сжатием Ledoit-Wolf", "en": "**Optimization**: Markowitz Mean-Variance with Ledoit-Wolf covariance shrinkage"},
    "how_step6": {"ru": "**Анализ рисков**: Монте-Карло, VaR/CVaR, кривая капитала", "en": "**Risk Analysis**: Monte Carlo simulation, VaR/CVaR, equity curve"},
    "how_step7": {"ru": "**Экспорт**: Скачайте полный Excel-отчёт со всеми результатами", "en": "**Export**: Download full Excel report with all results"},
}


def t(key: str, *args: object, lang: str = "en") -> str:
    """Вернуть переведённую строку по ключу.

    Args:
        key: Ключ словаря переводов.
        *args: Позиционные аргументы для форматирования строки (str.format).
        lang: Язык ('ru' или 'en').

    Returns:
        Переведённая и отформатированная строка.
    """
    entry = _TRANSLATIONS.get(key)
    if entry is None:
        return key
    text = entry.get(lang, entry.get("en", key))
    if args:
        text = text.format(*args)
    return text
