# MOEX Portfolio Optimizer

Автоматизированный инструмент для подбора оптимального инвестиционного портфеля акций Московской биржи. Загружает данные, фильтрует акции, находит группу с минимальными корреляциями и рассчитывает оптимальные веса через несколько финансовых моделей.

---

## Что делает этот проект?

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

---

## Установка

### Требования
- Python 3.10 или выше

### Шаг 1: Клонируем репозиторий

```bash
git clone https://github.com/dapetun/moex-investment.git
cd moex-investment
```

### Шаг 2: Устанавливаем зависимости

```bash
pip install -e ".[dashboard,dev]"
```

### Шаг 3: Запускаем дашборд

```bash
streamlit run app.py
```

Откроется браузер с интерактивным интерфейсом.

---

## Как пользоваться дашбордом

### Боковая панель (слева)

Здесь вы настраиваете параметры:

| Параметр | Что означает | Значение по умолчанию |
|----------|-------------|----------------------|
| **Correlation threshold** | Порог корреляции: если |корреляция| между двумя акциями ниже этого числа, они считаются «независимыми». **Чем ниже** — тем строже отбор. | 0.25 |
| **Min daily turnover** | Минимальный средний дневной оборот акции в млн руб. Акции с маленьким оборотом неликвидны. | 50 млн |
| **Max weight per asset** | Максимальная доля одной акции в портфеле. | 30% |
| **Risk-free rate** | Безрисковая ставка (годовая). Используется для Sharpe ratio. | 16% (КС ЦБ) |
| **Covariance method** | Как считать ковариационную матрицу. | ledoit_wolf |
| **Monte Carlo simulations** | Сколько случайных сценариев смоделировать. | 10 000 |
| **Rebalance frequency** | Как часто ребалансировать портфель (в торговых днях). | 21 |
| **Transaction cost** | Транзакционные издержки в базисных пунктах. 10 bps = 0.1%. | 10 |
| **Black-Litterman tau** | Параметр неопределённости в модели BL. | 0.05 |
| **BL: auto-views count** | Сколько автоматических views создавать. | 5 |
| **HRP clustering** | Метод кластеризации для HRP. | single |
| **Use cached data** | Использовать скачанные ранее данные. | Да |

### Нажимаете «Run Optimization»

Начинается полный пайплайн. Обычно занимает 30-60 секунд (если данные уже кэшированы — 2-3 секунды).

---

## 20 вкладок с результатами

| # | Вкладка | Описание |
|---|---------|----------|
| 1 | Portfolio | Оптимальный портфель с максимальным Sharpe ratio, веса, метрики, кривая капитала |
| 2 | Efficient Frontier | График «оптимальных» портфелей — от минимально рискового до максимально доходного |
| 3 | Monte Carlo | 10 000 случайных сценариев на год вперёд, гистограммы, процентили |
| 4 | Graph Analysis | Визуализация графа корреляций: полный граф, клика, тепловая карта |
| 5 | Detailed Analysis | Бар-чарт доходностей, таблица статистики по каждой акции |
| 6 | Rebalancing | Сравнение Rebalancing vs Buy & Hold с учётом транзакционных издержек |
| 7 | Stress Test | 5 исторических кризисов: COVID, 2022, 2018, 2014, 2008 |
| 8 | Black-Litterman | Комбинирование рыночного равновесия с вашими views |
| 9 | HRP | Иерархический риск-паритет (Lopez de Prado, 2016) |
| 10 | Rolling Correlation | Как корреляции и бета меняются со временем |
| 11 | Dividends | Dogs of the Dow, Dividend Aristocrats, High Dividend Yield |
| 12 | Fundamental | P/E, P/B, ROE, ранжирование по составному скору |
| 13 | Bonds | Кривая доходности ОФЗ, интерполяция, анализ термической структуры |
| 14 | Merton Model | Структурная модель кредитного риска: DD, PD, credit spread |
| 15 | Backtesting | Walk-forward бэктестинг vs Buy & Hold |
| 16 | Risk Budget | Вклад каждой акции в общий риск. Equal Risk Contribution |
| 17 | Drawdowns | Анализ всех просадок, underwater-чарт, худшие периоды |
| 18 | Multi-Asset | Мульти-активная оптимизация: акции + ОФЗ в одном портфеле |
| 19 | Benchmark | Сравнение с IMOEX/RGBI: tracking error, alpha, information ratio |
| 20 | ML Forecast | Walk-Forward, инкрементальное дообучение (SGD/PA), сравнение моделей |

---

## Экспорт результатов

- **Excel** (10 листов): Max Sharpe Portfolio, Min Variance, Summary, Monte Carlo, Parameters, Returns, Rebalancing, Stress Test, Black-Litterman, HRP
- **PDF** (5 страниц): Сводка с метриками, веса портфеля, гистограммы MC, сравнение стратегий, стресс-тесты
- **Профили**: JSON-файлы в `data/profiles/`

---

## Методы ковариации

