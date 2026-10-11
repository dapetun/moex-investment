# Контракт: пакет артефактов CLI → Аналитик портфеля

Schema: `moex_analyst_bundle.v1`

## Назначение

Одноразовый (или явный) handoff вычислительных результатов CLI Аналитику.
Аналитик **не** пересчитывает веса и **не** подменяет solver.

## Как собрать

```bash
python -m moex_portfolio build-analyst-bundle \
  --target data/outbox/last_target.json \
  --compare-json /path/compare.json \
  --validation-json /path/validation.json \
  --ingest-json /path/ingest.json \
  --run-ids <opt_run>,<cmp_run> \
  --test-events \
  --out-dir /tmp/bundle
```

Сквозной сценарий (изолированный tmp):

```bash
MOEX_ISS_ENABLED=false MOEX_DATA_SOURCE=fixture \
  python scripts/run_e2e_analyst_scenario.py
```

## Поля bundle

| Поле | Смысл |
|---|---|
| `schema` | `moex_analyst_bundle.v1` |
| `synthetic` | `true` для тестовых прогонов |
| `disclaimer` | запрет выдавать синтетику за инвестрекомендацию |
| `holdings` | текущий портфель + path |
| `validation` | результат QC |
| `target.payload` | `last_target` (только при `success: true`) |
| `compare` | drift / needs_rebalance |
| `events.items[]` | `event_id`, ticker, type, source, url, `factual_summary`, `materiality`, `equity_assessment`/`bond_assessment` (direction, confidence, rationale) — качественный блок радара, не вход solver |
| `runs[]` | journal run_id + path |
| `analyst_instructions` | правила интерпретации |

## Правила для Аналитика (one-shot)

1. Числа CLI и оценки радара — разные блоки.
2. Ссылки на `event_id`, `run_id`, пути.
3. Не выдумывать доходности/цены/сделки.
4. Явно писать про синтетику и ограничения.
