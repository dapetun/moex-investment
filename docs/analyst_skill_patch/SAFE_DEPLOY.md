# Безопасный deploy Permission A (не выполнять без подтверждения)

В этой подготовке deploy не выполняется: только текст процедуры и guards.
Пакет: `cli-analyst-bundle` + `live_patches/*` @ репо SHA, зафиксированный в задании.

Учёт операций и анти-параллель: `ops/DEPLOY_OPS.md`  
(уникальный `deploy_op_id`, статусы submitted→…→verified/failed/rolled_back/cancelled).
Решение владельца: `ops/DECISION_PERMISSION_A_*.md` + явная санкция на apply в задании.

Хелперы (обязательны на шагах 0/2+/4b/4c/6/10):  
`scripts/safe_deploy_guards.py` — path-check / skill-compare / canon / **validate-env** / **check-hashes**.  
Регрессия: `scripts/safe_deploy_regression.sh`, `tests/test_safe_deploy_guards.py`
(в т.ч. прогон inline-фрагментов из **этого** файла — N39).

## Модель платформы

- Create/delete — **штатный инструмент** (не `mkdir` / не `rm -rf`).
- Возвращает **`skill_id` и `path` независимо** (не выводить одно из другого;
  не предполагать `skill-<число>`).
- Библиотека skills **глобальная**; ограничение «только Аналитик» — программное.
- На box `/home/box/agent-data` — **symlink** на реальный каталог данных
  (факт pa-1405: `→ /home/box/sand-data`). Guard обязан принимать этот symlink
  и отвергать escape за пределы реального дерева данных.

## Единый корень операции (BL9)

```bash
# Задать один раз в начале deploy (после STAMP / deploy_op_id):
set -euo pipefail
STAMP=$(date +%Y%m%dT%H%M%S)
DEPLOY_OP_ID="${DEPLOY_OP_ID:?set deploy_op_id explicitly}"
DEPLOY_ROOT="/workspace/handoffs/backups/analyst-cli-${STAMP}"
mkdir -p "$DEPLOY_ROOT"
BK="$DEPLOY_ROOT"   # единственный корень: backup, MANIFEST_*, CLI_SKILL_*.txt
# Не писать манифесты в /tmp и не читать их оттуда.
```

Все последующие шаги используют **только** `$BK` (= `$DEPLOY_ROOT`).

Канонические корни путей (задаются **один раз**; каждый исполнитель получает
**полный** набор переменных явно — без наследования чужого shell):

```bash
set -euo pipefail
AGENT_DATA_LOGICAL=/home/box/agent-data
SKILL_ROOT_LOGICAL="$AGENT_DATA_LOGICAL/workflows"
AGENT_DATA_REAL=$(realpath -e "$AGENT_DATA_LOGICAL")
SKILL_ROOT_REAL=$(realpath -e "$SKILL_ROOT_LOGICAL")
AGENT="$AGENT_DATA_LOGICAL/agents/5bda2f3d-a61a-48d6-8663-2441802d68de"
WF="$SKILL_ROOT_REAL"
AGENT_REAL=$(realpath -e "$AGENT")
REPO_ROOT="<клон moex-investment @ SHA>"
# BL11: export обязателен — иначе python validate-env не видит shell-переменные
export BK DEPLOY_ROOT WF AGENT_REAL SKILL_ROOT_LOGICAL SKILL_ROOT_REAL \
  AGENT_DATA_LOGICAL AGENT_DATA_REAL REPO_ROOT DEPLOY_OP_ID
# N43/N44/N45: пустые/корневые пути + WF==SKILL_ROOT_REAL + BK==DEPLOY_ROOT + agents/
BK="$BK" DEPLOY_ROOT="$DEPLOY_ROOT" WF="$WF" AGENT_REAL="$AGENT_REAL" \
  SKILL_ROOT_LOGICAL="$SKILL_ROOT_LOGICAL" SKILL_ROOT_REAL="$SKILL_ROOT_REAL" \
  AGENT_DATA_LOGICAL="$AGENT_DATA_LOGICAL" REPO_ROOT="$REPO_ROOT" \
  python3 "$REPO_ROOT/scripts/safe_deploy_guards.py" validate-env --need-repo || exit 1
```

