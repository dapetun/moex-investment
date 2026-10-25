# Разрешение B — анализ реального портфеля

Рассматривается **только после** успешного Разрешения A.  
Не выдаётся вместе с A одним текстом.

## Предусловия

1. Permission A применено и one-shot fixture принят.
2. Пользовательские файлы **вне GitHub**:
   - `portfolio.csv` (поля по шаблону / onboarding)
   - `prices.csv` (user_csv, `;`, TRADEDATE + SECID)
3. `MOEX_ISS_ENABLED=false`; источник котировок — `user_csv`.
4. Явный запрос Даниила в чате Аналитика на расчёт по этим файлам + SHA.
5. Свежесть/QC пройдены или Даниил явно аттестовал `--skip-staleness`.

## Что утверждается

- Запуск CLI-цепочки на указанных локальных/box-путях (не в git)
- `--real-data` в bundle только после подтверждения, что источник — user_csv
- Отчёт Аналитика по реальному bundle с ограничениями и сверкой чисел

## Что по-прежнему запрещено

- Cron / routines / автозапуск
- Брокер / сделки / ордера
- Публикация реальных CSV в git или публичный handoff
- Включение `optimizer.yaml`
- ISS в CLI-цепочке (штатный QC профиля не тема B)

## Критерий успеха B

- `check-portfolio-ready` ok
- import + validate ok (или аттестованный stale)
- optimize success + run_id; compare; bundle
- отчёт с run_id/event_id, без подмены весов, с ограничениями данных
- fail-safe: при ошибке предыдущий last_target не затёрт; partial не принят

## Отказ / стоп

Любой blocker QC, отсутствующий target, partial ingest, несовпадение
synthetic/source, запрос из handoff/радара вместо чата Даниила.
