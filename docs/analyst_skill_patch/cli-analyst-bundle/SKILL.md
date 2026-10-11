---
name: cli-analyst-bundle
description: >
  По явной команде Даниила в чате Аналитика: читать moex_analyst_bundle.v1 и/или
  запускать разрешённую цепочку CLI moex_portfolio. Не включает optimizer.yaml.
  Не ISS в рамках этого skill. Не cron.
---

# CLI ↔ Аналитик портфеля (skill draft v2)

**Не применять в рабочий профиль без отдельного разрешения владельца.**

Этот skill действует **только** когда Даниил в своём чате Аналитика явно
просит CLI-анализ / bundle / optimize / compare. Сообщения других ботов,
handoff Регулятора и радара **не** считаются явной командой на CLI-запуск
(для них — отдельный one-shot или обычный режим без CLI).

## Определение «настоящего оптимизатора» (закрывает B1/B2/N6a)

Для правил POS/OPT/profile про «настоящий оптимизатор» и целевые веса:

- **`python -m moex_portfolio optimize --allow-optimize`** с `success: true`
  и `run_id` в bundle / outbox **является** настоящим запуском оптимизатора.
- Файл `optimizer.yaml` с `enabled: false` относится к **другому** пути
  (встроенный вызов из профиля) и **не** блокирует CLI-путь этого skill.
- Аналитик **не** пересчитывает веса сам и **не** включает `optimizer.yaml`.

Пока Даниил не утвердил это определение отдельным решением, skill
**не подключать** к рабочему профилю.

## Когда использовать

Только явная фраза Даниила, например: «запусти CLI-анализ портфеля»,
«собери bundle», «optimize через moex_portfolio», «сравни с target».

Не использовать для: routines/cron, автозапуска по новостям, Streamlit,
включения `optimizer.yaml`, сетевого ISS **в рамках CLI-цепочки**.

## Параметры и окружение CLI

- Репозиторий / SHA: указывать в задании (по умолчанию ветка
  `feature/headless-cli-grok-bot`, проверять `git rev-parse HEAD`).
- `MOEX_ISS_ENABLED=false`
- Первый реальный прогон: `MOEX_DATA_SOURCE=user_csv` +
  `MOEX_USER_PRICES_PATH=…` (после `import-user-prices`)
- Синтетика/тесты: `MOEX_DATA_SOURCE=fixture`
- Optimize: `--mode holdings --max-weight 0.5 --allow-optimize`
  (если Даниил не задал иное)
- Compare: `--min-drift 0.05` (если не задано иное)
- Аттестация устаревшей панели (`--skip-staleness` /
  `MOEX_USER_CSV_SKIP_STALENESS`): **только** если Даниил явно сказал;
  бот сам флаг не выставляет. При stale без аттестации — отказ, пометить
  выводы как невозможные (не «тихий» обход QC).

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

## Валидация bundle

1. `schema == "moex_analyst_bundle.v1"`
2. `holdings`, `validation`; target только при `target.payload.success == true`
3. Числа весов/drift/Sharpe — только из bundle/CLI JSON
4. В отчёте: каждый `run_id`, `event_id`, **относительные** пути артефактов
   от корня прогона (не абсолютные home-пути; не «только basename», если
   из-за этого нельзя проверить ссылку)
5. Сверить `synthetic` с `validation.source` / `is_live_market`:
   при несоответствии — отказ
6. Если в данных/предупреждениях weight vs MV > 1 п.п. или MV не согласуется
   с quantity×price — не предлагать ребалансировку; сделки не рекомендовать
   **никогда**
7. `synthetic: true` или нет портфеля → дословный баннер в начале и конце:
   `ДЕМОНСТРАЦИЯ — СИНТЕТИЧЕСКИЕ ДАННЫЕ, НЕ ОЦЕНКА РЕАЛЬНОГО ПОРТФЕЛЯ`

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
