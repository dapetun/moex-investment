---
name: cli-analyst-bundle
description: >
  Читать moex_analyst_bundle.v1 и по явной команде пользователя запускать
  разрешённую цепочку CLI (без ISS, без cron, без включения optimizer.yaml).
---

# CLI ↔ Аналитик портфеля (skill draft)

**Не применять в рабочий профиль без отдельного разрешения владельца.**

## Когда использовать

Только если пользователь **явно** просит: оценить портфель через CLI,
собрать bundle, сравнить с target, импортировать события, запустить optimize.

Не использовать для фоновых routines, автозапуска по файлам новостей,
Streamlit или включения `optimizer.yaml`.

## Разрешённая цепочка CLI

```text
check-portfolio-ready → adapt-portfolio --write-holdings →
import-user-prices (если новый CSV цен) → validate-data →
optimize --allow-optimize → compare → ingest-events [по запросу] →
build-analyst-bundle → отчёт по bundle
```

Окружение:

- `MOEX_ISS_ENABLED=false`
- `MOEX_DATA_SOURCE=user_csv` (реальный прогон) или `fixture` (синтетика)
- `optimizer.yaml`: не трогать (`enabled: false`)

## Валидация bundle

Перед отчётом проверить:

1. `schema == "moex_analyst_bundle.v1"`
2. Есть `holdings`, `validation`, при успехе — `target.payload.success == true`
3. Каждая цифра веса/drift/Sharpe взята из bundle/CLI JSON
4. Каждый `event_id` и `run_id` сохранены в отчёте со ссылкой на артефакт
5. Если `synthetic: true` — дисклеймер обязателен

Отказ в расчёте/интерпретации target, если:

- QC `ok=false` / stale без аттестации
- нет `last_target` или `success != true`
- `check-portfolio-ready` вернул blockers
- тикеры портфеля отсутствуют в панели (`USER_CSV_TICKERS_MISSING`)

## Запреты

- Не пересчитывать Max Sharpe / веса самостоятельно
- Не переводить `equity_assessment.direction/confidence` в expected return,
  constraints solver или торговые рекомендации
- Не вызывать ISS / зеркала
- Не публиковать абсолютные пути домашнего каталога пользователя в отчёте
  (только basename / `<local>/…`)
- Не рекомендовать сделки при расхождении weight vs market_value > 1 п.п.

## Формат отчёта (обязательные блоки)

1. Состав портфеля (из holdings)
2. QC входных данных
3. Целевые веса Max Sharpe + `run_id`
4. Отклонения compare + `run_id`
5. События радара с `event_id` / source / url (качественный блок)
6. Ограничения и неопределённость
7. Ссылки на артефакты bundle