**BL10 + N43/N44 (обязательно):** каждый шаг ниже начинается с **inline**
`set -euo pipefail` + `${VAR:?}` + `validate-env` (не вызов shell-функции).
Пустой `WF=""` / `AGENT_REAL="/"` / рассинхрон WF≠SKILL_ROOT_REAL — отказ.

## 0. Предусловия

- Permission A утверждено владельцем (синтетика only).
- Permission B не подразумевается; PR #2 не сливать.
- `optimizer.yaml` `enabled: false` (sha256 AUDIT_BASELINE).
- Аналитик неактивен; радар в окно deploy не запускать.
- Штатный create/delete доступен.
- Одноимённый `cli-analyst-bundle` ещё не зарегистрирован — иначе **стоп**
  (не удалять чужой автоматически).
- **N39/N47 (обязательно до любого apply):** сверить pin документа:

```bash
set -euo pipefail
REPO_ROOT="${REPO_ROOT:?}"
# N47: эталон из ledger § Pin values — передавать явно каждому исполнителю (не из SD).
EXPECT_DOC="${EXPECT_DOC:?set document_sha256 from ops/ledger.md Pin values}"
EXPECT_FIX="${EXPECT_FIX:?set fixture sha256 from ops/ledger.md Pin values}"
SD="$REPO_ROOT/docs/analyst_skill_patch/SAFE_DEPLOY.md"
FIX="$REPO_ROOT/tests/fixtures/safe_deploy_block_hashes.json"
python3 "$REPO_ROOT/scripts/safe_deploy_guards.py" check-hashes "$SD" "$FIX" \
  --expect-document "$EXPECT_DOC" --expect-fixture "$EXPECT_FIX" || exit 1
# Не перегенерировать fixture во время deploy.
```

## 1. Проверка актуальных версий

```bash
sha256sum \
  "$AGENT_REAL/profile.json" \
  "$WF/skill-1791618014068/SKILL.md" \
  "$WF/skill-1791618006478/SKILL.md" \
  "$WF/skill-1791617999761/SKILL.md" \
  /workspace/invest/portfolio/optimizer/config/optimizer.yaml \
  /workspace/invest/portfolio/optimizer/run_optimizer.example.py \
  /workspace/invest/portfolio/analysis_spec.md
python3 -c "import json,hashlib,pathlib; p=pathlib.Path('$AGENT_REAL/profile.json'); d=json.loads(p.read_text())['description']; print(hashlib.sha256(d.encode()).hexdigest(), 'description')"
```

Сверить с `live_patches/AUDIT_BASELINE.md`. Drift → стоп.

## 2. Резервная копия → `$BK`

```bash
set -euo pipefail
: "${BK:?}" "${WF:?}" "${AGENT_REAL:?}" "${SKILL_ROOT_LOGICAL:?}" \
  "${AGENT_DATA_LOGICAL:?}" "${SKILL_ROOT_REAL:?}" "${DEPLOY_ROOT:?}" "${REPO_ROOT:?}"
case "$WF" in ""|"/"|"."|"..") echo "WF unsafe: <$WF>"; exit 1;; esac
case "$AGENT_REAL" in ""|"/"|"."|"..") echo "AGENT_REAL unsafe"; exit 1;; esac
case "$BK" in ""|"/"|"."|"..") echo "BK unsafe"; exit 1;; esac
case "$DEPLOY_ROOT" in ""|"/"|"."|"..") echo "DEPLOY_ROOT unsafe"; exit 1;; esac
export BK DEPLOY_ROOT WF AGENT_REAL SKILL_ROOT_LOGICAL SKILL_ROOT_REAL \
  AGENT_DATA_LOGICAL REPO_ROOT
BK="$BK" DEPLOY_ROOT="$DEPLOY_ROOT" WF="$WF" AGENT_REAL="$AGENT_REAL" \
  SKILL_ROOT_LOGICAL="$SKILL_ROOT_LOGICAL" SKILL_ROOT_REAL="$SKILL_ROOT_REAL" \
  AGENT_DATA_LOGICAL="$AGENT_DATA_LOGICAL" REPO_ROOT="$REPO_ROOT" \
  python3 "$REPO_ROOT/scripts/safe_deploy_guards.py" validate-env --need-repo || exit 1
touch "$BK/BEFORE_MARKER"
cp -a "$AGENT_REAL/profile.json" "$BK/"
cp -a "$WF/skill-1791618014068/SKILL.md" "$BK/OPT_SKILL.md"
cp -a "$WF/skill-1791618006478/SKILL.md" "$BK/POS_SKILL.md"
cp -a "$WF/skill-1791617999761/SKILL.md" "$BK/QC_SKILL.md"
cp -a /workspace/invest/portfolio/analysis_spec.md "$BK/"
cp -a /workspace/invest/portfolio/optimizer/config/optimizer.yaml "$BK/"
cp -a /workspace/invest/portfolio/optimizer/run_optimizer.example.py "$BK/"
sha256sum "$BK"/* > "$BK/SHA256SUMS" || exit 1
test -s "$BK/SHA256SUMS" || { echo "empty SHA256SUMS"; exit 1; }
```

