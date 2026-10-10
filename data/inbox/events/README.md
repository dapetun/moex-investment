# Inbox: события бота №1 / Корпоративный радар

Положите сюда JSON-файлы `*.json`. Команда:

```bash
python -m moex_portfolio ingest-events
```

Поддерживаются: один объект, массив объектов, пакет `{ "events": [ ... ] }`.
Поля радара (`issuer_name`, `source_name`, `source_url`, `factual_summary`)
нормализуются в канон CLI. Неизвестный `event_type` отклоняется
(не подставляется фиктивный `disclosure_*`). См. `RADAR_CONTRACT.md`.

Имя в `processed/` строится из `event_id` (или хэша содержимого).
Повтор с тем же содержимым → `duplicate_skipped`; конфликт содержимого → `conflict`
без перезаписи.

## Обязательные поля (канон после нормализации)

- `event_type` — начинается с `disclosure_` или `dividend_`
- `title`
- `url` — ссылка на первоисточник
- `published_at` — ISO-дата/время
- `source` — например `e-disclosure`, `smart-lab`, `finam`, `dohod`

Опционально: `event_id`, `ticker`, `company`, `summary`, `facts`.

Cbonds не входит в обязательный контур MVP.
