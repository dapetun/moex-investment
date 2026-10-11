# Безопасный deploy Permission A (не выполнять без подтверждения)

Пакет: `cli-analyst-bundle` + `live_patches/*` @ репо SHA, зафиксированный в задании.  
**В этой подготовке deploy не выполняется.**

## 0. Предусловия

- Permission A утверждено владельцем.
- Permission B **не** подразумевается.
- `optimizer.yaml` остаётся `enabled: false` (sha256 из AUDIT_BASELINE).
- PR #2 не сливать ради этого шага.

## 1. Проверка актуальных версий

```bash
# На box, read-only:
sha256sum \
  /home/box/agent-data/agents/5bda2f3d-a61a-48d6-8663-2441802d68de/profile.json \
  /home/box/agent-data/workflows/skill-1791618014068/SKILL.md \
  /home/box/agent-data/workflows/skill-1791618006478/SKILL.md \
  /workspace/invest/portfolio/optimizer/config/optimizer.yaml \
  /workspace/invest/portfolio/analysis_spec.md
```

Сверить с `live_patches/AUDIT_BASELINE.md`.  
Любое расхождение → **стоп**, новый аудит, патчи не применять.

## 2. Резервная копия

```bash
STAMP=$(date +%Y%m%dT%H%M%S)
BK=/tmp/analyst-cli-backup-$STAMP
mkdir -p "$BK"
cp -a /home/box/agent-data/agents/5bda2f3d-a61a-48d6-8663-2441802d68de/profile.json "$BK/"
cp -a /home/box/agent-data/workflows/skill-1791618014068/SKILL.md "$BK/OPT_SKILL.md"
cp -a /home/box/agent-data/workflows/skill-1791618006478/SKILL.md "$BK/POS_SKILL.md"
cp -a /workspace/invest/portfolio/analysis_spec.md "$BK/"
# optimizer.yaml только копировать для контроля, не менять
cp -a /workspace/invest/portfolio/optimizer/config/optimizer.yaml "$BK/"
sha256sum "$BK"/* > "$BK/SHA256SUMS"
```

## 3. Контрольные суммы до изменения

Записать в `$BK/BEFORE.txt` вывод шага 1 + `ls -la` skill-каталогов.

## 4. Применение только утверждённых изменений

Порядок:

1. Создать skill-каталог `cli-analyst-bundle` (копия из
   `docs/analyst_skill_patch/cli-analyst-bundle/` репо на **зафиксированном SHA**).
2. Применить `OPT_SKILL.patch.md` к OPT.
3. Применить `POS_SKILL.patch.md` к POS.
4. Применить `PROFILE_DESCRIPTION.patch.md` к полю `description`.
5. Применить `SPEC_analysis_spec.patch.md` (если входит в утверждённый набор A).
6. **Не** менять: `optimizer.yaml`, settings радара, `portfolio.csv`, store.db,
   news/*, handoff/* (кроме чтения).

## 5. Проверка синтаксиса / корректности

- `profile.json` — валидный JSON после правки description.
- Frontmatter OPT/POS/cli-analyst-bundle — валидный YAML.
- Имя skill в D08 совпадает с каталогом skill.
- `optimizer.yaml`: `enabled: false`, command пуст (байт-в-байт или тот же sha256).

## 6. Проверка отсутствия побочных изменений

```bash
sha256sum /workspace/invest/portfolio/optimizer/config/optimizer.yaml
# == a9f44c2606b95b42bfb70c1c9400d4e5c39c1ce83f564be5ae3ab746e9c09c83
find /workspace/invest/news /workspace/invest/handoff \
  /home/box/agent-data/agents/5bda2f3d-a61a-48d6-8663-2441802d68de \
  -newer "$BK/BEFORE_MARKER" | grep -vE 'profile.json|SKILL.md|analysis_spec|cli-analyst-bundle' || true
```

Неожиданные файлы → rollback.

## 7. One-shot на fixture (явный запрос Даниила)

В чате Аналитика, явно: CLI-анализ на fixture / синтетике, SHA репо в задании,
`MOEX_DATA_SOURCE=fixture`, `MOEX_ISS_ENABLED=false`, без user_csv.

Критерий успеха:

- цепочка exit 0; bundle `schema=moex_analyst_bundle.v1`;
- в отчёте баннер ДЕМОНСТРАЦИЯ; есть `run_id` (и `event_id` если события были);
- формат 9 разделов; yaml не включался.

## 8. Программная сверка отчёта

Сверка claims отчёта с числами bundle (как verify_report / ручная таблица
весов, Sharpe, drift). Расхождение → rollback или стоп без Permission B.

## 9. Контрольные суммы после изменения

Записать AFTER sha256 изменённых файлов + каталога cli-analyst-bundle в `$BK/AFTER.txt`.

## 10. Rollback при ошибке

```bash
cp -a "$BK/profile.json" /home/box/agent-data/agents/5bda2f3d-a61a-48d6-8663-2441802d68de/profile.json
cp -a "$BK/OPT_SKILL.md" /home/box/agent-data/workflows/skill-1791618014068/SKILL.md
cp -a "$BK/POS_SKILL.md" /home/box/agent-data/workflows/skill-1791618006478/SKILL.md
cp -a "$BK/analysis_spec.md" /workspace/invest/portfolio/analysis_spec.md
rm -rf <путь-к-cli-analyst-bundle-skill>
# optimizer.yaml не должен был меняться; при отличии — восстановить из $BK
```

Проверка отката: запрос «optimize» без явного CLI → «интеграция не настроена»;
sha256 OPT/POS/profile/yaml = BEFORE.