## 3. MANIFEST_BEFORE (только realpath-пути)

До create skill. Писать **один раз** в `$BK` (`noclobber`).

```bash
set -euo pipefail
: "${BK:?}" "${WF:?}" "${AGENT_REAL:?}" "${SKILL_ROOT_LOGICAL:?}" \
  "${AGENT_DATA_LOGICAL:?}" "${SKILL_ROOT_REAL:?}" "${DEPLOY_ROOT:?}" "${REPO_ROOT:?}"
case "$WF" in ""|"/"|"."|"..") echo "WF unsafe: <$WF>"; exit 1;; esac
case "$AGENT_REAL" in ""|"/"|"."|"..") echo "AGENT_REAL unsafe"; exit 1;; esac
case "$BK" in ""|"/"|"."|"..") echo "BK unsafe"; exit 1;; esac
export BK DEPLOY_ROOT WF AGENT_REAL SKILL_ROOT_LOGICAL SKILL_ROOT_REAL \
  AGENT_DATA_LOGICAL REPO_ROOT
BK="$BK" DEPLOY_ROOT="$DEPLOY_ROOT" WF="$WF" AGENT_REAL="$AGENT_REAL" \
  SKILL_ROOT_LOGICAL="$SKILL_ROOT_LOGICAL" SKILL_ROOT_REAL="$SKILL_ROOT_REAL" \
  AGENT_DATA_LOGICAL="$AGENT_DATA_LOGICAL" REPO_ROOT="$REPO_ROOT" \
  python3 "$REPO_ROOT/scripts/safe_deploy_guards.py" validate-env --need-repo || exit 1
set -o noclobber
(
  find "$WF" "$AGENT_REAL" -type f \
    ! -name 'store.db' ! -name 'store.db-wal' ! -name 'store.db-shm' \
    | sort | while read -r f; do sha256sum "$(realpath -e "$f")"; done
  find /workspace/invest/portfolio/optimizer /workspace/invest/config \
       /workspace/invest/schemas /workspace/invest/handoff \
       -type f 2>/dev/null | sort | while read -r f; do sha256sum "$(realpath -e "$f")"; done
  find /workspace/invest/portfolio -maxdepth 1 -type f 2>/dev/null \
    | sort | while read -r f; do sha256sum "$(realpath -e "$f")"; done
  sha256sum "$(realpath -e /workspace/invest/news/events_latest.json)" \
    "$(realpath -e /workspace/invest/portfolio/optimizer/config/optimizer.yaml)"
) > "$BK/MANIFEST_BEFORE.txt" || { echo "MANIFEST_BEFORE write failed"; exit 1; }
set +o noclobber
test -s "$BK/MANIFEST_BEFORE.txt" || { echo "MANIFEST_BEFORE empty"; exit 1; }
# не grep -F "/" при пустом WF — case выше уже стоп; плюс явная длина префикса
test "${#WF}" -ge 8 && test "${#AGENT_REAL}" -ge 8 \
  || { echo "WF/AGENT_REAL too short"; exit 1; }
grep -F -- "$WF/" "$BK/MANIFEST_BEFORE.txt" >/dev/null \
  || { echo "MANIFEST_BEFORE missing WF entries"; exit 1; }
grep -F -- "$AGENT_REAL/" "$BK/MANIFEST_BEFORE.txt" >/dev/null \
  || { echo "MANIFEST_BEFORE missing AGENT_REAL entries"; exit 1; }
```

Записать в `$BK/BEFORE.txt` шаг 1 + список skills платформы.

## 4. Регистрация skill + патчи

### 4a. Create

