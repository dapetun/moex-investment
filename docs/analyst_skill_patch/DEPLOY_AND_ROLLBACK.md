# Развёртывание и откат (кратко)

Полный воспроизводимый план: **`MINIMAL_DEPLOY.md`** + `scripts/minimal_deploy.py`.  
`SAFE_DEPLOY.md` — superseded (архив).  
Дословные патчи live: **`live_patches/`** (закрытие V8).  
Разрешения: **`permissions/PERMISSION_A.md`**, **`permissions/PERMISSION_B.md`**.

**Не копировать в рабочий профиль без Permission A.**

## Предусловия (решения владельца)

1. CLI `optimize --allow-optimize` + success + `run_id` = настоящий оптимизатор.
2. `optimizer.yaml` остаётся `enabled: false`.
3. Инициатор — только Даниил в чате Аналитика.
4. До Permission B — только синтетика / fixture.
5. PR #2 не сливать.

## Файлы к изменению при Permission A

| Файл | Патч |
|------|------|
| новый skill `cli-analyst-bundle` | копия `cli-analyst-bundle/` |
| OPT `skill-1791618014068` | `live_patches/OPT_SKILL.patch.md` |
| POS `skill-1791618006478` | `live_patches/POS_SKILL.patch.md` |
| QC `skill-1791617999761` | `live_patches/QC_SKILL.patch.md` |
| profile.json description | `live_patches/PROFILE_DESCRIPTION.patch.md` |
| analysis_spec.md (опц.) | `live_patches/SPEC_analysis_spec.patch.md` |

Базовые sha256: `live_patches/AUDIT_BASELINE.md`. Drift → стоп.

## Не менять

`optimizer.yaml`, settings/store радара, реальные portfolio/prices, PR merge.

## Rollback

См. rollback в `MINIMAL_DEPLOY.md`: файлы из `$BK`, затем platform delete
только `skill_id` этой операции (не `rm -rf`).

Частичный update уже существующего `cli-analyst-bundle` + только OPT-6/POS-4
(без description): **`ops/PARTIAL_UPDATE.md`**. Там порядок OPT → POS → skill,
precondition SHA перед каждой записью, `UNKNOWN_PENDING` и запрет слепого
повторного `UpdateSkill`. Не исполнять без отдельного разрешения владельца.
