# MOEX Portfolio Optimizer

> 🇬🇧 [English](#english) | 🇷🇺 [Русский](#русский)

---

<a id="english"></a>
## 🇬🇧 English

Automated tool for constructing an optimal investment portfolio from Moscow Exchange (MOEX) stocks. Loads data, filters stocks, finds groups with minimum correlations, and calculates optimal weights using multiple financial models.

### What does this project do?

You click one button — and the system:

1. Loads a list of **all MOEX stocks** via the official API
2. Downloads **2 years of price history** for each stock
3. **Filters** — removes illiquid, anomalous, and "dead" stocks
4. Builds a **correlation graph** — finds stocks that move independently
5. Finds the **maximum clique** — a group where **every pair** is weakly correlated
6. Calculates **optimal weights** using 5 methods (Markowitz, Min Variance, Black-Litterman, HRP, Multi-Asset)
7. Shows **all risk metrics** — VaR, CVaR, drawdowns, Monte Carlo, stress tests
8. **ML forecasting** of returns with incremental online learning
9. **Exports** results to Excel (10 sheets) and PDF (5 pages)

### Quick Start

```bash
git clone https://github.com/dapetun/moex-investment.git
cd moex-investment
pip install -e ".[dashboard,dev]"
streamlit run app.py
```

Dashboard opens at `http://localhost:8501`.

### Dashboard Tabs (20)

| # | Tab | Description |
|---|-----|-------------|
| 1 | Portfolio | Max Sharpe portfolio, weights, metrics, equity curve |
| 2 | Efficient Frontier | Optimal portfolios from min-risk to max-return |
| 3 | Monte Carlo | 10,000 random scenarios for 1 year ahead |
| 4 | Graph Analysis | Correlation graph, clique, heatmap |
| 5 | Detailed Analysis | Return bar charts, per-stock statistics |
| 6 | Rebalancing | Rebalancing vs Buy & Hold with transaction costs |
| 7 | Stress Test | 5 historical crises: COVID, 2022, 2018, 2014, 2008 |
| 8 | Black-Litterman | Combining market equilibrium with your views |
| 9 | HRP | Hierarchical Risk Parity (Lopez de Prado, 2016) |
| 10 | Rolling Correlation | How correlations and beta change over time |
| 11 | Dividends | Dogs of the Dow, Dividend Aristocrats, High Yield |
| 12 | Fundamental | P/E, P/B, ROE, composite scoring |
| 13 | Bonds | OFZ yield curve, interpolation, term structure |
| 14 | Merton Model | Structural credit risk: DD, PD, credit spread |
| 15 | Backtesting | Walk-forward vs Buy & Hold |
| 16 | Risk Budget | Per-stock risk contribution, Equal Risk Contribution |
| 17 | Drawdowns | Drawdown analysis, underwater chart, worst periods |
| 18 | Multi-Asset | Stocks + OFZ in one portfolio |
| 19 | Benchmark | IMOEX/RGBI comparison: tracking error, alpha |
| 20 | ML Forecast | Walk-Forward, incremental SGD/PA, model comparison |

### Modules

```
src/moex_portfolio/
├── config.py              — Constants: paths, filters, API, optimization
├── defaults.py            — Theory-based defaults (frozen dataclass)
├── data_loader.py         — MOEX ISS data loading (sync/async, CSV cache)
├── filters.py             — Liquidity, anomaly, volatility filtering
├── correlation.py         — Correlation matrix, heatmap
├── graph_analysis.py      — Correlation graph, maximum clique
├── metrics.py             — Sharpe, Sortino, Calmar, Treynor, M2, IR
├── optimizer.py           — Markowitz Mean-Variance, Efficient Frontier
├── risk_models.py         — Ledoit-Wolf, EWMA, Beta, Alpha
├── analytics.py           — Monte Carlo, Equity Curve, VaR, CVaR
├── charts.py              — Interactive Plotly charts
├── visualization.py       — Static matplotlib/seaborn charts
├── black_litterman.py     — Black-Litterman model
├── hrp.py                 — Hierarchical Risk Parity
├── multi_asset.py         — Multi-asset optimization (stocks + bonds)
├── rebalancing.py         — Rebalancing simulation with costs
├── stress_test.py         — Historical crisis stress testing
├── backtesting.py         — Walk-forward backtesting
├── risk_budget.py         — Risk budgeting, Equal Risk Contribution
├── drawdown_analysis.py   — Drawdown period analysis
├── bonds.py               — YTM, Duration, Convexity
├── bonds_loader.py        — OFZ/Corporate bond data loader
├── yield_curve.py         — OFZ yield curve, cubic spline
├── merton.py              — Merton structural credit model
├── benchmark.py           — Index comparison (IMOEX, RGBI)
├── fundamental.py         — Fundamental analysis, composite scoring
├── dividend_strategies.py — Dogs of the Dow, Aristocrats
├── ml_models.py           — Ridge/Lasso/RF/GBR/SGD/PA, Walk-Forward, AutoML
├── exporter.py            — Excel and PDF export
├── profiles.py            — Portfolio save/load (JSON)
├── i18n.py                — Internationalization (RU/EN, 328 keys)
└── glossary.py            — Financial glossary (30+ terms)
```

### Testing

```bash
python -m pytest tests/ -v                                          # All tests
python -m pytest tests/ --cov=moex_portfolio --cov-report=term-missing  # Coverage
ruff check src/ tests/                                              # Lint
```

**201 tests** covering all major modules. CI runs on Python 3.11/3.12/3.13.

### Export

- **Excel** (10 sheets): Max Sharpe, Min Variance, Summary, Monte Carlo, Parameters, Returns, Rebalancing, Stress Test, Black-Litterman, HRP
- **PDF** (5 pages): Summary with metrics, portfolio weights, MC histograms, strategy comparison, stress tests
- **Profiles**: JSON files in `data/profiles/`

### CI/CD

- Tests: Python 3.11/3.12/3.13, coverage >= 65%
- Security: bandit scanning
- Pre-commit: ruff lint/format, trailing whitespace, EOF, YAML

---

<a id="русский"></a>
## 🇷🇺 Русский

Автоматизированный инструмент для подбора оптимального инвестиционного портфеля акций Московской биржи. Загружает данные, фильтрует акции, находит группу с минимальными корреляциями и рассчитывает оптимальные веса через несколько финансовых моделей.

### Что делает этот проект?

Вы запускаете одно нажатие кнопки — и система сама:

1. Загружает список **всех акций MOEX** через официальный API
2. Скачивает **2 года истории цен** для каждой акции
3. **Фильтрует** — убирает неликвидные, аномальные, «мёртвые» акции
4. Строит **граф корреляций** — находит акции, которые движутся независимо друг от друга
5. Находит **максимальную клику** — группу акций, где **каждая пара** слабо коррелирована
6. Рассчитывает **оптимальные веса** пятью методами (Markowitz, Min Variance, Black-Litterman, HRP, Multi-Asset)
7. Показывает **все метрики риска** — VaR, CVaR, просадки, Monte Carlo, стресс-тесты
8. **ML-прогнозирование** доходности с инкрементальным дообучением
9. Позволяет **экспортировать** результат в Excel (10 листов) и PDF (5 страниц)

### Быстрый старт

```bash
git clone https://github.com/dapetun/moex-investment.git
cd moex-investment
pip install -e ".[dashboard,dev]"
streamlit run app.py
```

Дашборд откроется на `http://localhost:8501`.

### Боковая панель (слева)

| Параметр | Описание | По умолчанию |
|----------|----------|--------------|
| **Correlation threshold** | Порог корреляции: чем ниже — тем строже отбор | 0.25 |
| **Min daily turnover** | Минимальный средний дневной оборот в млн руб. | 50 млн |
| **Max weight per asset** | Максимальная доля одной акции в портфеле | 30% |
| **Risk-free rate** | Безрисковая ставка (годовая). Авто: ЦБ/OFZ | 16% |
| **Covariance method** | Метод ковариационной матрицы | ledoit_wolf |
| **Monte Carlo simulations** | Количество случайных сценариев | 10 000 |
| **Rebalance frequency** | Частота ребалансировки (в торговых днях) | 21 |
| **Transaction cost** | Транзакционные издержки (bps) | 10 |
| **Black-Litterman tau** | Параметр неопределённости BL | 0.05 |
| **BL: auto-views count** | Количество автоматических views | 5 |
| **HRP clustering** | Метод кластеризации для HRP | single |
| **Use cached data** | Использовать кэшированные данные | Да |

### 20 вкладок с результатами

| # | Вкладка | Описание |
|---|---------|----------|
| 1 | Portfolio | Оптимальный портфель, веса, метрики, кривая капитала |
| 2 | Efficient Frontier | От минимально рискового до максимально доходного |
| 3 | Monte Carlo | 10 000 случайных сценариев на год вперёд |
| 4 | Graph Analysis | Визуализация графа корреляций, клика, тепловая карта |
| 5 | Detailed Analysis | Бар-чарт доходностей, таблица статистики |
| 6 | Rebalancing | Rebalancing vs Buy & Hold с издержками |
| 7 | Stress Test | 5 исторических кризисов: COVID, 2022, 2018, 2014, 2008 |
| 8 | Black-Litterman | Комбинирование рыночного равновесия с вашими views |
| 9 | HRP | Иерархический риск-паритет (Lopez de Prado, 2016) |
| 10 | Rolling Correlation | Как корреляции и бета меняются со временем |
| 11 | Dividends | Dogs of the Dow, Aristocrats, High Dividend Yield |
| 12 | Fundamental | P/E, P/B, ROE, ранжирование по составному скору |
| 13 | Bonds | Кривая доходности ОФЗ, интерполяция, термическая структура |
| 14 | Merton Model | Структурная модель кредитного риска: DD, PD, credit spread |
| 15 | Backtesting | Walk-forward бэктестинг vs Buy & Hold |
| 16 | Risk Budget | Вклад каждой акции в общий риск. ERC |
| 17 | Drawdowns | Анализ всех просадок, underwater-чарт, худшие периоды |
| 18 | Multi-Asset | Мульти-активная оптимизация: акции + ОФЗ |
| 19 | Benchmark | Сравнение с IMOEX/RGBI: tracking error, alpha |
| 20 | ML Forecast | Walk-Forward, инкрементальное дообучение, сравнение моделей |

### Модули проекта

```
src/moex_portfolio/
├── config.py              — Константы: пути, фильтры, API, оптимизация
├── defaults.py            — Theory-based дефолты (frozen dataclass)
├── data_loader.py         — Загрузка данных MOEX ISS (sync/async, кэш)
├── filters.py             — Фильтрация: ликвидность, аномалии, волатильность
├── correlation.py         — Матрица корреляций, тепловая карта
├── graph_analysis.py      — Граф корреляций, максимальная клика
├── metrics.py             — Sharpe, Sortino, Calmar, Treynor, M2, IR
├── optimizer.py           — Markowitz Mean-Variance, эффективная граница
├── risk_models.py         — Ledoit-Wolf, EWMA, Beta, Alpha (Jensen's)
├── analytics.py           — Monte Carlo, Equity Curve, VaR, CVaR
├── charts.py              — Интерактивные графики Plotly
├── visualization.py       — Статические графики matplotlib/seaborn
├── black_litterman.py     — Модель Black-Litterman
├── hrp.py                 — Hierarchical Risk Parity
├── multi_asset.py         — Мульти-активная оптимизация (акции + облигации)
├── rebalancing.py         — Симуляция ребалансирования с издержками
├── stress_test.py         — Стресс-тестирование на исторических кризисах
├── backtesting.py         — Walk-forward бэктестинг
├── risk_budget.py         — Риск-бюджет, Equal Risk Contribution
├── drawdown_analysis.py   — Анализ просадок
├── bonds.py               — YTM, Duration, Convexity облигаций
├── bonds_loader.py        — Загрузчик данных ОФЗ/Корпоблигаций
├── yield_curve.py         — Кривая доходности ОФЗ, кубический сплайн
├── merton.py              — Структурная модель Мертона
├── benchmark.py           — Сравнение с индексами (IMOEX, RGBI)
├── fundamental.py         — Фундаментальный анализ, составной скор
├── dividend_strategies.py — Dogs of the Dow, Aristocrats
├── ml_models.py           — Ridge/Lasso/RF/GBR/SGD/PA, Walk-Forward, AutoML
├── exporter.py            — Экспорт в Excel и PDF
├── profiles.py            — Сохранение/загрузка профилей (JSON)
├── i18n.py                — Интернационализация (RU/EN, 328 ключей)
└── glossary.py            — Глоссарий финансовых терминов (30+)
```

### Тесты

```bash
python -m pytest tests/ -v                                          # Все тесты
python -m pytest tests/ --cov=moex_portfolio --cov-report=term-missing  # Покрытие
ruff check src/ tests/                                              # Lint
```

**201 тест**, покрывающих все основные модули проекта. CI запускается на Python 3.11/3.12/3.13.

### Экспорт результатов

- **Excel** (10 листов): Max Sharpe, Min Variance, Summary, Monte Carlo, Parameters, Returns, Rebalancing, Stress Test, Black-Litterman, HRP
- **PDF** (5 страниц): Сводка с метриками, веса портфеля, гистограммы MC, сравнение стратегий, стресс-тесты
- **Профили**: JSON-файлы в `data/profiles/`

### CI/CD

- Тесты: Python 3.11/3.12/3.13, coverage >= 65%
- Безопасность: bandit
- Pre-commit: ruff lint/format, trailing whitespace, EOF, YAML

---

## Roadmap / Дорожная карта

### ✅ v0.1.0 — Initial Release
- Full pipeline: data loading → filtering → optimization → visualization → export
- 20-tab Streamlit dashboard, 201 tests, i18n RU/EN

### ✅ v0.1.1 — Stage 1 Critical Fixes
- `config.py`: `get_today()` — no more stale dates
- `black_litterman.py`: Ridge regularization for singular matrices
- `stress_test.py`: DatetimeIndex bugfix
- Bare except → specific exceptions (6 modules)
- CI: coverage 65%, bandit security, pre-commit hooks
- `risk_free_rate.py`: Auto risk-free rate (CBR/OFZ/manual)
- Removed `requirements.txt` (pyproject.toml is SSoT)

### 🔜 Stage 2 — Code Quality
- [ ] Decompose `app.py` (1334 lines) into modules
- [ ] Decompose `ml_models.py` (901 lines)
- [ ] Type hints + mypy strict
- [ ] Pydantic models for API responses
- [ ] ML model caching (joblib)
- [ ] Async rewrite for bonds_loader/fundamental

### 🔜 Stage 3 — Infrastructure
- [ ] Structured logging (structlog)
- [ ] Lazy data loading
- [ ] Dockerfile + docker-compose
- [ ] Custom exception types
- [ ] Rate limiting for API

### 🔜 Stage 4 — Features
- [ ] Rebalancing alerts
- [ ] Custom stress scenarios
- [ ] Portfolio comparison (side-by-side)
- [ ] Currency hedging (USD/RUB)
- [ ] Sector constraints UI
- [ ] Multi-period optimization

---

## License / Лицензия

MIT
