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
# --skip-staleness / MOEX_USER_CSV_SKIP_STALENESS=true —
# только если Даниил явно аттестовал историчность панели

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
# --real-data только после явного подтверждения Даниила,
# что источник — настоящий user_csv (не fixture)
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
| validate stale | стоп; обход только если Даниил явно аттестовал `--skip-staleness` + env |
| optimize success=false | `last_target` сохраняется прежний |
| любой ненулевой exit | не передавать partial bundle Аналитику как успех |

Dry-run на искусственных данных той же структуры:

```bash
MOEX_ISS_ENABLED=false python scripts/dry_run_real_shaped_analysis.py
```

## Чек-лист портфеля (для пользователя)

Шаблон полей: `docs/templates/portfolio_input_template.csv` (подставьте свои
SECID/ISIN; шаблонные EXA* не использовать как реальные).

Положите файл **вне репозитория**, например `%USERPROFILE%\moex-private\portfolio.csv`.

| # | Проверка |
|---|----------|
| 1 | Колонки: `as_of_date`, `account_label`, `ticker`, `isin`, `secid`, `board`, `security_type`, `quantity`, `market_value`, `weight`, `notes` |
| 2 | `secid` = канонический SECID Мосбиржи для каждой позиции |
| 3 | Несколько счетов: один SECID на разных `account_label` допускается (консолидация) |
| 4 | Сумма `weight` ≈ 1.0 (допуск входа ±0.005) |
| 5 | `market_value` согласован с количеством и ценой; при расхождении с weight >1 п.п. - исправить до прогона |
| 6 | Нет дублей одной и той же позиции на одном счёте с разными weight-базами |
| 7 | Файл не в git, не в `docs/examples/`, не в публичном handoff |

Предпроверка: `check-portfolio-ready --csv … --panel-tickers SECID1,SECID2,…`

## Чек-лист ценовой панели (user_csv)

Положите файл **вне репозитория**, например `%USERPROFILE%\moex-private\prices.csv`.

| # | Проверка |
|---|----------|
| 1 | Разделитель `;`, колонка дат `TRADEDATE`, далее столбцы по SECID (и опционально `SECID_VALUE`) |
| 2 | Все SECID из портфеля присутствуют как колонки |
| 3 | ≥20 торговых дней непрерывной истории (лучше больше) |
| 4 | Нет дубликатов дат; цены > 0; без нечисловых ячеек |
| 5 | Дневной скачок цены ≤ 80% (иначе QC отклонит) |
| 6 | Последняя дата близка к последней сессии **или** Даниил явно аттестует историчность (`--skip-staleness`) |
| 7 | Это настоящий пользовательский CSV, не `data/fixtures/synthetic_prices*.csv` |
| 8 | Файл не в git и не в публичном handoff |

Импорт: `import-user-prices --csv … --require-tickers …` при `MOEX_ISS_ENABLED=false`.
