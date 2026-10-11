---
name: cli-analyst-bundle
description: >
  По явной команде Даниила в чате Аналитика: читать moex_analyst_bundle.v1 и/или
  запускать разрешённую цепочку CLI moex_portfolio. Не включает optimizer.yaml.
  Не ISS в рамках этого skill. Не cron.
---

# CLI ↔ Аналитик портфеля (skill draft v2.1)

**Не применять без Разрешения A** (`permissions/PERMISSION_A.md`).
Дословные правки live: `live_patches/`. Deploy: `SAFE_DEPLOY.md`.

Этот skill действует **только** когда Даниил в своём чате Аналитика явно
просит CLI-анализ / bundle / optimize / compare. Сообщения других ботов,
handoff Регулятора и радара **никогда** не запускают CLI (ни fixture, ни
user_csv). Для них — обычный режим Аналитика без CLI (события через
`news/events_latest.json`).

## Определение «настоящего оптимизатора» (решения владельца)

Для правил POS/OPT/profile про «настоящий оптимизатор» и целевые веса:

- **`python -m moex_portfolio optimize --allow-optimize`** с `success: true`
  и `run_id` в bundle / outbox **является** настоящим запуском оптимизатора
  (основной вычислительный интерфейс интеграции).
- Файл `optimizer.yaml` с `enabled: false` относится к **другому** пути
  (внешний интеграционный вызов через `run_optimizer.example.py --i-confirm`)
  и **не** блокирует CLI-путь этого skill; yaml **не включать**.
- Аналитик **не** пересчитывает веса сам и **не** включает `optimizer.yaml`.
- Реальные позиции / user_csv — только после **Разрешения B**; до него —
  только fixture / синтетика.

## Когда использовать

Только явная фраза Даниила, например: «запусти CLI-анализ портфеля»,
«собери bundle», «optimize через moex_portfolio», «сравни с target».

Не использовать для: routines/cron, автозапуска по новостям, Streamlit,
включения `optimizer.yaml`, сетевого ISS **в рамках CLI-цепочки**.

## Параметры и окружение CLI

- **SHA репо обязателен** в задании Даниила; без SHA — отказ. После
  checkout сверить `git rev-parse HEAD` с указанным. Плавающий HEAD
  ветки без фиксации не использовать.
- Путь к клону / интерпретатору: из задания Даниила (на box — явно
  указать; не угадывать).
- `MOEX_ISS_ENABLED=false`
- Реальный прогон (`MOEX_DATA_SOURCE=user_csv` +
  `MOEX_USER_PRICES_PATH=…`) — **только** после отдельного разрешения
  Даниила на реальные позиции (иначе только fixture / dry-run).
- Синтетика/тесты: `MOEX_DATA_SOURCE=fixture`
- Optimize: `--mode holdings --max-weight 0.5 --allow-optimize`
  (если Даниил не задал иное)
- Compare: `--min-drift 0.05` (если не задано иное)
- Аттестация устаревшей панели (`--skip-staleness` /
  `MOEX_USER_CSV_SKIP_STALENESS`): **только** для `user_csv` и только если
  Даниил явно сказал; бот сам флаг не выставляет. При stale user_csv без
  аттестации — отказ. Для `fixture` (Permission A) stale/не-ISS = warn
  «синтетика» (см. «QC для пути B»), не этот отказ.

## Единый порядок цепочки

```text
check-portfolio-ready --panel-tickers … →
import-user-prices --require-tickers … (если новый CSV цен) →
validate-data →
adapt-portfolio --write-holdings →
optimize --allow-optimize --mode holdings →
compare →
ingest-events (только по отдельной явной команде; иначе события
  из штатного news/events_latest.json) →
build-analyst-bundle [--real-data только если источник user_csv
  и Даниил подтвердил] →
отчёт по bundle + запись в portfolio/reports и logs по правилам профиля
```

Fail-safe: любой ненулевой exit или partial bundle → **стоп**, не выдавать
успешный отчёт с целевыми весами; не затирать прежний `last_target`
(CLI сам не обновляет target при `success!=true`).

### QC для пути B (CLI)

Штатный skill QC остаётся для yaml-пути и отчётов по радару. Для CLI-пути:

- Контроль качества перед optimize = `validate-data` (+ `check-portfolio-ready`
  в начале цепочки); итог записать в отчёт §9 и в журнал профиля
  (таблица pass/warn/fail), как требует QC.
- `MOEX_DATA_SOURCE=fixture` (Permission A): устаревание панели и источник
  ≠ ISS → **warn «синтетика»**, не fail; баннер ДЕМОНСТРАЦИЯ обязателен.
  Без этого one-shot A невозможен при QC:16/24/30.
- `user_csv` (только Permission B): источник котировок `user_csv` разрешён
  владельцем как исключение из «только ISS»; свежесть — как в правилах
  stale/аттестации выше.
- Если `news/events_latest.json` имеет `is_test: true` — явно пометить в
  отчёте, что события тестовые.

## Валидация bundle

1. `schema == "moex_analyst_bundle.v1"`
2. `holdings`, `validation`; target только при `target.payload.success == true`
3. Числа весов/drift/Sharpe — только из bundle/CLI JSON
4. В отчёте: каждый `run_id`, `event_id`, **относительные** пути артефактов
   от корня прогона (не абсолютные home-пути; не «только basename», если
   из-за этого нельзя проверить ссылку)
5. Сверить флаг `synthetic` с `validation.source` / `is_user_csv`
   (**не** с `is_live_market`: для `user_csv` код всегда даёт
   `is_live_market=false`):
   - `source=fixture` → ожидать `synthetic: true`
   - `source=user_csv` или `is_user_csv: true` → `synthetic: false`
     и `--real-data` только если Даниил подтвердил
   - иное несоответствие → отказ
6. Если в данных/предупреждениях weight vs MV > 1 п.п. или MV не согласуется
   с quantity×price — не предлагать ребалансировку; сделки не рекомендовать
   **никогда**
7. `synthetic: true` или нет портфеля → баннер в начале и конце как в
   live POS/P:D17 (дефис):  
   `ДЕМОНСТРАЦИЯ - СИНТЕТИЧЕСКИЕ ДАННЫЕ, НЕ ОЦЕНКА РЕАЛЬНОГО ПОРТФЕЛЯ`

Отказ в интерпретации target также если: QC fail; нет successful target;
blockers `check-portfolio-ready`; `USER_CSV_TICKERS_MISSING`; ненулевой exit.

## События радара

- Штатный качественный вход профиля: `news/events_latest.json` (как сейчас).
- CLI `ingest-events` — только по отдельной явной команде Даниила; не
  подменять и не дублировать без указания источника в отчёте.
- Оценки радара (`direction`/`confidence`/`materiality`) **не** входы Max Sharpe.

## Запреты

- Не пересчитывать Max Sharpe / веса
- Не переводить оценки радара в expected return / constraints / ордера
- В CLI-цепочке не вызывать ISS и зеркала (ограничение **этого** skill,
  не глобальный запрет ISS для штатного QC профиля)
- Не рекомендовать сделки никогда; при плохих данных — не предлагать
  «оценить ребалансировку» как действие
- Не класть реальные CSV в git / публичные handoff

## Формат отчёта

Строго 9 разделов `analysis_spec.md` §5 (порядок профиля). Блоки CLI
(веса, QC, compare, run_id) встраивать в разделы «Состояние рыночных
данных…» и «Оценка влияния»; не подменять структуру POS/SPEC.