1. `printf '%s\n' 'cli-analyst-bundle' > "$BK/CLI_SKILL_NAME.txt"`
2. Штатный create из `docs/analyst_skill_patch/cli-analyst-bundle/` @ SHA.
3. Сохранить независимо:
   - `$BK/CLI_SKILL_ID.txt`
   - `$BK/CLI_SKILL_PATH.txt` (как вернула платформа; может быть logical path)
4. Пустые/неполные ID/path → стоп; частичные записи → 10b `exit 2`.

### 4b. Path guard (fail-closed; BL7+BL8)

```bash
set -euo pipefail
: "${BK:?}" "${WF:?}" "${AGENT_REAL:?}" "${SKILL_ROOT_LOGICAL:?}" \
  "${AGENT_DATA_LOGICAL:?}" "${SKILL_ROOT_REAL:?}" "${DEPLOY_ROOT:?}" "${REPO_ROOT:?}"
case "$WF" in ""|"/"|"."|"..") echo "WF unsafe"; exit 1;; esac
case "$AGENT_REAL" in ""|"/"|"."|"..") echo "AGENT_REAL unsafe"; exit 1;; esac
export BK DEPLOY_ROOT WF AGENT_REAL SKILL_ROOT_LOGICAL SKILL_ROOT_REAL \
  AGENT_DATA_LOGICAL REPO_ROOT
BK="$BK" DEPLOY_ROOT="$DEPLOY_ROOT" WF="$WF" AGENT_REAL="$AGENT_REAL" \
  SKILL_ROOT_LOGICAL="$SKILL_ROOT_LOGICAL" SKILL_ROOT_REAL="$SKILL_ROOT_REAL" \
  AGENT_DATA_LOGICAL="$AGENT_DATA_LOGICAL" REPO_ROOT="$REPO_ROOT" \
  python3 "$REPO_ROOT/scripts/safe_deploy_guards.py" validate-env --need-repo || exit 1
CLI_ID=$(cat "$BK/CLI_SKILL_ID.txt")
CLI_PATH_RAW=$(cat "$BK/CLI_SKILL_PATH.txt")
test -n "$CLI_ID" && test -n "$CLI_PATH_RAW" || { echo "empty id/path"; exit 1; }

# BL8: любой ненулевой python → exit 1; «4b ok» только после успеха
# N34: path-check требует существования пути (strict)
python3 "$REPO_ROOT/scripts/safe_deploy_guards.py" path-check \
  "$CLI_PATH_RAW" "$SKILL_ROOT_LOGICAL" "$AGENT_DATA_LOGICAL" \
  > "$BK/CLI_SKILL_PATH_REAL.txt" || exit 1
CLI_PATH=$(cat "$BK/CLI_SKILL_PATH_REAL.txt")
test -d "$CLI_PATH" || { echo "CLI_PATH not a directory"; exit 1; }

# existed before — Path-сравнение (N37/N40), не prefix-grep по строке
BK="$BK" CLI_PATH="$CLI_PATH" REPO_ROOT="$REPO_ROOT" python3 - <<'PY' || exit 1
import os, pathlib, sys
sys.path.insert(0, os.path.join(os.environ["REPO_ROOT"], "scripts"))
import safe_deploy_guards as g
cli = pathlib.Path(g.canonicalize_path(os.environ["CLI_PATH"]))
before = g.load_manifest(pathlib.Path(os.environ["BK"]) / "MANIFEST_BEFORE.txt")
for p in before:
    pp = pathlib.Path(p)
    if pp == cli or cli in pp.parents:
        raise SystemExit("path existed before deploy")
print("not in MANIFEST_BEFORE")
PY
for known in skill-1791618014068 skill-1791618006478 skill-1791617999761 \
             skill-1791617992518 skill-1791617966204 skill-1791617976741; do
  KNOWN_REAL=$(realpath -e "$WF/$known" 2>/dev/null || true)
  if [ -n "$KNOWN_REAL" ] && [ "$CLI_PATH" = "$KNOWN_REAL" ]; then
    echo "collides with existing $known"; exit 1
  fi
done
# get платформы: ID и path согласованы с $BK (не выводить path из id)
echo "4b ok"
```

Отказ 4b → **не** патчить live; только **10b**, затем стоп.

### 4c. Содержимое skill (не побайт всего файла)

Платформа нормализует YAML frontmatter (`>`→`>-`, wrap).  
Критерий: **`name` + тело после frontmatter** (байт-в-байт) +  
`description` после нормализации пробелов. Иначе 10b, стоп.

