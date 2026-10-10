# Контракт: Корпоративный радар → CLI (подтверждён 2026-10-10)

Источники подтверждения (отдельные handoff, не смешивать ref и id):

| ref | id RESULT | тема |
|---|---|---|
| `cur-20261010-1713` | `2026-10-10_radar-portfolio-contract` | схемы радара, пути, расхождения CLI |
| `cur-20261010-1715` | `2026-10-10_cursor-headless-cli-facts` | факты среды / частичный |
| `cur-20261010-1820` | `2026-10-10_pr2-test-c-rerun` | Test C на SHA `a5fff7f` |
| `cur-20261010-1936` | `2026-10-10_portfolio-eventtype-contract` | портфель (amend) + полный bond `event_type` |

Схемы на облаке: `/workspace/invest/schemas/event.schema.json`,
`events_file.schema.json`.

## Канонические пути (облако)

| Роль | Путь |
|---|---|
| Выпуск радара | `/workspace/invest/news/events_latest.json` |
| История | `/workspace/invest/news/events_history.jsonl` |
| Уведомление аналитику | `/workspace/invest/handoff/radar_to_analyst/<YYYYMMDD_HHMM>.md` |
| Inbox CLI | `<repo>/data/inbox/events/*.json` |
| Архив исходников после ingest | `<repo>/data/processed/inbox_archive/` |
| Текущие принятые события | `<repo>/data/processed/events/` |
| История ревизий CLI | `<repo>/data/processed/events_history/` |

**Мост:** радар **не** пишет в `data/inbox/events/`. Передача:

```bash
python -m moex_portfolio ingest-events \
  --source /workspace/invest/news/events_latest.json
```

Оригинал `--source` не удаляется. Копия в inbox после обработки
переносится в `processed/inbox_archive/`.

При `partial=true` (exit 2) JSON-отчёт печатается в **stderr**, stdout пуст.

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
| `published_at` | ISO date или datetime; **`unknown`/пусто → reject** (`PUBLISHED_AT_INVALID`); не подменяется на `event_date` без метки |
| `event_date` | дата события (YYYY-MM-DD), сохраняется отдельно |
| `event_id` | `EV-<YYYYMMDD>-<TICKER>-<NNN>`; имя файла processed |
| `event_type` | строка из allowlist радара (см. ниже), **без** переписывания в `disclosure_*` |
| `equity_assessment` / `bond_assessment` | сохраняются целиком; `unknown` ≠ `low`/`ignore` |
| `duplicate_of` / `novelty=duplicate` / `materiality=ignore` | skip (не reject), статус в `details` |
| `revision` | при той же идентичности → `updated` (см. ниже) |
| полный объект | `radar_original` |

Поля `facts` у радара нет; факты — в `factual_summary` + блоки оценок.

## Ревизии (повторная оценка)

| Ситуация | статус | current |
|---|---|---|
| новый `event_id` | `accepted` | создаётся |
| полный повтор той же версии | `duplicate_skipped` | без изменений |
| тот же `event_id` + жёсткая согласованность + изменились оценки/содержание | `updated` | предыдущая → `events_history/`, затем новая current |
| тот же `event_id`, разошлись ticker/isin/event_type/event_date | `conflict` / `EVENT_IDENTITY_MISMATCH` | **не** перезаписывается |
| тот же `revision.number` и/`или` `generated_at`, другое содержимое | `conflict` / `EVENT_EQUAL_FRESHNESS_CONFLICT` | **не** перезаписывается |
| более старый выпуск (`revision.number` или `radar_batch.generated_at`) | `stale_skipped` | current не трогаем; **не** rejected (exit 0) |

**Первичный ключ:** только `event_id` (RESULT 1936).
Жёсткая согласованность: `ticker`, `isin`, `event_type`, `event_date`.
Мягкие (ревизия с флагом `soft_identity_changed`): `document_url`, `source_url`,
`published_at`, `url`, `issuer_name` (радар может переписать сокращение/кавычки;
RESULT `cur-20261010-2229` I9).
Оценки / materiality / rationale — не идентичность.
`novelty=clarification` с `duplicate_of` — **не** skip; skip только
`novelty=duplicate` и `materiality=ignore`.

**Ограничение свежести:** если нет `revision.number` и нет `radar_batch.generated_at`
у обеих сторон, порядок ревизий не гарантируется (`freshness_guaranteed=false` в
`details`). Не заявляем per-event гарантию только по полям оценок.

В отчёте ingest есть счётчик `updated` и `details[].changed_fields`.

## Allowlist `event_type`

**Equity** (`settings.yaml` → `equity_rules`, RESULT 1713/1820):

`default_or_technical_default`, `sanctions_or_regulatory_ban`,
`bankruptcy_or_license_revocation`, `delisting_or_listing_change`,
`dividend_recommendation`, `dividend_policy_change`,
`buyback_or_additional_issue`, `major_transaction_or_m_and_a`,
`credit_rating_change`, `financial_statements_ifrs`,
`financial_statements_ras`, `operating_results`, `guidance_change`,
`board_decision_other`, `shareholder_meeting`, `bond_offer_coupon_or_put`,
`operational_incident`, `project_launch`, `management_change_ceo_cfo`,
`management_change_routine`, `litigation_major`, `market_technical_notice`,
`press_release_marketing`, `noise_holiday_award_charity`, `unknown`.

**Bond-only** (`bond_rules.start`, RESULT 1936 §2.2, 15 ключей):
`coupon_payment_missed_or_delayed`, `coupon_payment_regular`,
`principal_redemption_scheduled`, `put_offer_announced`,
`call_offer_early_redemption`, `rating_action_downgrade`,
`rating_action_upgrade`, `rating_action_affirmed`, `issue_terms_change`,
`covenant_breach_or_waiver`, `collateral_or_guarantee_change`,
`leverage_change_material`, `liquidity_stress`, `refinancing_risk`,
`dividend_large`.

Канон: union equity+bond = 39 ключей + `unknown`. Неизвестные →
`EVENT_TYPE_UNMAPPED`, без выдуманных `disclosure_*`.

Legacy CLI: префиксы `disclosure_*` / `dividend_*` и короткие алиасы
(`material_fact`, `meeting`, …) — только для старых фикстур.

## Коды `ingest-events`

| Ситуация | exit | поля отчёта |
|---|---|---|
| все события приняты / skip / дубликаты / updates / `stale_skipped` | 0 | `partial=false`; `stale_skipped` не rejected |
| есть хотя бы один reject/conflict (в т.ч. equal-freshness) | **2** | `partial=true`, JSON в **stderr**, `details[]` с `event_id` |

## Фикстуры

- Форма пилота (синтетика, **не** байт-в-байт копия боевого выпуска):
  `tests/fixtures/radar_events_latest_v1_1_pilot.json`
  — `is_test: true`, все `event_id` в namespace `TEST-EV-…`
  (например `TEST-EV-20261009-SBER-001`), без пересечения с боевыми `EV-…`.
  В JSON Schema `event_id` — строка без regex; префикс `TEST-` допустим
  и не требует правки боевой схемы.
- Каталог `processed/events/` общий для тестовых и боевых id (MVP).
  Разделение — соглашением имён (`TEST-EV-…`); флаг `is_test` у пилотного
  боевого выпуска радара тоже может быть `true`, поэтому по нему нельзя
  отфильтровать каталог. Отдельный каталог/CLI-gate — вне текущего PR.
- Упрощённый batch: `tests/fixtures/radar_batch_sample.json`
