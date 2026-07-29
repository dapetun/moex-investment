"""Глоссарий финансовых терминов — подсказки для дашборда."""

from __future__ import annotations

_GLOSSARY: dict[str, dict[str, str]] = {
    # ─── Portfolio metrics ─────────────────────────────────
    "Sharpe Ratio": {
        "ru": "Коэффициент Шарпа — отношение избыточной доходности портфеля к его волатильности. Показывает, сколько дополнительной доходности вы получаете за каждый единицу риска. Чем выше — тем лучше. Нормальные значения: 0.5–1.0, хорошие: 1.0–2.0, отличные: >2.0.",
        "en": "Sharpe Ratio — excess portfolio return divided by its volatility. Shows how much additional return you get per unit of risk. Higher is better. Normal: 0.5–1.0, good: 1.0–2.0, excellent: >2.0.",
    },
    "Sortino Ratio": {
        "ru": "Коэффициент Сортино — как Шарпа, но учитывает только «плохую» волатильность (просадки). Более точно измеряет.reward-to-risk, наказывая за падения, но не за рост.",
        "en": "Sortino Ratio — like Sharpe, but considers only downside volatility (drawdowns). More accurately measures reward-to-risk by penalizing only losses, not gains.",
    },
    "Annual Return": {
        "ru": "Годовая доходность — среднегодовая норма прироста портфеля. Рассчитывается как (1 + средняя_дневная)²⁵² − 1. Не учитывает реинвестирование.",
        "en": "Annual Return — average annual growth rate of the portfolio. Calculated as (1 + mean_daily)²⁵² − 1. Does not account for compounding.",
    },
    "Annual Volatility": {
        "ru": "Годовая волатильность — стандартное отклонение дневных доходностей, умноженное на √252. Показывает разброс доходности. Чем ниже — тем стабильнее портфель.",
        "en": "Annual Volatility — standard deviation of daily returns multiplied by √252. Shows the dispersion of returns. Lower = more stable portfolio.",
    },
    "Risk-free Rate": {
        "ru": "Безрисковая ставка — доходность, которую можно получить без риска (обычно ставка по ОФЗ или депозиты ЦБ). Используется как базовая линия при расчёте Sharpe, Treynor и др.",
        "en": "Risk-free Rate — return achievable without risk (typically OFZ yields or central bank rates). Used as a baseline when calculating Sharpe, Treynor, etc.",
    },
    "VaR (95%)": {
        "ru": "Value at Risk — максимальный убыток с вероятностью 95%. Означает: в 5% худших дней портфель теряет не более этой суммы. Чем ниже (ближе к нулю) — тем безопаснее.",
        "en": "Value at Risk — maximum loss at 95% confidence. Means: in 5% worst days the portfolio loses no more than this amount. Lower (closer to zero) = safer.",
    },
    "CVaR (95%)": {
        "ru": "Conditional Value at Risk (Expected Shortfall) — средний убыток в худших 5% дней. Более консервативная мера риска, чем VaR, так как учитывает тяжесть худших сценариев.",
        "en": "Conditional Value at Risk (Expected Shortfall) — average loss in the worst 5% of days. More conservative risk measure than VaR, as it accounts for severity of worst scenarios.",
    },

    # ─── Optimization ──────────────────────────────────────
    "Efficient Frontier": {
        "ru": "Граница эффективности — множество портфелей, дающих максимальную доходность для каждого уровня риска. Точки выше и левее — более эффективны. Оптимальные портфели находятся на этой кривой.",
        "en": "Efficient Frontier — set of portfolios offering maximum return for each risk level. Points higher and to the left are more efficient. Optimal portfolios lie on this curve.",
    },
    "Max Sharpe": {
        "ru": "Портфель с максимальным коэффициентом Шарпа — «наиболее эффективный» портфель, дающий лучшее соотношение доходности к риску.",
        "en": "Maximum Sharpe portfolio — the 'most efficient' portfolio, offering the best return-to-risk ratio.",
    },
    "Min Variance": {
        "ru": "Портфель минимальной дисперсии — портфель с наименьшей волатильностью среди всех возможных комбинаций. Подходит консервативным инвесторам.",
        "en": "Minimum Variance portfolio — portfolio with the lowest volatility among all possible combinations. Suitable for conservative investors.",
    },
    "Black-Litterman": {
        "ru": "Модель Black-Litterman — объединяет рыночное равновесие (implied returns) с субъективными ожиданиями инвестора (views). Даёт более стабильные веса, чем классический Markowitz, устраняя проблему чувствительности к ожидаемым доходностям.",
        "en": "Black-Litterman model — combines market equilibrium (implied returns) with subjective investor expectations (views). Produces more stable weights than classical Markowitz by eliminating sensitivity to expected returns.",
    },
    "HRP": {
        "ru": "Hierarchical Risk Parity — аллокация на основе кластерного анализа. Сначала группирует активы по схожести, затем рекурсивно делит веса между кластерами. Не требует обращения матрицы ковариации — устойчив к ошибкам оценки.",
        "en": "Hierarchical Risk Parity — allocation based on cluster analysis. Groups assets by similarity, then recursively bisects weights between clusters. Doesn't require covariance matrix inversion — robust to estimation errors.",
    },

    # ─── Risk metrics ──────────────────────────────────────
    "Monte Carlo": {
        "ru": "Монте-Карло — метод симуляции thousands случайных сценариев на основе статистических свойств портфеля. Позволяет оценить распределение будущей доходности, просадок и Sharpe.",
        "en": "Monte Carlo — simulation method generating thousands of random scenarios based on portfolio's statistical properties. Allows estimating distribution of future returns, drawdowns, and Sharpe.",
    },
    "Drawdown": {
        "ru": "Просадка — падение портфеля от пика до дна в процентах. Например, просадка -20% означает, что портфель упал на 20% от максимального значения. Ключевой показатель для понимания риска.",
        "en": "Drawdown — decline of portfolio from peak to trough in percentage terms. For example, -20% drawdown means the portfolio fell 20% from its maximum value. Key metric for understanding risk.",
    },
    "Max Drawdown": {
        "ru": "Максимальная просадка — худшее падение портфеля за весь период. Важнейший показатель для понимания худшего сценария. Чем меньше — тем лучше.",
        "en": "Maximum Drawdown — worst portfolio decline over the entire period. Most important metric for understanding worst-case scenario. Smaller is better.",
    },
    "Distance to Default": {
        "ru": "Расстояние до дефолта (модель Мертона) — количество стандартных отклонений, на которое рыночная стоимость активов превышает порог дефолта. >3 — безопасно, <1 — высокий риск.",
        "en": "Distance to Default (Merton model) — number of standard deviations by which asset market value exceeds the default threshold. >3 = safe, <1 = high risk.",
    },
    "Probability of Default": {
        "ru": "Вероятность дефолта (модель Мертона) — оценка вероятности того, что компания не сможет выплатить долг. Рассчитывается через модель Black-Scholes. <5% — низкий риск, >20% —非常高.",
        "en": "Probability of Default (Merton model) — estimated likelihood that a company will be unable to repay its debt. Calculated via Black-Scholes model. <5% = low risk, >20% = very high.",
    },
    "Credit Spread": {
        "ru": "Кредитный спред — разница доходности корпоративных облигаций и безрисковых. Компенсирует инвестору кредитный риск. Высокий спред = рынок оценивает компанию как рискованную.",
        "en": "Credit Spread — difference between corporate bond yield and risk-free yield. Compensates investor for credit risk. High spread = market perceives the company as risky.",
    },

    # ─── Covariance methods ────────────────────────────────
    "sample": {
        "ru": "Выборочная ковариация — классический метод оценки через эмпирическую ковариационную матрицу. Прост, но нестабилен при малом числе наблюдений или большом числе активов.",
        "en": "Sample covariance — classic estimation method using the empirical covariance matrix. Simple, but unstable with few observations or many assets.",
    },
    "ledoit_wolf": {
        "ru": "Сжатие Ledoit-Wolf — статистический метод улучшения оценки ковариационной матрицы. Сдвигает выборочную матрицу к диагональной, уменьшая шум. Рекомендуется при >30 акций.",
        "en": "Ledoit-Wolf shrinkage — statistical method for improving covariance matrix estimation. Shrinks sample matrix toward diagonal, reducing noise. Recommended when >30 stocks.",
    },
    "ewma": {
        "ru": "EWMA (Exponentially Weighted Moving Average) — ковариация с экспоненциально убывающими весами. Последние данные важнее старых. Хорошо ловит изменения в корреляционной структуре.",
        "en": "EWMA (Exponentially Weighted Moving Average) — covariance with exponentially decaying weights. Recent data weighted more heavily than old. Good at capturing changes in correlation structure.",
    },

    # ─── Rebalancing ──────────────────────────────────────
    "Rebalancing": {
        "ru": "Ребалансировка — периодическая корректировка весов портфеля к целевым значениям. Не даёт портфелю «уплыть» из-за неравномерного роста активов. Транзакционные издержки — комиссии за сделки.",
        "en": "Rebalancing — periodic adjustment of portfolio weights to target values. Prevents portfolio from drifting due to uneven asset growth. Transaction costs are trading commissions.",
    },
    "Buy & Hold": {
        "ru": "Buy & Hold — стратегия «купи и держи». Покупаете портфель один раз и не меняете веса. Сравнивается с ребалансировкой для оценки эффективности стратегии.",
        "en": "Buy & Hold — strategy of buying a portfolio once and never adjusting weights. Compared with rebalancing to evaluate strategy effectiveness.",
    },

    # ─── Other ─────────────────────────────────────────────
    "Correlation": {
        "ru": "Корреляция — статистическая мера связи между двумя активами. Варьируется от -1 (идеально противоположные) до +1 (идеально одинаковые). 0 = нет связи. Низкая корреляция = хорошая диверсификация.",
        "en": "Correlation — statistical measure of the relationship between two assets. Ranges from -1 (perfectly opposite) to +1 (perfectly aligned). 0 = no relationship. Low correlation = good diversification.",
    },
    "Clique": {
        "ru": "Клика в графе — максимальное множество вершин, где каждая пара вершин соединена ребром. В нашем контексте: группа акций, где КАЖДАЯ ПАРА имеет корреляцию ниже порога.",
        "en": "Clique in a graph — maximum set of vertices where every pair is connected by an edge. In our context: a group of stocks where EVERY PAIR has correlation below the threshold.",
    },
    "Dogs of the Dow": {
        "ru": "Dogs of the Dow — стратегия: купить 10 акций из Dow Jones с самой высокой дивидендной доходностью. Основана на предположении, что «недооценённые» акции с высокими дивидендами восстановятся.",
        "en": "Dogs of the Dow — strategy: buy 10 Dow Jones stocks with highest dividend yield. Based on the premise that 'undervalued' high-dividend stocks will recover.",
    },
    "Treynor Ratio": {
        "ru": "Коэффициент Трейнора — отношение избыточной доходности портфеля к его бете. Показывает доходность за единицу рыночного риска. Подходит для диверсифицированных портфелей.",
        "en": "Treynor Ratio — excess portfolio return divided by its beta. Shows return per unit of market risk. Suitable for diversified portfolios.",
    },
    "Modigliani M²": {
        "ru": "M² (Модильяни) —.adjusted доходность портфеля, приведённая к волатильности рыночного портфеля. Позволяет сравнивать портфели с разным риском в процентах доходности.",
        "en": "M² (Modigliani) — portfolio return adjusted to match market volatility. Allows comparing portfolios with different risk levels in percentage return terms.",
    },
    "Jensen's Alpha": {
        "ru": "Альфа Дженсена — разность между фактической доходностью портфеля и ожидаемой по CAPM. Положительная альфа = портфель обыграл рынок с учётом риска. Отрицательная = проиграл.",
        "en": "Jensen's Alpha — difference between actual portfolio return and CAPM-expected return. Positive alpha = portfolio outperformed the market on a risk-adjusted basis. Negative = underperformed.",
    },
    "Tracking Error": {
        "ru": "Трекинг-ошибка — стандартное отклонение разности доходностей портфеля и бенчмарка. Показывает, насколько активное управление отклоняется от индекса. Низкая = близко к бенчмарку.",
        "en": "Tracking Error — standard deviation of the difference between portfolio and benchmark returns. Shows how much active management deviates from the index. Low = close to benchmark.",
    },
    "Information Ratio": {
        "ru": "Коэффициент информационности — отношение избыточной доходности (над бенчмарком) к трекинг-ошибке. Показывает эффективность активного управления. >0.5 — хорошо, >1.0 — отлично.",
        "en": "Information Ratio — excess return (over benchmark) divided by tracking error. Shows effectiveness of active management. >0.5 = good, >1.0 = excellent.",
    },
    "R²": {
        "ru": "Коэффициент детерминации — доля дисперсии доходности портфеля, объясняемая бенчмарком. R²=1.0 означает полное копирование индекса. Низкий R² = высокая доля собственных решений.",
        "en": "R-squared — proportion of portfolio return variance explained by the benchmark. R²=1.0 means perfect index tracking. Low R² = high proportion of independent decisions.",
    },
    "Beta": {
        "ru": "Бета — чувствительность портфеля к рыночным движениям. Бета=1.0 = портфель движется как рынок. Бета>1.0 = более волатильный, <1.0 = менее волатильный. Бета<0 = движется против рынка.",
        "en": "Beta — portfolio sensitivity to market movements. Beta=1.0 = portfolio moves with the market. Beta>1.0 = more volatile, <1.0 = less volatile. Beta<0 = moves opposite to market.",
    },
    "Risk Budget": {
        "ru": "Бюджет риска — анализ, какой вклад каждый актив вносит в общий риск портфеля. Помогает понять, какие акции «опаснее», чем кажутся по весу.",
        "en": "Risk Budget — analysis of each asset's contribution to total portfolio risk. Helps understand which stocks are 'riskier' than their weight suggests.",
    },
    "ERC": {
        "ru": "Equal Risk Contribution — метод аллокации, при котором каждый актив вносит равный вклад в общий риск. Более сбалансирован, чем классический Sharpe-оптимизатор.",
        "en": "Equal Risk Contribution — allocation method where each asset contributes equally to total risk. More balanced than classical Sharpe optimization.",
    },
    "Yield Curve": {
        "ru": "Кривая доходности — график зависимости доходности облигации от срока погашения. Нормальная — положительный наклон. Инвертированная — предвестник рецессии. Плоская — неопределённость.",
        "en": "Yield Curve — graph of bond yield vs. maturity. Normal — positive slope. Inverted — recession predictor. Flat — uncertainty.",
    },
    "Duration": {
        "ru": "Дюрация — мера чувствительности цены облигации к изменению ставки. Дюрация 5 лет означает: при росте ставки на 1% цена упадёт примерно на 5%. Чем выше — тем больше риск.",
        "en": "Duration — measure of bond price sensitivity to rate changes. Duration of 5 years means: if rates rise by 1%, price falls approximately 5%. Higher = more risk.",
    },
    "Convexity": {
        "ru": "Конвексити — мера кривизны связи цены и доходности. Дополняет дюрацию для точного расчёта изменения цены при больших изменениях ставок. Положительная конвексити — хорошо для инвестора.",
        "en": "Convexity — measure of the curvature of the price-yield relationship. Complements duration for accurate price change calculation at large rate shifts. Positive convexity is good for investors.",
    },
    "Walk-Forward": {
        "ru": "Walk-Forward — метод бэктестинга: портфель переоптимизируется на расширяющемся окне, а проверяется на out-of-sample данных. Имитирует реальный процесс принятия решений.",
        "en": "Walk-Forward — backtesting method: portfolio is re-optimized on expanding window, tested on out-of-sample data. Simulates real decision-making process.",
    },
}


def get_glossary_entry(term: str, lang: str = "en") -> str | None:
    """Получить описание термина из глоссария.

    Args:
        term: Термин для поиска.
        lang: Язык ('ru' или 'en').

    Returns:
        Описание термина или None, если термин не найден.
    """
    entry = _GLOSSARY.get(term)
    if entry is None:
        return None
    return entry.get(lang, entry.get("en"))


def get_all_terms(lang: str = "en") -> dict[str, str]:
    """Получить все термины из глоссария.

    Args:
        lang: Язык ('ru' или 'en').

    Returns:
        Словарь {термин: описание}.
    """
    return {term: entry.get(lang, entry.get("en", "")) for term, entry in _GLOSSARY.items()}
