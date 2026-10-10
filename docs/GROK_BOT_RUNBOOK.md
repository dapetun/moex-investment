# Runbook: moex-investment на Grok Bot (`/workspace`)

Офлайн-first CLI для связки с двумя ботами. **MOEX ISS по умолчанию выключен** до письменного ответа биржи о допустимом режиме. Seed `data/price_data.csv` **не** использовать как разрешённый источник для авторасчёта.

## 0. Ветки и клон

Репозиторий публичный. Default branch на GitHub: **`main`**. Рабочая линия с фичами может быть `prod` — уточняйте перед деплоем.

```bash
cd /workspace
git clone https://github.com/dapetun/moex-investment.git
cd moex-investment
# выберите нужную ветку явно:
# git checkout main
# или: git checkout prod
python3 -m venv .venv
source .venv/bin/activate   # Windows cloud: .venv\Scripts\activate
pip install -U pip
pip install -e ".[dev]"
# dashboard (Streamlit) на машине бота обычно не нужен
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

## 3. Команды CLI

```bash
python -m moex_portfolio show-portfolio
python -m moex_portfolio update-data
python -m moex_portfolio validate-data --max-staleness-days 5
python -m moex_portfolio ingest-events
python -m moex_portfolio optimize --allow-optimize --mode universe --max-weight 0.5
python -m moex_portfolio compare --min-drift 0.05
python -m moex_portfolio report --run-id <run_id>
```

Коды выхода: `0` ok, `2` бизнес/валидация, `3` lock занят, `4` источник заблокирован (ISS).

`optimize` без `--allow-optimize` отказывается работать.

## 4. Роли ботов

**Бот №1 (корпоративный мониторинг):** браузер → e-disclosure и (опционально) Finam / Smart-Lab / ДОХОДЪ → JSON в `data/inbox/events/`. Не сохранять сессии Cbonds на shared computer без явного согласия владельца. Cbonds вне обязательного MVP.

**Бот №2 (аналитик):** вызывает CLI, читает `outbox/reports` и journal, пишет текстовые пояснения. Не подменяет числа CLI. Не запускает ISS.

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