```bash
set -euo pipefail
: "${BK:?}" "${WF:?}" "${AGENT_REAL:?}" "${SKILL_ROOT_LOGICAL:?}" \
  "${AGENT_DATA_LOGICAL:?}" "${SKILL_ROOT_REAL:?}" "${DEPLOY_ROOT:?}" \
  "${REPO_ROOT:?}" "${CLI_PATH:?}"
case "$AGENT_REAL" in ""|"/"|"."|"..") echo "AGENT_REAL unsafe"; exit 1;; esac
export BK DEPLOY_ROOT WF AGENT_REAL SKILL_ROOT_LOGICAL SKILL_ROOT_REAL \
  AGENT_DATA_LOGICAL REPO_ROOT CLI_PATH
BK="$BK" DEPLOY_ROOT="$DEPLOY_ROOT" WF="$WF" AGENT_REAL="$AGENT_REAL" \
  SKILL_ROOT_LOGICAL="$SKILL_ROOT_LOGICAL" SKILL_ROOT_REAL="$SKILL_ROOT_REAL" \
  AGENT_DATA_LOGICAL="$AGENT_DATA_LOGICAL" REPO_ROOT="$REPO_ROOT" \
  python3 "$REPO_ROOT/scripts/safe_deploy_guards.py" validate-env --need-repo || exit 1
test -d "$CLI_PATH" || exit 1
REPO_SKILL="$REPO_ROOT/docs/analyst_skill_patch/cli-analyst-bundle/SKILL.md"
LIVE_SKILL="$CLI_PATH/SKILL.md"
test -f "$LIVE_SKILL" || { echo "live SKILL.md missing"; exit 1; }
python3 "$REPO_ROOT/scripts/safe_deploy_guards.py" skill-compare \
  "$REPO_SKILL" "$LIVE_SKILL" || exit 1
```

### 4d. Live-патчи

Только после 4b+4c: OPT → POS → QC → PROFILE → SPEC.  
Не менять yaml / radar settings / portfolio.csv / store / news / handoff.  
Ошибка mid-patch → **10a затем 10b**.

## 5. Синтаксис

- `profile.json` валидный JSON; frontmatter YAML валиден.
- Имя D08 / frontmatter / `$BK/CLI_SKILL_NAME.txt` = `cli-analyst-bundle`.
- get(ID) согласован с path; yaml `enabled: false`, тот же sha256.

## 6. MANIFEST_AFTER

