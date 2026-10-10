# Контракт CLI: moex-investment ↔ Grok Bot

Ветка приёмки: `feature/headless-cli-grok-bot`. ISS выключен (`MOEX_ISS_ENABLED=false`).

## Команды

| Команда | Назначение | Успех | Типичные ошибки |
|---|---|---|---|
| `show-portfolio` | holdings JSON + `file_status` | 0 | 1/3 |
| `adapt-portfolio --csv` | CSV аналитика → holdings (read-only) | 0 | 2 adapter/validation |
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
data/portfolio/holdings.json                # канон CLI (см. PORTFOLIO_CONTRACT.md)
data/portfolio/PORTFOLIO_CONTRACT.md
data/fixtures/synthetic_prices.csv
data/inbox/events/*.json                    # копии для ingest (--source)
data/processed/events/*.json
data/processed/events_history/*.json        # предыдущие версии при updated
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
- `file_status=missing` ≠ пустой файл (`empty`); оба дают `positions: []` для весов.

## Портфель

См. `data/portfolio/PORTFOLIO_CONTRACT.md`. Адаптер CSV → holdings не пишет в
`/workspace/invest`. `--write-holdings` пишет только `data/portfolio/holdings.json`.

## События радара

См. `data/inbox/events/RADAR_CONTRACT.md` (refs: `cur-20261010-1713`, `1820`, `1936`).
Фикстуры: `tests/fixtures/radar_events_latest_v1_1_pilot.json` (синтетическая форма
пилота, не байт-копия боевого выпуска; `event_id` = `TEST-EV-…`, `is_test: true`),
`tests/fixtures/radar_batch_sample.json` (legacy batch).

- Канон выпуска: `/workspace/invest/news/events_latest.json` (schema 1.1).
- Мост: `ingest-events --source <path>` (оригинал не удаляется; inbox → archive).
- Типы: union equity_rules + bond_rules.start (39) + `unknown` (RESULT 1936);
  не маппить в выдуманные `disclosure_*`.
- `published_at: "unknown"` → reject (`PUBLISHED_AT_INVALID`).
- Оценки: `equity_assessment` / `bond_assessment` сохраняются; повторная оценка
  при том же `event_id` и жёсткой согласованности → `updated` (+ history);
  hard mismatch → `EVENT_IDENTITY_MISMATCH`; старый batch → `stale_skipped`.
- `partial=true` и exit **2**, если есть reject/conflict; JSON тогда в **stderr**;
  смотреть `details[]` (`event_id`, `changed_fields` для updates).

## Ограничения

- Нет live MOEX ISS, брокера, cron, реальных holdings.
- Фикстура ≠ рыночные котировки (staleness для fixture не блокирует).
- Для market/iss применяется `MIN_TURNOVER` как в Streamlit; для fixture — 0.
