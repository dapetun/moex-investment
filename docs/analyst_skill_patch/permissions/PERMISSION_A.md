# Разрешение A — подключение CLI-skill к рабочему Аналитику

**Не включает** анализ реального портфеля (это Разрешение B).

## Что утверждается

1. Скопировать skill `cli-analyst-bundle` из репо на **зафиксированном SHA**.
2. Применить дословные патчи:
   - `live_patches/OPT_SKILL.patch.md`
   - `live_patches/POS_SKILL.patch.md`
   - `live_patches/QC_SKILL.patch.md`
   - `live_patches/PROFILE_DESCRIPTION.patch.md`
   - `live_patches/SPEC_analysis_spec.patch.md` (если включён в approve)
3. Выполнить `SAFE_DEPLOY.md` шаги 1–10 на fixture/синтетике
   (включая 7b dry-run формы user_csv на искусственных данных).
4. `optimizer.yaml` остаётся `enabled: false`.
5. Инициатор CLI — только Даниил в чате Аналитика.
6. PR #2 не сливать.

## Что запрещено в рамках A

- Реальные `portfolio.csv` / `prices.csv` / user_csv боевых данных
- Включение cron / routines / брокера / сделок
- Запуск CLI / optimize по сообщению радара или handoff (никогда, даже на fixture)
- Изменение settings радара и пользовательских данных invest
- Слияние PR #2

## Критерий успеха A

- One-shot fixture: exit 0, bundle v1, баннер ДЕМОНСТРАЦИЯ, run_id в отчёте
- Программная сверка claims без расхождений
- Yaml sha256 неизменен
- Rollback-план проверен (хотя бы dry: бэкап есть, команды записаны)

## После успеха A

Аналитик может по явной команде Даниила гонять CLI на **синтетике/fixture**
и писать отчёт по `moex_analyst_bundle.v1`.  
Реальный портфель по-прежнему требует **Разрешение B**.
