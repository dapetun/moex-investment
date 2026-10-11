# Сквозной сценарий: CLI + тестовый радар → bundle Аналитика

## Что делает

1. Синтетический multi-account CSV → `adapt-portfolio`
2. QC + Max Sharpe (`optimize --allow-optimize`)
3. `compare` current vs target
4. Ingest тестового выпуска радара (`--test-events`)
5. Сборка `moex_analyst_bundle.v1`
6. (Вне скрипта) one-shot задание Аналитику через существующий Grok Bot bridge

## Запуск

```bash
# из корня репозитория, ветка feature/headless-cli-grok-bot
MOEX_ISS_ENABLED=false MOEX_DATA_SOURCE=fixture \
  python scripts/run_e2e_analyst_scenario.py
```

Успех: stdout JSON с `"ok": true`, путь `bundle_path`.

Повторный запуск идемпотентен по событиям (`duplicate_skipped`).

## Изоляция

- Работа в `git clone` во временный каталог.
- Тестовые события → `data/processed/events_test/` (не `events/`).
- Контроль: fingerprint `data/` рабочего репо до/после не меняется.

## Ограничения

- Не включает ISS, broker, cron, merge PR, правки профилей ботов.
- `optimizer.yaml` не трогается (`enabled: false`).
- События не меняют математику оптимизации.
