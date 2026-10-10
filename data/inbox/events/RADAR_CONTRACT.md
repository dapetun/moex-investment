# Контракт: Корпоративный радар → CLI (требует подтверждения)

Полная схема «Корпоративного радара» **не найдена** в репозитории `moex-investment`.
Ниже — адаптер по полям, названным в ревью PR #2. Подтвердите или пришлите
канонический JSON Schema радара.

## Несовпадения с текущим каноном CLI

| Канон CLI | Поле радара (по ревью) | Статус адаптера |
|---|---|---|
| `source` | `source_name` | маппится |
| `url` | `source_url` | маппится |
| `summary` | `factual_summary` | маппится |
| `company` | `issuer_name` | маппится |
| `title` | (не указано) | из `factual_summary` или `{issuer}: {event_type}` |
| `published_at` | (не указано; пробуем `event_date`/`date`/…) | **подтвердить имя поля** |
| `event_type` | (не указано) | только явные алиасы; неизвестное → reject |
| `event_id` | (ожидается) | сохраняется; имя файла |
| пакет | обёртка с массивом | принимаем `{ "events": [ ... ] }` или `[...]` |

## Правила `event_type`

1. Уже `disclosure_*` / `dividend_*` → без изменений.
2. Известные алиасы (`dividend`, `e-disclosure`, `meeting`, …) → таблица в `events.py`.
3. Иначе → `EVENT_TYPE_UNMAPPED` (не подставляем фиктивный `disclosure_*`).

## Сохраняемые без интерпретации поля

Адаптер копирует и не переименовывает (если присутствуют):
`event_id`, `facts`, `equity_score`, `bond_score`, `score_equity`,
`score_bond`, `scores`, `impact_score`, `severity_score`, плюс полный
`radar_original`.

## Подтвердить у владельца радара / Grok Bot

1. Точное имя поля даты публикации (`published_at` vs `event_date`).
2. Полный перечень значений `event_type` / `category` / `type`.
3. Имя корневого ключа пакета (`events` или иное).
4. Наличие и формат `event_id` / `facts` / оценок акций и облигаций.
5. Канонический путь выпуска на облаке (`/workspace/invest/...`).

Синтетическая фикстура адаптера: `tests/fixtures/radar_batch_sample.json`.
