# Inbox: события Корпоративного радара → CLI

Канонический выпуск на облаке: `/workspace/invest/news/events_latest.json`
(schema 1.1). Радар **не** пишет сюда напрямую.

```bash
# предпочтительно: мост без удаления оригинала
python -m moex_portfolio ingest-events \
  --source /workspace/invest/news/events_latest.json

# или положить копию *.json в этот каталог и:
python -m moex_portfolio ingest-events
```

После обработки файл из inbox уходит в `data/processed/inbox_archive/`
(не удаляется бесследно). Частичный отказ → exit **2**, `partial=true`.

Поддерживаются: один объект, массив, пакет `{ "events": [ ... ] }`.
Типы — allowlist радара (см. `RADAR_CONTRACT.md`); неизвестный тип → reject
без выдуманного `disclosure_*`. Оценки `equity_assessment` / `bond_assessment`
сохраняются.

Имя в `processed/` — из `event_id` (или хэша). Повтор → `duplicate_skipped`;
конфликт → `conflict` без перезаписи. `duplicate_of` / `materiality=ignore` →
skip (не reject).

Фикстура формы пилота: `tests/fixtures/radar_events_latest_v1_1_pilot.json`.
