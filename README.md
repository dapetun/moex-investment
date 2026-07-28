# MOEX Portfolio Optimizer

Автоматизированный подбор оптимального инвестиционного портфеля акций Московской биржи.

## Возможности

- Загрузка данных через MOEX ISS API с кэшированием
- Фильтрация по ликвидности и статистическим критериям
- Построение графа корреляций и поиск максимальной клики
- Markowitz Mean-Variance оптимизация
- Efficient Frontier
- Расчёт Sharpe ratio, Sortino ratio, максимальной просадки
- Интерактивный Streamlit-дашборд

## Установка

```bash
git clone https://github.com/dapetun/moex-investment.git
cd moex-investment
pip install -e .
```

Для дашборда:
```bash
pip install -e ".[dashboard]"
streamlit run app.py
```

## Быстрый старт

```python
from moex_portfolio.data_loader import load_all_data, get_all_shares
from moex_portfolio.filters import prepare_returns
from moex_portfolio.graph_analysis import build_correlation_graph, find_max_clique
from moex_portfolio.optimizer import max_sharpe_portfolio

# Загрузка данных
tickers = get_all_shares()
data = load_all_data(tickers)

# Фильтрация
returns, valid_tickers = prepare_returns(data)

# Графовый анализ
corr = returns.corr()
G = build_correlation_graph(corr)
clique = find_max_clique(G)

# Оптимизация
result = max_sharpe_portfolio(
    returns[clique].mean(),
    returns[clique].cov()
)
print(result)
```

## Структура проекта

```
src/moex_portfolio/
├── config.py           # Параметры и конфигурация
├── data_loader.py      # Загрузка данных с MOEX ISS API
├── filters.py          # Фильтрация по ликвидности и аномалиям
├── correlation.py      # Корреляционный анализ
├── graph_analysis.py   # Граф корреляций, максимальная клика
├── metrics.py          # Финансовые метрики (Sharpe, Sortino, drawdown)
├── optimizer.py        # Markowitz оптимизация, efficient frontier
└── visualization.py    # Визуализация
```

## Лицензия

MIT
