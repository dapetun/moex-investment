# Минимальный deploy Permission A (вариант B)

**Каноническая процедура.** Старый `SAFE_DEPLOY.md` — архив (superseded), не исполнять.

Модель угроз: честные исполнители (Регулятор / Песочница) + ошибки/опечатки;  
не «произвольно скомпрометированный `.git` на box». При недоверии к среде — **стоп**.

## Инварианты

1. Один `deploy_op_id`, один tip SHA, один `$BK`.
2. Пакет кода — архив tip; хэши критических файлов из **задания** (не изнутри архива).
3. Allowlist live-файлов фиксирован; `optimizer.yaml` не меняется (`enabled: false`).
4. Create/delete skill — только штатный инструмент платформы.
5. Любой сбой → rollback файлов из `$BK` + delete только skill этой операции.
6. Синтетика only; ISS off; PR #2 не сливать.

## Роли

| Фаза | Кто | Что |
|------|-----|-----|
| A подготовка | Песочница | baseline, backup, MANIFEST_BEFORE |
| B.1 create | Регулятор | platform create → `skill_id`, `path` |
| B.2–B.8 | Песочница | path-check, skill-compare, патчи, MANIFEST_AFTER |
| rollback | оба | 10a файлы (Песочница), 10b delete (Регулятор) |

Между фазами передавать **только** зафиксированные поля:  
`deploy_op_id`, `target_sha`, `expect_hashes`, `BK`, `skill_id`, `skill_path`, baseline table.

## Доверенный пакет

1. Получить архив commit `EXPECT_HEAD` (`GIT_NO_REPLACE_OBJECTS=1 git archive EXPECT_HEAD`).
2. Распаковать в чистый каталог `PKG` (без чужого `.git`).
3. **Внешний pin** (текст задания Permission A / handoff Регулятора, не из PKG):
   `expect_head` + sha256 всех `PACKAGE_CRITICAL` (см. `tests/fixtures/minimal_deploy_external_pin.json` как образец формата).
4. Сверить `git get-tar-commit-id` архива с `expect_head`.
5. `python3 -I -B PKG/scripts/minimal_deploy.py verify-package PKG --expect-json /path/OUTSIDE/pkg/pin.json --expect-head <SHA> --archive-commit <tar-commit-id>`
   (`--expect-json` **внутри** PKG → отказ.)
6. Дальше исполнять **только** `PKG/scripts/minimal_deploy.py` (guards — ленивый compile байт после verify).

Не исполнять произвольный checkout на box. Не полагаться на `GIT_*` / hooks.

## Фаза A — подготовка

```text
active deploy ops? → стоп
cli-analyst-bundle уже есть? → стоп
sha256 live == AUDIT_BASELINE (обновлённый)? → иначе стоп
optimizer.yaml enabled: false
Аналитик/радар idle (насколько видно инструментами)
BK = /workspace/handoffs/backups/analyst-cli-<stamp>/
backup allowlist files → BK/files + BACKUP_MAP.json
MANIFEST_BEFORE (noclobber)
```

Команды: `python3 -I -B …/minimal_deploy.py phase-a --config /path/phase-a.json`  
(явные пути, без дефолтов на live). После platform create: `record_created_skill` → `skill_id.txt`/`skill_path.txt` в BK.

## Фаза B — изменение

1. Регулятор: platform create skill из `PKG/.../cli-analyst-bundle/SKILL.md`.
2. Сохранить **фактические** `skill_id` и `path` (не выводить path из id).
3. Песочница: `register_skill_path` + `compare_registered_skill`.
4. Применить утверждённые патчи OPT/POS/QC/profile/SPEC **только** в allowlist.
5. `MANIFEST_AFTER` + `verify_manifest_allowlist`.
6. sha256 `optimizer.yaml` == до apply.
7. Подтвердить доступность skill Аналитику (обновление контекста — платформа).

## Rollback

1. `restore_backup`: preflight всех членов BK → tmp+`os.replace` → сверка с `MANIFEST_BEFORE`.
2. Delete: сравнить `requested_skill_id` с `BK/skill_id.txt`; путь только из `BK/skill_path.txt`.
3. Файловый и delete-контуры независимы (оба отрабатывают с отчётом об ошибках).
4. Не `rm -rf`.

## Allowlist (логические пути)

- `…/workflows/skill-1791618014068/SKILL.md`
- `…/workflows/skill-1791618006478/SKILL.md`
- `…/workflows/skill-1791617999761/SKILL.md`
- `…/agents/<Analyst>/profile.json`
- `/workspace/invest/portfolio/analysis_spec.md`
- (+ новый `…/workflows/<created>/SKILL.md` после create)

## Что удалено относительно старого SAFE_DEPLOY

- Многошаговый bash с дублированием `validate-env` / `EXPECT_GUARDS` на каждый шаг.
- Борьба с `refs/replace`, `fsmonitor`, `core.worktree`, теневыми пакетами на «грязном» checkout.
- Pin целого `SAFE_DEPLOY.md` и whack-a-mole мутаций prose.
- Исполнение из произвольного worktree с git-hardening.

Сохранены: baseline, allowlist, path-check+symlink, skill-compare, refuse foreign delete, backup+restore, fail-closed, platform create/delete.

## Тесты

`tests/test_minimal_deploy.py` — полная последовательность на изолированном mock-box  
(те же функции, что для live; без записи в рабочий Аналитик).
