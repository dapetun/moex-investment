# Inbox: события бота №1

Положите сюда JSON-файлы `*.json`. Команда:

```bash
python -m moex_portfolio ingest-events
```

## Обязательные поля

- `event_type` — начинается с `disclosure_` или `dividend_`
- `title`
- `url` — ссылка на первоисточник
- `published_at` — ISO-дата/время
- `source` — например `e-disclosure`, `smart-lab`, `finam`, `dohod`

Опционально: `ticker`, `company`, `summary`.

Cbonds не входит в обязательный контур MVP.
