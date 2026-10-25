# Подключение реального портфеля (без передачи секретов в репо)

## Минимальный набор полей CSV

Обязательные колонки (шаблон: `docs/templates/portfolio_input_template.csv`):

| Колонка | Назначение |
|---|---|
| `as_of_date` | Дата среза позиций |
| `account_label` | Счёт/брокер (для multi-account) |
| `ticker` | Подсказка; ключ CLI — **SECID** |
| `isin` | Опционально, с `--isin-map` при неоднозначности |
| `secid` | Канонический идентификатор позиции |
| `board` | Режим торгов (TQBR и т.п.) |
| `security_type` | share / bond / … |
| `quantity` | Количество штук |
| `market_value` | Рыночная стоимость в валюте учёта |
| `weight` | Доля в портфеле (portfolio-level; сумма ≈ 1) |
| `notes` | Свободный текст |

Контракт: `data/portfolio/PORTFOLIO_CONTRACT.md`.

## Правила

1. Сумма `weight` = 1.0 (±1e-6 после адаптера; на входе CSV допуск ±0.005 с явной нормализацией).
2. При наличии `weight` он **приоритетнее** `market_value`; расхождение >1 п.п. — предупреждение в `check-portfolio-ready`.
3. Один SECID на нескольких счетах консолидируется; смешанная база weight/MV → ошибка.
4. Не кладите реальный CSV в git, логи CI или публичные примеры.

## Предпроверка (без optimize)

```bash
MOEX_ISS_ENABLED=false \
  python -m moex_portfolio check-portfolio-ready \
    --csv path/to/your.csv \
    --panel-tickers EXA1,EXA2,EXA3
```

Успех: `"ok": true`, `"ready_for_optimize": true`.

Затем:

```bash
python -m moex_portfolio adapt-portfolio --csv path/to/your.csv \
  --panel-tickers ... --write-holdings
```

## Что должен предоставить пользователь

- CSV (или уже готовый `data/portfolio/holdings.json`)
- Список тикеров для панели / сам файл цен (`user_csv`)
- Дату актуальности позиций

## Что система выводит сама

- Консолидацию счетов, QC панели, target, compare, bundle, ingest событий (отдельно)

## Что пока нельзя

- Автозагрузка MOEX ISS
- Постоянный вызов CLI из рабочего Аналитика без утверждённых skills
- Брокерские операции
