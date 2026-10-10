# Контракт: Корпоративный радар → CLI (подтверждён 2026-10-10)

Источник подтверждения: Grok Bot RESULT `cur-20261010-1715` /
`2026-10-10_radar-portfolio-contract` (схемы на облаке
`/workspace/invest/schemas/event.schema.json`,
`events_file.schema.json`).

## Канонические пути (облако)

| Роль | Путь |
|---|---|
| Выпуск радара | `/workspace/invest/news/events_latest.json` |
| История | `/workspace/invest/news/events_history.jsonl` |
| Уведомление аналитику | `/workspace/invest/handoff/radar_to_analyst/<YYYYMMDD_HHMM>.md` |
| Inbox CLI | `<repo>/data/inbox/events/*.json` |
| Архив исходников после ingest | `<repo>/data/processed/inbox_archive/` |

**Мост:** радар **не** пишет в `data/inbox/events/`. Передача:

```bash
python -m moex_portfolio ingest-events \
  --source /workspace/invest/news/events_latest.json
```

Оригинал `--source` не удаляется. Копия в inbox после обработки
переносится в `processed/inbox_archive/`.

## Обёртка файла (`schema_version` 1.0 | 1.1)

Обязательные: `schema_version`, `generated_at`, `coverage_from`, `coverage_to`,
`generated_by`, `is_test`, `sources_checked[]`, `events[]`. Опционально: `notes`.

Метаданные обёртки сохраняются в `processed/batches/` и в поле
`radar_batch` каждого принятого события.

## Поля события

| Поле радара | Канон CLI / поведение |
|---|---|
| `source_name` | → `source` |
| `source_url` / `document_url` | → `url` (document_url — запасной) |
| `factual_summary` | → `summary` и `title` (если нет title) |
| `issuer_name` | → `company` |
| `published_at` | дата публикации (ISO +03:00); **не** подменяется на `event_date` без метки |
| `event_date` | дата события (YYYY-MM-DD), сохраняется отдельно |
| `event_id` | `EV-<YYYYMMDD>-<TICKER>-<NNN>`; имя файла processed |
| `event_type` | строка из allowlist радара (см. ниже), **без** переписывания в `disclosure_*` |
| `equity_assessment` / `bond_assessment` | сохраняются целиком |
| `duplicate_of` / `novelty=duplicate` / `materiality=ignore` | skip (не reject), статус в `details` |
| полный объект | `radar_original` |

Поля `facts` у радара нет; факты — в `factual_summary` + блоки оценок.

## Allowlist `event_type` (radar `equity_rules` + `put_offer_announced`)

`default_or_technical_default`, `sanctions_or_regulatory_ban`,
`bankruptcy_or_license_revocation`, `delisting_or_listing_change`,
`dividend_recommendation`, `dividend_policy_change`,
`buyback_or_additional_issue`, `major_transaction_or_m_and_a`,
`credit_rating_change`, `financial_statements_ifrs`,
`financial_statements_ras`, `operating_results`, `guidance_change`,
`board_decision_other`, `shareholder_meeting`, `bond_offer_coupon_or_put`,
`operational_incident`, `project_launch`, `management_change_ceo_cfo`,
`management_change_routine`, `litigation_major`, `market_technical_notice`,
`press_release_marketing`, `noise_holiday_award_charity`,
`put_offer_announced`, `unknown`.

Legacy CLI: префиксы `disclosure_*` / `dividend_*` и короткие алиасы
(`material_fact`, `meeting`, …) — только для старых фикстур.

Неизвестный тип → `EVENT_TYPE_UNMAPPED` (reject), без выдуманных категорий.

## Коды `ingest-events`

| Ситуация | exit | поля отчёта |
|---|---|---|
| все события приняты / skip semantics / дубликаты | 0 | `partial=false` |
| есть хотя бы один reject/conflict | **2** | `partial=true`, `accepted`, `rejected`, `details[]` с `event_id` |

## Фикстуры

- Форма пилота (6 событий): `tests/fixtures/radar_events_latest_v1_1_pilot.json`
- Упрощённый batch: `tests/fixtures/radar_batch_sample.json`