| Метод | Описание | Когда использовать |
|-------|----------|-------------------|
| **sample** | Обычная ковариационная матрица | Для больших выборок |
| **ledoit_wolf** | Сжатие Ledoit-Wolf | Когда число активов сравнимо с числом наблюдений |
| **ewma** | Экспоненциально взвешенная | Для нестационарных данных |

---

## Модули проекта

```
src/moex_portfolio/
├── config.py              — Константы: пути, фильтры, API, оптимизация
├── defaults.py            — Theory-based дефолты (Defaults frozen dataclass)
├── data_loader.py         — Загрузка данных с MOEX ISS API (синхронная/асинхронная, кэш)
├── filters.py             — Фильтрация: ликвидность, аномалии, волатильность
├── correlation.py         — Матрица корреляций, тепловая карта
├── graph_analysis.py      — Граф корреляций, максимальная клика
├── metrics.py             — Sharpe, Sortino, Calmar, Treynor, Modigliani, Information Ratio
├── optimizer.py           — Markowitz Mean-Variance, Efficient Frontier
├── risk_models.py         — Ledoit-Wolf, EWMA, Beta, Alpha (Jensen's)
├── analytics.py           — Monte Carlo, Equity Curve, VaR, CVaR, Rolling
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
├── yield_curve.py         — Кривая доходности ОФЗ
├── merton.py              — Структурная модель Мертона
├── benchmark.py           — Сравнение с индексами (IMOEX, RGBI)
├── fundamental.py         — Фундаментальный анализ
├── dividend_strategies.py — Dogs of the Dow, Dividend Aristocrats
├── ml_models.py           — ML: Ridge/Lasso/RF/GBR/SGD/PA, Walk-Forward, AutoML, incremental
├── exporter.py            — Экспорт в Excel и PDF
├── profiles.py            — Сохранение/загрузка профилей (JSON)
├── i18n.py                — Интернационализация (RU/EN, 328 ключей)
└── glossary.py            — Глоссарий финансовых терминов (30+)
```

---

## Тесты

```bash
# Запуск всех тестов
python -m pytest tests/ -v

# Запуск конкретного файла
python -m pytest tests/test_optimizer.py -v

# Покрытие
python -m pytest tests/ --cov=moex_portfolio --cov-report=term-missing
```

**201 тест**, покрывающих все основные модули проекта.

---

## Известные проблемы и план исправлений

Проект был подвергнут комплексному аудиту. Ниже — список выявленных проблем и план их устранения.

### Критические проблемы (Этап 1)

| # | Проблема | Файл | Статус |
|---|----------|------|--------|
| 1 | `app.py` — монолитный файл (1321 строка), нарушение SRP | `app.py` | Будет разделён |
| 2 | `sys.path.insert()` — хрупкий путь импорта | `app.py` | Заменён на `pip install -e .` |
| 3 | `TODAY = date.today()` вычисляется при import time | `config.py` | Будет исправлено |
| 4 | Division by zero в Black-Litterman при сингулярных данных | `black_litterman.py` | Будет исправлено |
| 5 | Голые `except` блокируют ошибки | `data_loader.py`, `ml_models.py` | Будут заменены |
| 6 | `time.sleep()` блокирует UI | `app.py` | Заменено на async patterns |
| 7 | Отсутствует rate limiting для API | `data_loader.py` | Будет добавлен |

### Проблемы качества (Этап 2)

| # | Проблема | Файл |
|---|----------|------|
| 8 | Отсутствие type hints в ~60% функций | Все модули |
| 9 | Нет валидации API ответов | `data_loader.py` |
| 10 | `ml_models.py` — 901 строка, нужен разделение | `ml_models.py` |
| 11 | Нет кэширования ML моделей | `ml_models.py` |
| 12 | Pickle для моделей (риск RCE) | `ml_models.py` |
| 13 | XSS через `unsafe_allow_html` | `app.py` |
| 14 | Отсутствует Dependency Injection | `config.py` |
| 15 | Coverage threshold — 60% | `pyproject.toml` |
| 16 | Нет structured logging | Все модули |
| 17 | Дублирование `requirements.txt` / `pyproject.toml` | Корень проекта |
| 18 | Нет CI coverage/security reporting | `.github/workflows/ci.yml` |

### Проблемы производительности (Этап 3)

| # | Проблема | Файл |
|---|----------|------|
| 19 | Избыточные копирования DataFrame | Несколько модулей |
| 20 | Нет lazy loading для данных | `data_loader.py` |
| 21 | Нет batch loading для API | `data_loader.py` |
| 22 | Matplotlib figure не закрывается | `visualization.py` |
| 23 | Отсутствует параллелизм в загрузке | `data_loader.py` |

---

## Дорожная карта

### Этап 1 — Критические исправления
Исправление проблем, мешающих корректной и безопасной работе.

### Этап 2 — Улучшение качества
Type safety, dependency injection, структурирование кода, покрытие тестами.

### Этап 3 — Оптимизация
Производительность, кэширование, structured logging, Docker.

### Этап 4 — Новые возможности
REST API, real-time tracking, алерты, mobile UI.

### Этап 5 — Долгосрочное развитие
Tax optimization, Kubernetes, GraphQL, enterprise-ready.

---

## Лицензия

MIT
