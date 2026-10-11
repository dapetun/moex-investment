# Процедура первого реального анализа (user_csv only)

ISS выключен. `optimizer.yaml` не включать. Реальные файлы — **только вне git**.

## Безопасные каталоги (пример)

Положите файлы **вне** репозитория, например:

```text
%USERPROFILE%\moex-private\portfolio.csv
%USERPROFILE%\moex-private\prices.csv
```

Не коммитьте, не кладите в `docs/examples/`, не прикладывайте к публичным handoff.

## Последовательность

```bash
export MOEX_ISS_ENABLED=false

# 1. Валидация портфеля (без optimize)
python -m moex_portfolio check-portfolio-ready \
  --csv "$HOME/moex-private/portfolio.csv" \
  --panel-tickers SECID1,SECID2,...

# стоп, если ok=false

# 2. Импорт цен (явный user_csv)
python -m moex_portfolio import-user-prices \
  --csv "$HOME/moex-private/prices.csv" \
  --require-tickers SECID1,SECID2,...
# при заведомо исторической панели: --skip-staleness
# и MOEX_USER_CSV_SKIP_STALENESS=true

export MOEX_DATA_SOURCE=user_csv
export MOEX_USER_PRICES_PATH=<путь из sidecar cache_abs или runtime_cache>

# 3. QC
python -m moex_portfolio validate-data --max-staleness-days 5
# стоп при ok=false (если не аттестована историчность)

# 4. Holdings
python -m moex_portfolio adapt-portfolio \
  --csv "$HOME/moex-private/portfolio.csv" \
  --panel-tickers SECID1,... --write-holdings

# 5. Optimize + compare (явный флаг)
python -m moex_portfolio optimize --allow-optimize --mode holdings --max-weight 0.5
# стоп если success!=true — last_target не перезапишется при неуспехе

python -m moex_portfolio compare --min-drift 0.05

# 6. События (опционально, prod без --test-events)
# python -m moex_portfolio ingest-events --source <radar_release.json>

# 7. Bundle
python -m moex_portfolio build-analyst-bundle \
  --out-dir "$HOME/moex-private/bundle" \
  --real-data \
  --run-ids <opt_run>,<cmp_run>

# 8. Аналитик (после approve skill): явная команда пользователя
# «Оцени портфель по этому bundle» + путь к JSON
```

## Fail-safe

| Сбой | Действие |
|---|---|
| check-portfolio-ready blockers | стоп; holdings/target не трогать |
| import USER_CSV_* | стоп; кэш не обновлять (ошибка до copy при валидации) |
| validate stale | стоп или явный `--skip-staleness` + env |
| optimize success=false | `last_target` сохраняется прежний |
| любой ненулевой exit | не передавать partial bundle Аналитику как успех |

Dry-run на искусственных данных той же структуры:

```bash
MOEX_ISS_ENABLED=false python scripts/dry_run_real_shaped_analysis.py
```

## Чек-лист портфеля (для пользователя)

См. раздел в итоговом ответе чата / шаблон `docs/templates/portfolio_input_template.csv`.

## Чек-лист ценовой панели

Формат `;`, колонка `TRADEDATE`, столбцы `SECID` и опционально `SECID_VALUE`.
≥20 торговых дней, без дубликатов дат, цены > 0, дневной скачок ≤ 80%,
все SECID портфеля присутствуют.
