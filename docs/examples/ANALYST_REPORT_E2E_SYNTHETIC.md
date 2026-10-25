# Пример пользовательского отчёта (синтетика E2E)

> Источник чисел: `docs/examples/analyst_bundle_e2e_synthetic.json`  
> (прогон `scripts/run_e2e_analyst_scenario.py`).  
> **Не является инвестиционной рекомендацией.** Данные полностью синтетические.

## 1. Исходный тестовый портфель

| Тикер | Текущий вес | Примечание |
|---|---|---|
| AAA | 0.38 | два счёта (`broker_a` + `broker_b`), консолидация SECID |
| BBB | 0.25 | один счёт |
| CCC | 0.37 | один счёт |

`as_of`: 2026-10-10. Сумма весов = 1.0 (канон CLI ±1e-6).

## 2. Проверка качества данных

- Источник панели: `fixture` (`synthetic_prices.csv`).
- `is_live_market: false` — календарная свежесть не блокирует fixture.
- ISS не вызывался (`MOEX_ISS_ENABLED=false`).

## 3. Целевые веса (Max Sharpe)

| Тикер | Target |
|---|---|
| AAA | 0.3333 |
| BBB | 0.3333 |
| CCC | 0.3333 |

`success: true`, режим `universe`, `max_weight: 0.5`.

## 4. Отклонения current vs target

- `allocation_kind`: rebalance  
- `needs_rebalance`: true (`max_abs_drift` ≈ 0.083 > `min_drift` 0.05)

| Тикер | Current | Target | Drift |
|---|---|---|---|
| AAA | 0.38 | 0.3333 | 0.0467 |
| BBB | 0.25 | 0.3333 | 0.0833 |
| CCC | 0.37 | 0.3333 | 0.0367 |

Порог 5% превышен по BBB.

## 5. Корпоративные события (тестовый режим CLI)

Записаны только в `processed/events_test/` (не в боевой каталог):

| event_id | Тип | Materiality | Источник |
|---|---|---|---|
| `TEST-EV-20261011-AAA-001` | dividend_recommendation | medium | synthetic-prime |
| `TEST-EV-20261011-BBB-001` | guidance_change | high | synthetic-prime |

Событие CCC (`press_release_marketing`, `materiality=ignore` / novelty=duplicate) пропущено семантикой ingest.

## 6. Качественные выводы (роль Аналитика)

- Количественный блок (веса, drift, QC) и оценки радара разделены.
- По BBB одновременно наибольший drift к target и событие `guidance_change` с materiality **high** — зона внимания при интерпретации.
- Оценки радара **не** переводились в ожидаемую доходность и **не** меняли solver.

## 7. Ограничения и неопределённость

- Тикеры AAA/BBB/CCC и цены — синтетика; результат нельзя переносить на реальный портфель.
- Live MOEX ISS и брокерские операции не использовались.
- `optimizer.yaml` у Аналитика не включался (`enabled: false`).
- Автозапуски / cron не настраивались.

## 8. Идентификаторы и артефакты

- Bundle schema: `moex_analyst_bundle.v1`
- Пример JSON: `docs/examples/analyst_bundle_e2e_synthetic.json`
- Запуск сценария: `python scripts/run_e2e_analyst_scenario.py`
- Контракт: `docs/ANALYST_BUNDLE_CONTRACT.md`
