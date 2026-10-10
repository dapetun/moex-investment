# Контракт CLI: moex-investment ↔ Grok Bot

Ветка приёмки: `feature/headless-cli-grok-bot`. ISS выключен (`MOEX_ISS_ENABLED=false`).

## Команды

| Команда | Назначение | Успех | Типичные ошибки |
|---|---|---|---|
| `show-portfolio` | holdings JSON (пустой OK) | 0 | 1/3 |
| `validate-data` | QC активной панели | 0 | 2 QC fail, 4 source blocked |
| `update-data` | fixture → runtime cache | 0 | 4 ISS/market blocked |
| `optimize --allow-optimize` | Max Sharpe + QC | 0 | 2 QC/solver/params, 4 source |
| `compare` | current vs last_target | 0 | 2 invalid holdings/target |
| `ingest-events [--source PATH]` | радар/inbox → processed | 0 | 2 если `rejected>0` (partial) |
| `report --run-id` | MD/JSON по journal | 0 | 1 missing run |

Коды: `0` ok, `1` unexpected/missing run, `2` бизнес/валидация (в т.ч. partial ingest),
`3` lock, `4` источник заблокирован.

## Файлы

```
/workspace/invest/news/events_latest.json   # канон радара (вне репо)
data/portfolio/holdings.json
data/fixtures/synthetic_prices.csv
data/inbox/events/*.json                    # копии для ingest (--source)
data/processed/events/*.json
data/processed/rejected/*.json
data/processed/inbox_archive/*.json         # сохранённые исходники inbox
data/processed/batches/*.json               # мета обёртки выпуска
data/outbox/last_target.json                # только success=true
data/outbox/runs/{run_id}.json
data/outbox/reports/{run_id}.{json,md}
data/locks/pipeline.lock
```

## Правила результата оптимизатора

- QC обязателен до solver.
- Target пишется атомарно только при `success is True`.
- Отсутствующий флаг `success` = неуспех.
- Веса: конечные, ≥0, ≤ max_weight, сумма ≈ 1.
- При ошибке предыдущий target не трогается; отчёт и journal создаются.

## Compare

- Target без `success: true` отклоняется.
- Пустой current + непустой target → `allocation_kind=initial_allocation`
  (`needs_rebalance=false`, `needs_action` по drift).
- Holdings: явные `weight`; shares-only → `HOLDINGS_SHARES_WITHOUT_WEIGHTS`.

## События радара

См. `data/inbox/events/RADAR_CONTRACT.md`.
Фикстуры: `tests/fixtures/radar_events_latest_v1_1_pilot.json` (форма пилота),
`tests/fixtures/radar_batch_sample.json` (legacy batch).

- Канон выпуска: `/workspace/invest/news/events_latest.json` (schema 1.1).
- Мост: `ingest-events --source <path>` (оригинал не удаляется; inbox → archive).
- Типы: allowlist радара (24 + `put_offer_announced`/`unknown`); не маппить в выдуманные `disclosure_*`.
- Оценки: `equity_assessment` / `bond_assessment` сохраняются.
- `partial=true` и exit **2**, если есть reject/conflict; смотреть `details[]` (`event_id`).

## Ограничения

- Нет live MOEX ISS, брокера, cron, реальных holdings.
- Фикстура ≠ рыночные котировки (staleness для fixture не блокирует).
- Для market/iss применяется `MIN_TURNOVER` как в Streamlit; для fixture — 0.