```bash
set -euo pipefail
: "${BK:?}" "${WF:?}" "${AGENT_REAL:?}" "${SKILL_ROOT_LOGICAL:?}" \
  "${AGENT_DATA_LOGICAL:?}" "${SKILL_ROOT_REAL:?}" "${DEPLOY_ROOT:?}" "${REPO_ROOT:?}"
case "$WF" in ""|"/"|"."|"..") echo "WF unsafe"; exit 1;; esac
case "$AGENT_REAL" in ""|"/"|"."|"..") echo "AGENT_REAL unsafe"; exit 1;; esac
export BK DEPLOY_ROOT WF AGENT_REAL SKILL_ROOT_LOGICAL SKILL_ROOT_REAL \
  AGENT_DATA_LOGICAL REPO_ROOT
BK="$BK" DEPLOY_ROOT="$DEPLOY_ROOT" WF="$WF" AGENT_REAL="$AGENT_REAL" \
  SKILL_ROOT_LOGICAL="$SKILL_ROOT_LOGICAL" SKILL_ROOT_REAL="$SKILL_ROOT_REAL" \
  AGENT_DATA_LOGICAL="$AGENT_DATA_LOGICAL" REPO_ROOT="$REPO_ROOT" \
  python3 "$REPO_ROOT/scripts/safe_deploy_guards.py" validate-env --need-repo || exit 1
test -f "$BK/MANIFEST_BEFORE.txt" || { echo "MANIFEST_BEFORE missing"; exit 1; }
CLI_PATH=$(cat "$BK/CLI_SKILL_PATH_REAL.txt")
test -n "$CLI_PATH" || exit 1

(
  find "$WF" "$AGENT_REAL" -type f \
    ! -name 'store.db' ! -name 'store.db-wal' ! -name 'store.db-shm' \
    | sort | while read -r f; do sha256sum "$(realpath -e "$f")"; done
  find /workspace/invest/portfolio/optimizer /workspace/invest/config \
       /workspace/invest/schemas /workspace/invest/handoff \
       -type f 2>/dev/null | sort | while read -r f; do sha256sum "$(realpath -e "$f")"; done
  find /workspace/invest/portfolio -maxdepth 1 -type f 2>/dev/null \
    | sort | while read -r f; do sha256sum "$(realpath -e "$f")"; done
  sha256sum "$(realpath -e /workspace/invest/news/events_latest.json)" \
    "$(realpath -e /workspace/invest/portfolio/optimizer/config/optimizer.yaml)"
) > "$BK/MANIFEST_AFTER.txt" || exit 1

BK="$BK" CLI_PATH="$CLI_PATH" REPO_ROOT="$REPO_ROOT" python3 - <<'PY' || exit 1
import os, pathlib, sys
sys.path.insert(0, os.path.join(os.environ["REPO_ROOT"], "scripts"))
import safe_deploy_guards as g
bk = pathlib.Path(os.environ["BK"])
cli = pathlib.Path(os.environ["CLI_PATH"]).resolve()
# allow-list через canonicalize (учитывает symlink agent-data):
allowed_exact = {
    g.canonicalize_path("/home/box/agent-data/agents/5bda2f3d-a61a-48d6-8663-2441802d68de/profile.json"),
    g.canonicalize_path("/home/box/agent-data/workflows/skill-1791618014068/SKILL.md"),
    g.canonicalize_path("/home/box/agent-data/workflows/skill-1791618006478/SKILL.md"),
    g.canonicalize_path("/home/box/agent-data/workflows/skill-1791617999761/SKILL.md"),
    g.canonicalize_path("/workspace/invest/portfolio/analysis_spec.md"),
}
before, after = g.load_manifest(bk/"MANIFEST_BEFORE.txt"), g.load_manifest(bk/"MANIFEST_AFTER.txt")
bad = []
for f, h in after.items():
    fp = pathlib.Path(f)
    if fp == cli or cli in fp.parents:
        continue
    if f in allowed_exact:
        continue
    if before.get(f) != h:
        bad.append(("changed_or_new", f, before.get(f), h))
for f in before:
    fp = pathlib.Path(f)
    if f not in after and not (fp == cli or cli in fp.parents):
        if f not in allowed_exact:
            bad.append(("missing", f, before[f], None))
if bad:
    print("UNEXPECTED:")
    for row in bad:
        print(row)
    sys.exit(1)
print("manifest ok")
PY
```

Unexpected → rollback 10a+10b.

## 7–9. One-shot / dry-run / AFTER

Без изменений по смыслу (fixture only; явный Даниил; yaml не включать).  
`$BK/AFTER.txt` — sha256 изменённых файлов + skill + ID/path.

## 10. Rollback

Сначала **10a**, затем **10b**. Тот же `$BK` / `$DEPLOY_ROOT`.

### 10a. Файлы

```bash
set -euo pipefail
: "${BK:?}" "${WF:?}" "${AGENT_REAL:?}" "${SKILL_ROOT_LOGICAL:?}" \
  "${AGENT_DATA_LOGICAL:?}" "${SKILL_ROOT_REAL:?}" "${DEPLOY_ROOT:?}" "${REPO_ROOT:?}"
case "$WF" in ""|"/"|"."|"..") echo "WF unsafe"; exit 1;; esac
case "$AGENT_REAL" in ""|"/"|"."|"..") echo "AGENT_REAL unsafe"; exit 1;; esac
case "$BK" in ""|"/"|"."|"..") echo "BK unsafe"; exit 1;; esac
export BK DEPLOY_ROOT WF AGENT_REAL SKILL_ROOT_LOGICAL SKILL_ROOT_REAL \
  AGENT_DATA_LOGICAL REPO_ROOT
BK="$BK" DEPLOY_ROOT="$DEPLOY_ROOT" WF="$WF" AGENT_REAL="$AGENT_REAL" \
  SKILL_ROOT_LOGICAL="$SKILL_ROOT_LOGICAL" SKILL_ROOT_REAL="$SKILL_ROOT_REAL" \
  AGENT_DATA_LOGICAL="$AGENT_DATA_LOGICAL" REPO_ROOT="$REPO_ROOT" \
  python3 "$REPO_ROOT/scripts/safe_deploy_guards.py" validate-env --need-repo || exit 1
cp -a "$BK/profile.json" "$AGENT_REAL/profile.json"
cp -a "$BK/OPT_SKILL.md" "$WF/skill-1791618014068/SKILL.md"
cp -a "$BK/POS_SKILL.md" "$WF/skill-1791618006478/SKILL.md"
cp -a "$BK/QC_SKILL.md" "$WF/skill-1791617999761/SKILL.md"
cp -a "$BK/analysis_spec.md" /workspace/invest/portfolio/analysis_spec.md
test "$(sha256sum "$(realpath -e /workspace/invest/portfolio/optimizer/config/optimizer.yaml)" | awk '{print $1}')" \
  = "a9f44c2606b95b42bfb70c1c9400d4e5c39c1ce83f564be5ae3ab746e9c09c83" \
  || cp -a "$BK/optimizer.yaml" /workspace/invest/portfolio/optimizer/config/optimizer.yaml
```

