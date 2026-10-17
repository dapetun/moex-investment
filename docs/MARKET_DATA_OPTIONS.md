# Источники рыночных данных для CLI

Ограничение проекта: **MOEX ISS выключен** (`MOEX_ISS_ENABLED=false`), live-fetch не подключён даже при флаге true до отдельного правового решения.

## Требования оптимизатора к панели

Формат: CSV с разделителем `;`, индекс `TRADEDATE`, столбцы `TICKER` и опционально `TICKER_VALUE` (оборот).

| Параметр | Минимум |
|---|---|
| Частота | дневные close |
| История | ≥20 торговых дней (QC); для устойчивой cov желательно ≥60–126 |
| Покрытие | тикеры портфеля ⊆ столбцы панели |
| Свежесть | для `market` / `user_csv`: ≤ `max_staleness_days` (по умолчанию 5), если не аттестована историчность |
| QC | `validate-data` / `validate_for_optimize` |

## Сравнение вариантов

| Источник | Доступность | Лицензия / риски | Полнота RU акции/облигации | Стоимость | Сложность | Статус в CLI |
|---|---|---|---|---|---|---|
| Синтетическая fixture | всегда | N/A (тест) | только AAA/BBB/CCC | 0 | 0 | **работает** (`fixture`) |
| Пользовательский CSV | ручной экспорт | ответственность пользователя | зависит от экспорта | 0 | низкая | **реализован** (`user_csv` + `import-user-prices`) |
| Runtime cache (`market`) | после import/update | не сеть | как загружено | 0 | низкая | есть; без approved upstream |
| MOEX ISS напрямую | сеть | требуется письменное разрешение биржи | высокая | 0 API, но legal gate | средняя | **заблокирован** |
| Зеркала / неофициальные агрегаторы ISS | сеть | правовая неопределённость, ToS | переменная | ? | средняя | **запрещены** как обход |
| Платные терминалы (экспорт CSV) | подписка | по договору поставщика | обычно высокая | высокая | низкая (ручной CSV) | через `user_csv` |
| Брокерский API | OAuth/ключи | договор брокера | зависит от брокера | по тарифу | высокая | **не подключено** |

## Рекомендация на сейчас

1. **Краткий путь:** экспорт дневных close из вашего разрешённого терминала/брокера → `import-user-prices` → `MOEX_DATA_SOURCE=user_csv`.
2. **Не использовать** ISS и зеркала до явного решения.
3. Синтетика (`fixture`) только для тестов/e2e; не выдавать за рынок.

## Режим `user_csv`

```bash
# проверка и копирование в data/cache/runtime_prices.csv
python -m moex_portfolio import-user-prices --csv /path/to/prices.csv [--skip-staleness]

export MOEX_ISS_ENABLED=false
export MOEX_DATA_SOURCE=user_csv
export MOEX_USER_PRICES_PATH=/path/to/data/cache/runtime_prices.csv
# для заведомо исторической панели:
# export MOEX_USER_CSV_SKIP_STALENESS=true

python -m moex_portfolio validate-data
python -m moex_portfolio optimize --allow-optimize --mode holdings
```

Запреты:

- Нельзя указать tracked `synthetic_prices.csv` как `user_csv` (`USER_CSV_FIXTURE_REFUSED`).
- Нельзя вызвать ISS через этот путь.
- Импорт не помечает данные как «биржевые» автоматически: в bundle нужен явный `--real-data` только если вы подтверждаете происхождение.
