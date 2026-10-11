# Развёртывание и откат skill `cli-analyst-bundle`

Рабочее место бота (не этот репозиторий): каталог skills Аналитика портфеля.

## Развёртывание (только после явного approve владельца)

1. Скопировать `cli-analyst-bundle/SKILL.md` в skills Аналитика.
2. Добавить ссылку из profile (см. `PROFILE_SNIPPET.md`) — без изменения
   `optimizer.yaml` и без включения ISS.
3. One-shot: синтетический `docs/examples/analyst_bundle_e2e_synthetic.json`
   → отчёт → сверка claims.
4. One-shot: `user_csv` dry-run из `scripts/dry_run_real_shaped_analysis.py`
   на искусственных данных той же структуры.
5. Только после успеха п.3–4 — разрешение на реальные файлы пользователя
   **вне** git и **вне** публичных handoff.

## Откат

1. Удалить/отключить skill `cli-analyst-bundle` в workspace бота.
2. Убрать строку из profile, если добавлялась.
3. `optimizer.yaml` не менялся — откат не затрагивает.
4. CLI и репозиторий `moex-investment` продолжают работать автономно.

## Что skill НЕ получает

- Право менять `optimizer.yaml`
- Право ставить cron/routines
- Право читать `/workspace/invest` портфель без явной команды пользователя
- Право слать реальные CSV в bot-handoffs / публичный git
