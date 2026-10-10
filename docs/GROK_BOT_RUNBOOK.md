# Runbook: moex-investment на Grok Bot (`/workspace`)

Офлайн-first CLI для связки с двумя ботами. **MOEX ISS по умолчанию выключен** до письменного ответа биржи о допустимом режиме. Seed `data/price_data.csv` **не** использовать как разрешённый источник для авторасчёта.

## 0. Ветки и клон

Репозиторий публичный. Default branch на GitHub: **`main`**. Рабочая линия с фичами может быть `prod` — уточняйте перед деплоем.

```bash
cd /workspace
git clone https://github.com/dapetun/moex-investment.git
cd moex-investment
# для приёмки PR #2:
# git fetch origin feature/headless-cli-grok-bot
# git checkout feature/headless-cli-grok-bot
# git rev-parse HEAD   # зафиксируйте SHA
python3 -m venv .venv
source .venv/bin/activate   # Windows cloud: .venv\Scripts\activate
pip install -U pip
# CLI + тесты: без Streamlit и без flaml (ML — optional extra)
pip install -e ".[dev]"
# dashboard на машине бота обычно не нужен:
# pip install -e ".[dashboard,ml]"
```

Храните venv внутри `/workspace/moex-investment/.venv` (после computer update пакеты могут пропасть — переустановите по этому runbook).

Не кладите GitHub tokens / пароли на shared computer без необходимости. Для публичного clone токен не нужен.

## 1. Переменные окружения

| Переменная | По умолчанию | Смысл |
|---|---|---|
| `MOEX_ISS_ENABLED` | `false` | Гейт сетевого ISS. Не включать без письменного clearance. |
| `MOEX_DATA_SOURCE` | `fixture` (если ISS выкл.) | `fixture` \| `iss` |
| `MOEX_FIXTURE_PATH` | `data/fixtures/synthetic_prices.csv` | Синтетика для разработки |
| `MOEX_RUNTIME_CACHE` | `data/cache/runtime_prices.csv` | Рабочий кэш CLI |

## 2. Каталоги на машине бота

```
data/portfolio/holdings.json     # факт. позиции (может отсутствовать → пустой)
data/fixtures/synthetic_prices.csv
data/cache/                      # runtime cache (gitignore)
data/inbox/events/               # пишет бот №1
data/processed/events/           # принятые события
data/outbox/runs/                # journal
data/outbox/reports/             # MD+JSON
data/outbox/last_target.json     # последний target после optimize
data/locks/                      # pipeline.lock
```

Скопируйте пример: `data/portfolio/holdings.example.json` → `holdings.json`.

### Holdings: ограничение весов (MVP)

`compare` и вывод текущих весов требуют **явного** поля `weight` у каждой позиции.
Позиции только с `shares` без `weight` дают машиночитаемую ошибку
`HOLDINGS_SHARES_WITHOUT_WEIGHTS` — веса не выдумываются.
Будущая задача: рыночные веса = shares × цены (после clearance источника котировок).

Перед `optimize` всегда выполняется QC данных. Для `fixture` календарная
свежесть **не** требуется (синтетика ≠ live market). Для `market`/`iss`
устаревшие/пустые/дырявые панели блокируют расчёт и **не** перезаписывают
`data/outbox/last_target.json`. Target пишется только при `success=true`.

## 3. Команды CLI

```bash
python -m moex_portfolio show-portfolio
python -m moex_portfolio update-data
python -m moex_portfolio validate-data --max-staleness-days 5
# мост радар → CLI (оригинал /workspace/invest/... не удаляется):
python -m moex_portfolio ingest-events \
  --source /workspace/invest/news/events_latest.json
# либо положить копию вручную в data/inbox/events/ и вызвать без --source
python -m moex_portfolio optimize --allow-optimize --mode universe --max-weight 0.5
python -m moex_portfolio compare --min-drift 0.05
python -m moex_portfolio report --run-id <run_id>
```

Коды выхода: `0` ok, `1` непредвиденная ошибка / missing run, `2` бизнес/валидация
(включая **частичный** отказ ingest: `partial=true`), `3` lock занят,
`4` источник заблокирован (ISS).

Радар пишет только в `/workspace/invest/news/`. CLI читает
`<repo>/data/inbox/events/`. Без шага `--source` (или ручного копирования)
события не появятся. После ingest исходник из inbox архивируется в
`data/processed/inbox_archive/`.

`optimize` без `--allow-optimize` отказывается работать.

`compare` для пустого текущего портфеля возвращает `allocation_kind=initial_allocation`
(`needs_rebalance=false`, `needs_action=true` при drift ≥ порога) — это не обычный ребаланс.

Если после аварийного kill остался `data/locks/pipeline.lock` с мёртвым PID,
следующий запуск CLI снимает stale lock автоматически. Если PID ещё «жив» в ОС —
удалите lock вручную только убедившись, что другого `python -m moex_portfolio` нет.

## 4. Роли ботов

**Бот №1 (корпоративный мониторинг):** пишет выпуск в
`/workspace/invest/news/events_latest.json` (schema 1.1). В `data/inbox/events/`
радара нет — мост через `ingest-events --source …` (см. выше). Не сохранять
сессии Cbonds на shared computer без согласия владельца.

**Бот №2 (аналитик):** пока **не** подключать CLI к рабочим инструкциям /
`optimizer.yaml` (`enabled: false`), пока не закрыты условия из decisions
handoff. Технически может вызывать CLI и читать stdout/exit/`outbox/`.
Не подменяет числа CLI. Не запускает ISS.

## 5. Юридический стоп по ISS

Пока нет письменного подтверждения допустимого бесплатного режима:

- не ставить `MOEX_ISS_ENABLED=true` для авторасчёта портфеля;
- не считать HTTP 200 разрешением;
- не подставлять tracked seed-кэш как обход.

При отказе биржи — отдельный анализ альтернативного источника (вне этого runbook).

## 6. После computer update / reset

1. `cd /workspace/moex-investment && git pull`
2. Пересоздать `.venv` и `pip install -e ".[dev]"`
3. Проверить `MOEX_ISS_ENABLED=false`
4. `python -m moex_portfolio show-portfolio`

## 7. Что не делать

- Не включать cron/routines для optimize без approve.
- Не подключать брокер и не исполнять заявки.
- Не утверждать готовность к реальной эксплуатации, пока не закрыт вопрос ISS и чек-лист критериев готовности.
