# Патч (опционально при Permission A): `analysis_spec.md`

**Не применять без Permission A.**  
Путь: `/workspace/invest/portfolio/analysis_spec.md`  
Базовый sha256: `fa1ee6e4f2ec9dbf63e93d83c22773282e97680e4cf334ea37d5e4e4eb5fc3af`

Минимально нужен для согласованности с D04/OPT; не меняет формат §5 и правила радара.

---

## Изменение 1 — §1 таблица, после строки про `optimizer.yaml` (вставка строки таблицы)

**Добавить строку:**
```text
| `moex_analyst_bundle.v1` (outbox / путь из задания) | пакет CLI moex_portfolio при явной команде Даниила (skill cli-analyst-bundle); не заменяет `news/events_latest.json` | JSON schema в dapetun/moex-investment docs/ANALYST_BUNDLE_CONTRACT.md |
```

## Изменение 2 — §1, формулировка «единственный машинный вход» (строка 9, уточнение)

**Было (фрагмент):**
```text
| `news/events_latest.json` | события от «Корпоративного радара» — **единственный машинный вход** (дайджест `.md` не парсится) | ...
```

**Стало:**
```text
| `news/events_latest.json` | события от «Корпоративного радара» — **единственный машинный вход от радара** (дайджест `.md` не парсится); CLI-bundle — отдельный вход только по явной команде Даниила | ...
```

## Изменение 3 — §4 после пункта про «оптимизатор не подключён» (вставка)

**Добавить:**
```text
- Параллельный CLI-путь (без изменения этого yaml): по явной команде Даниила skill cli-analyst-bundle запускает `python -m moex_portfolio optimize --allow-optimize`. Успех = `success: true` и `run_id` в bundle/outbox. `optimizer.yaml` остаётся `enabled: false` и к CLI-пути не относится. Реальные позиции / user_csv — только после отдельного разрешения владельца.
```

## Что не менять

- §2 правила анализа событий;
- §3 QC (ISS для штатного market_data);
- §5 порядок 9 разделов;
- баннер (в SPEC с длинным тире; в POS/profile — дефис; при сверке принимать оба как эквивалент баннера ДЕМОНСТРАЦИЯ).