### 10b. Skill delete (платформа; тот же path guard)

```bash
set -euo pipefail
: "${BK:?}" "${WF:?}" "${AGENT_REAL:?}" "${SKILL_ROOT_LOGICAL:?}" \
  "${AGENT_DATA_LOGICAL:?}" "${SKILL_ROOT_REAL:?}" "${DEPLOY_ROOT:?}" "${REPO_ROOT:?}"
case "$WF" in ""|"/"|"."|"..") echo "WF unsafe"; exit 1;; esac
case "$AGENT_REAL" in ""|"/"|"."|"..") echo "AGENT_REAL unsafe"; exit 1;; esac
export BK DEPLOY_ROOT WF AGENT_REAL SKILL_ROOT_LOGICAL SKILL_ROOT_REAL \
  AGENT_DATA_LOGICAL REPO_ROOT
BK="$BK" DEPLOY_ROOT="$DEPLOY_ROOT" WF="$WF" AGENT_REAL="$AGENT_REAL" \
  SKILL_ROOT_LOGICAL="$SKILL_ROOT_LOGICAL" SKILL_ROOT_REAL="$SKILL_ROOT_REAL" \
  AGENT_DATA_LOGICAL="$AGENT_DATA_LOGICAL" REPO_ROOT="$REPO_ROOT" \
  python3 "$REPO_ROOT/scripts/safe_deploy_guards.py" validate-env --need-repo || exit 2
if [ ! -f "$BK/CLI_SKILL_ID.txt" ] && [ ! -f "$BK/CLI_SKILL_PATH.txt" ]; then
  echo "no create record — skip skill delete"; exit 0
fi
if [ ! -s "$BK/CLI_SKILL_ID.txt" ] || [ ! -s "$BK/CLI_SKILL_PATH.txt" ] \
   || [ ! -s "$BK/CLI_SKILL_NAME.txt" ]; then
  echo "incomplete create record"; exit 2
fi
CLI_ID=$(cat "$BK/CLI_SKILL_ID.txt")
CLI_PATH_RAW=$(cat "$BK/CLI_SKILL_PATH.txt")
CLI_PATH=$(python3 "$REPO_ROOT/scripts/safe_deploy_guards.py" path-check \
  "$CLI_PATH_RAW" "$SKILL_ROOT_LOGICAL" "$AGENT_DATA_LOGICAL") || exit 2
# N36: path не в MANIFEST_BEFORE (Path-сравнение)
BK="$BK" CLI_PATH="$CLI_PATH" REPO_ROOT="$REPO_ROOT" python3 - <<'PY' || exit 2
import os, pathlib, sys
sys.path.insert(0, os.path.join(os.environ["REPO_ROOT"], "scripts"))
import safe_deploy_guards as g
cli = pathlib.Path(g.canonicalize_path(os.environ["CLI_PATH"]))
before = g.load_manifest(pathlib.Path(os.environ["BK"]) / "MANIFEST_BEFORE.txt")
for p in before:
    pp = pathlib.Path(p)
    if pp == cli or cli in pp.parents:
        raise SystemExit("10b: path existed before deploy — refuse delete")
print("10b path not in MANIFEST_BEFORE")
PY
# get(ID): name==cli-analyst-bundle, path совпадает с CLI_PATH
# только тогда: штатный delete(skill_id=CLI_ID)
# mismatch → не удалять, exit 2
# N42: если skill уже удалён — path-check выше даст rc≠0 (fail-closed)
```

Запрещено: `rm -rf`; delete по одному path; удаление pre-existing одноимённого skill.
