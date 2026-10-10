# Контракт модели портфеля: аналитик ↔ CLI

Статус: **amend accepted** — RESULT `cur-20261010-1936` /
`2026-10-10_portfolio-eventtype-contract` (+ факты `cur-20261010-1713`).

## 1. Фактический портфель

| Роль | Путь | Формат |
|---|---|---|
| Аналитик (вне CLI) | `/workspace/invest/portfolio/portfolio.csv` | ISIN/SECID/board, weight, quantity |
| **Канон CLI** | `<repo>/data/portfolio/holdings.json` | `ticker` + `weight` и/или `shares`, `cash` |

CLI **не** мигрирует и не перезаписывает файлы в `/workspace/invest`.
Мост: `python -m moex_portfolio adapt-portfolio --csv <path> [--write-holdings]`.

## 2. Идентификаторы

Ключ позиции CLI = **SECID** (не CSV-`ticker` облигации: у `TSTA-BO1`
secid может быть `RU00TEST0004`). Порядок в адаптере:

1. `secid` → поле `ticker` holdings;
2. карта `--isin-map` / `isin_to_ticker`;
3. CSV `ticker` только если secid нет.

`isin`/`board`/`security_type`/`account_label`/`notes→note` сохраняются в выводе
адаптера и в `holdings.json` после `--write-holdings`. Битая строка или смешанные
weight/shares → отказ всего файла (`PORTFOLIO_ROW_ERRORS` /
`PORTFOLIO_MIXED_WEIGHTS`), без записи неполного holdings. Неоднозначность →
`PORTFOLIO_ID_AMBIGUOUS`.

Одинаковый SECID на нескольких счетах (`account_label`): адаптер **консолидирует**
в одну позицию (сумма portfolio-level `weight` или `market_value` + `shares`),
сохраняя исходные счета в `accounts[]`. Смешанная база (часть строк с weight,
часть только shares/MV) → `PORTFOLIO_CONSOLIDATION_AMBIGUOUS`, без угадывания.
Канонический `holdings.json` по-прежнему отвергает дубликат ticker
(`duplicate ticker`) — дубликаты допустимы только во входном CSV до адаптера.

## 3. Веса

- Канон CLI / оптимизатор: сумма `weight` = 1.0 (±**1e-6**, `WEIGHT_SUM_TOLERANCE`).
- Вход CSV аналитика: допуск ±**0.005** (`ANALYST_WEIGHT_SUM_TOLERANCE`).
  При `1e-6 < |Σ−1| ≤ 0.005` адаптер **явно** нормализует веса к 1.0 и пишет в
  метаданные `adapter.weight_normalized=true`, `adapter.weight_sum_before`.
  Вне ±0.005 → reject (`PORTFOLIO_WEIGHT_SUM`), без тихой подгонки.
- `cash` — абсолютная сумма (RUB), **не** входит в сумму весов.
- Shares-only без weight → `HOLDINGS_SHARES_WITHOUT_WEIGHTS`.

## 4. Missing vs empty

| `file_status` | смысл |
|---|---|
| `missing` | `holdings.json` отсутствует |
| `empty` | файл есть, `positions: []` |
| `ok` | есть позиции |

`show-portfolio` возвращает `file_status` вместе с JSON.

## 5. Тикер вне ценовой панели

Адаптер с `--panel-tickers` помечает `adapter.missing_from_panel[]`.
Вес/цену не выдумывает. Optimize/compare на таких тикерах — по правилам QC панели.

## 6. Compare current vs target

- Одни ключи: uppercase ticker.
- Одна база: явные weights (сумма ≈ 1).
- Target только с `success: true`.
- Пустой current + непустой target → `allocation_kind=initial_allocation`.

## 7. Сценарии аналитика

Пока инструкции бота «Аналитик портфеля» **не** меняем (защищено).
Технически доступны: `show-portfolio`, `adapt-portfolio`, `compare`,
`optimize --allow-optimize` (отдельно от `optimizer.yaml` с `enabled: false`).
