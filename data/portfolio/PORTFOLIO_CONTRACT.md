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

`isin`/`board`/`security_type` сохраняются в выводе адаптера (мета), даже если
`save_holdings` их отбрасывает. Неоднозначность → `PORTFOLIO_ID_AMBIGUOUS`.

## 3. Веса

- Единый допуск с аналитиком: сумма `weight` = 1.0 (±**0.005**).
- `cash` — абсолютная сумма (RUB), **не** входит в сумму весов.
- Shares-only без weight → `HOLDINGS_SHARES_WITHOUT_WEIGHTS`.
- Молча не нормируем; веса вне ±0.005 — reject.

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
