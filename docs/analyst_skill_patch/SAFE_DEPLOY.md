# Безопасный deploy Permission A (не выполнять без подтверждения)

Пакет: `cli-analyst-bundle` + `live_patches/*` @ репо SHA, зафиксированный в задании.  
**В этой подготовке deploy не выполняется.**

Учёт операций и анти-параллель: `ops/DEPLOY_OPS.md`  
(уникальный `deploy_op_id`, статусы submitted→…→verified/failed/rolled_back/cancelled;
не слать второй apply, пока предыдущий op не cancelled/failed/rolled_back/verified).
Решение владельца для SHA: `ops/DECISION_PERMISSION_A_*.md`.

## Модель платформы (исходные данные владельца)

- Новый skill создаётся и удаляется **штатным инструментом платформы**
  (не `mkdir` / не `rm -rf` вручную).
- Инструмент возвращает **`skill_id` и `path` независимо** — не выводить
  одно из другого и не предполагать форму `skill-<число>`.
- Библиотека skills **глобальная** для всех ботов; отдельной серверной
  привязки skill→агент нет. Ограничение «только Аналитик» — программное
  (текст skill + патчи), не серверная изоляция.
- Разрешённый корень путей на box:  
  `SKILL_ROOT=/home/box/agent-data/workflows`  
  (realpath пути skill должен оставаться внутри этого корня).

## 0. Предусловия

- Permission A утверждено владельцем (условное — только синтетика).
- Permission B **не** подразумевается.
- `optimizer.yaml` остаётся `enabled: false` (sha256 из AUDIT_BASELINE).
- PR #2 не сливать ради этого шага.
- Аналитик **неактивен** на всё время deploy (нет активного анализа;
  иначе store.db* / settings шумят; store.* из манифеста исключены,
  но settings.json агента — нет). Радар в окно deploy не запускать (N26).
- Штатный create/delete skill доступен исполнителю deploy.
- Одноимённый skill `cli-analyst-bundle` **ещё не зарегистрирован**
  (проверка списком платформы). Если уже есть — **стоп**, не удалять
  чужой/старый одноимённый skill автоматически.

## 1. Проверка актуальных версий

```bash
# На box, read-only:
AGENT=/home/box/agent-data/agents/5bda2f3d-a61a-48d6-8663-2441802d68de
WF=/home/box/agent-data/workflows
sha256sum \
  "$AGENT/profile.json" \
  "$WF/skill-1791618014068/SKILL.md" \
  "$WF/skill-1791618006478/SKILL.md" \
  "$WF/skill-1791617999761/SKILL.md" \
  /workspace/invest/portfolio/optimizer/config/optimizer.yaml \
  /workspace/invest/portfolio/optimizer/run_optimizer.example.py \
  /workspace/invest/portfolio/analysis_spec.md
python3 -c "import json,hashlib,pathlib; p=pathlib.Path('$AGENT/profile.json'); d=json.loads(p.read_text())['description']; print(hashlib.sha256(d.encode()).hexdigest(), 'description')"
```

Сверить с `live_patches/AUDIT_BASELINE.md`.  
Любое расхождение → **стоп**, новый аудит, патчи не применять.

Дополнительно (платформа, read-only): список skills — нет записи
`name=cli-analyst-bundle`. Есть → **стоп**.

## 2. Резервная копия (только live-инструкции)

Независимый откат файлов OPT/POS/QC/profile/SPEC (и контроль yaml).  
Регистрация skill откатывается отдельно шагом 10b.

```bash
STAMP=$(date +%Y%m%dT%H%M%S)
BK=/tmp/analyst-cli-backup-$STAMP
mkdir -p "$BK" /workspace/handoffs/backups
touch "$BK/BEFORE_MARKER"
cp -a /home/box/agent-data/agents/5bda2f3d-a61a-48d6-8663-2441802d68de/profile.json "$BK/"
cp -a /home/box/agent-data/workflows/skill-1791618014068/SKILL.md "$BK/OPT_SKILL.md"
cp -a /home/box/agent-data/workflows/skill-1791618006478/SKILL.md "$BK/POS_SKILL.md"
cp -a /home/box/agent-data/workflows/skill-1791617999761/SKILL.md "$BK/QC_SKILL.md"
cp -a /workspace/invest/portfolio/analysis_spec.md "$BK/"
cp -a /workspace/invest/portfolio/optimizer/config/optimizer.yaml "$BK/"
cp -a /workspace/invest/portfolio/optimizer/run_optimizer.example.py "$BK/"
sha256sum "$BK"/* > "$BK/SHA256SUMS"
cp -a "$BK" "/workspace/handoffs/backups/analyst-cli-$STAMP/"
```

## 3. MANIFEST_BEFORE (до создания skill и до любых правок)

Снимок **до** регистрации skill: новый skill не должен числиться в BEFORE
(иначе guard «existed before» / allow-list сломаются).

```bash
AGENT=/home/box/agent-data/agents/5bda2f3d-a61a-48d6-8663-2441802d68de
WF=/home/box/agent-data/workflows
set -o noclobber
(
  find "$WF" "$AGENT" -type f \
    ! -name 'store.db' ! -name 'store.db-wal' ! -name 'store.db-shm' \
    | sort | xargs -r sha256sum
  find /workspace/invest/portfolio/optimizer /workspace/invest/config \
       /workspace/invest/schemas /workspace/invest/handoff \
       -type f 2>/dev/null | sort | xargs -r sha256sum
  find /workspace/invest/portfolio -maxdepth 1 -type f 2>/dev/null | sort | xargs -r sha256sum
  sha256sum /workspace/invest/news/events_latest.json \
    /workspace/invest/portfolio/optimizer/config/optimizer.yaml
) > "$BK/MANIFEST_BEFORE.txt" || { echo "MANIFEST_BEFORE write failed (exists?)"; exit 1; }
set +o noclobber
```

Записать в `$BK/BEFORE.txt` вывод шага 1 + снимок списка skills платформы.

## 4. Регистрация skill + применение патчей

### 4a. Создать skill штатным инструментом

1. **До** create записать ожидаемое имя (N29):
   `printf '%s\n' 'cli-analyst-bundle' > "$BK/CLI_SKILL_NAME.txt"`
2. Вызвать **create** платформы с именем `cli-analyst-bundle`
   и содержимым `docs/analyst_skill_patch/cli-analyst-bundle/` @ зафиксированном SHA.
3. Сохранить возвращённые поля **независимо** (не выводить одно из другого):
   - `$BK/CLI_SKILL_ID.txt` — ID как вернула платформа;
   - `$BK/CLI_SKILL_PATH.txt` — path как вернула платформа.
4. Если create ошибся или ID/path пусты: **не** писать частичные ID/path
   (или удалить неполные); **стоп**; 10a не нужен. Если после сбоя
   остались частичные записи ID/path — см. 10b (`exit 2`).

### 4b. Проверка path (без rm)

```bash
SKILL_ROOT=/home/box/agent-data/workflows
CLI_ID=$(cat "$BK/CLI_SKILL_ID.txt")
CLI_PATH_RAW=$(cat "$BK/CLI_SKILL_PATH.txt")
CLI_PATH=$(realpath -e "$CLI_PATH_RAW") || { echo "path missing or broken"; exit 1; }
ROOT_REAL=$(realpath -e "$SKILL_ROOT")
# path traversal / escape: realpath должен остаться под SKILL_ROOT/
case "$CLI_PATH" in
  "$ROOT_REAL"/*) ;;
  *) echo "path outside SKILL_ROOT: $CLI_PATH"; exit 1 ;;
esac
# отказ, если промежуточный symlink уводит за пределы корня
export ROOT_REAL CLI_PATH_RAW CLI_PATH
python3 - <<'PY'
import os, pathlib, sys
root = pathlib.Path(os.environ["ROOT_REAL"]).resolve()
raw = pathlib.Path(os.environ["CLI_PATH_RAW"])
cli = pathlib.Path(os.environ["CLI_PATH"]).resolve()
if root not in cli.parents and cli != root:
    print("resolved path outside root", cli); sys.exit(1)
cur = pathlib.Path("/")
for part in raw.parts[1:]:
    cur = cur / part
    if cur.is_symlink():
        tgt = cur.resolve()
        if root not in tgt.parents and tgt != root:
            print("symlink escape at", cur, "->", tgt)
            sys.exit(1)
print("path ok", cli)
PY
# не было в BEFORE (BL6: if/then, не grep&&exit — иначе rc=1 на успехе)
if grep -Fq " $CLI_PATH/" "$BK/MANIFEST_BEFORE.txt" \
   || grep -Eq " ${CLI_PATH}$" "$BK/MANIFEST_BEFORE.txt"; then
  echo "path existed before deploy"; exit 1
fi
# не известные skills Аналитика/радара
for known in skill-1791618014068 skill-1791618006478 skill-1791617999761 \
             skill-1791617992518 skill-1791617966204 skill-1791617976741; do
  if [ "$CLI_PATH" = "$ROOT_REAL/$known" ]; then
    echo "collides with existing $known"; exit 1
  fi
done
# имя в реестре = cli-analyst-bundle; ID совпадает с сохранённым
# (через штатный list/get платформы — не выдумывать из path)
echo "4b ok"
```

Любой отказ 4b → **не** править OPT/POS/QC/profile/SPEC; выполнить
только **10b** (удаление только что созданного skill по ID), затем стоп.

### 4c. Содержимое skill

Убедиться, что зарегистрированный skill содержит утверждённый `SKILL.md`
(sha256 или байт-сравнение с репо @ SHA). Расхождение → 10b, стоп.

### 4d. Live-патчи (только после успешного 4b–4c)

Порядок: OPT → POS → QC → PROFILE description → SPEC (если в наборе A).  
Дословные OLD/NEW из `live_patches/*`.  
**Не** менять: `optimizer.yaml`, settings радара, `portfolio.csv`, store.db,
news/*, handoff/* (кроме чтения).

Ошибка mid-patch → **стоп**, выполнить **10a затем 10b** (файлы, потом skill).

## 5. Проверка синтаксиса / корректности

- `profile.json` — валидный JSON после правки description.
- Frontmatter OPT/POS/cli-analyst-bundle — валидный YAML.
- Имя в D08 / frontmatter / `$BK/CLI_SKILL_NAME.txt` = `cli-analyst-bundle`.
- ID и path в `$BK` совпадают с ответом `get` платформы.
- `optimizer.yaml`: `enabled: false`, command пуст (тот же sha256).

## 6. MANIFEST_AFTER

Только после шага 5. `MANIFEST_BEFORE.txt` не перезаписывать.

```bash
AGENT=/home/box/agent-data/agents/5bda2f3d-a61a-48d6-8663-2441802d68de
WF=/home/box/agent-data/workflows
test -f "$BK/MANIFEST_BEFORE.txt" || { echo "MANIFEST_BEFORE missing"; exit 1; }
CLI_PATH=$(realpath -e "$(cat "$BK/CLI_SKILL_PATH.txt")") || exit 1
CLI_ID=$(cat "$BK/CLI_SKILL_ID.txt")

(
  find "$WF" "$AGENT" -type f \
    ! -name 'store.db' ! -name 'store.db-wal' ! -name 'store.db-shm' \
    | sort | xargs -r sha256sum
  find /workspace/invest/portfolio/optimizer /workspace/invest/config \
       /workspace/invest/schemas /workspace/invest/handoff \
       -type f 2>/dev/null | sort | xargs -r sha256sum
  find /workspace/invest/portfolio -maxdepth 1 -type f 2>/dev/null | sort | xargs -r sha256sum
  sha256sum /workspace/invest/news/events_latest.json \
    /workspace/invest/portfolio/optimizer/config/optimizer.yaml
) > "$BK/MANIFEST_AFTER.txt"

BK="$BK" CLI_PATH="$CLI_PATH" python3 - <<'PY'
import os, pathlib, sys
bk = pathlib.Path(os.environ["BK"])
cli = pathlib.Path(os.environ["CLI_PATH"]).resolve()
allowed_exact = {
    "/home/box/agent-data/agents/5bda2f3d-a61a-48d6-8663-2441802d68de/profile.json",
    "/home/box/agent-data/workflows/skill-1791618014068/SKILL.md",
    "/home/box/agent-data/workflows/skill-1791618006478/SKILL.md",
    "/home/box/agent-data/workflows/skill-1791617999761/SKILL.md",
    "/workspace/invest/portfolio/analysis_spec.md",
}
def load(p):
    d = {}
    for i, line in enumerate(p.read_text().splitlines(), 1):
        parts = line.split(None, 1)
        if len(parts) != 2 or len(parts[0]) != 64:
            print(f"bad manifest line {i}: {line!r}")
            sys.exit(1)
        d[parts[1]] = parts[0]
    return d
before, after = load(bk/"MANIFEST_BEFORE.txt"), load(bk/"MANIFEST_AFTER.txt")
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

Любое unexpected → rollback **10a + 10b**.

В манифесте (не в allow-list): `events_latest.json`, skills радара,
`invest/config/**`, `schemas/**`, `handoff/**`, `portfolio/optimizer/**`.  
Не в манифесте (штатный шум): `news/digest*`, `news/events_history.jsonl`,
`logs/`, `portfolio/reports/`.

## 7. One-shot на fixture (явный запрос Даниила)

В чате Аналитика, явно: CLI-анализ на fixture / синтетике, SHA репо в задании,
`MOEX_DATA_SOURCE=fixture`, `MOEX_ISS_ENABLED=false`, без user_csv.
Handoff / радар / другой бот **не** заменяют инициатора.

Критерий успеха:

- цепочка exit 0; bundle `schema=moex_analyst_bundle.v1`;
- в отчёте баннер ДЕМОНСТРАЦИЯ; есть `run_id` (и `event_id` если события были);
- формат 9 разделов; yaml не включался;
- запись в portfolio/reports и logs по правилам профиля.

## 7b. Dry-run формы user_csv (между A и B, ещё не Permission B)

```bash
MOEX_ISS_ENABLED=false python scripts/dry_run_real_shaped_analysis.py
```

Критерий: exit 0, все шаги ok, пути без абсолютных home.  
Боевые portfolio/prices не используются.

## 8. Программная сверка отчёта

Сверка claims отчёта с числами bundle. Расхождение → rollback или стоп
без Permission B.

## 9. Контрольные суммы после изменения

Записать AFTER sha256 изменённых файлов + содержимого skill +  
`CLI_SKILL_ID` / path в `$BK/AFTER.txt`.

## 10. Rollback (два независимых контура)

При любой критической ошибке после начала изменений: **сначала 10a, затем 10b**.  
Частичный сбой документировать: какие контуры уже откатили, что осталось.

### 10a. Восстановление live-инструкций

```bash
AGENT=/home/box/agent-data/agents/5bda2f3d-a61a-48d6-8663-2441802d68de
WF=/home/box/agent-data/workflows
cp -a "$BK/profile.json" "$AGENT/profile.json"
cp -a "$BK/OPT_SKILL.md" "$WF/skill-1791618014068/SKILL.md"
cp -a "$BK/POS_SKILL.md" "$WF/skill-1791618006478/SKILL.md"
cp -a "$BK/QC_SKILL.md" "$WF/skill-1791617999761/SKILL.md"
cp -a "$BK/analysis_spec.md" /workspace/invest/portfolio/analysis_spec.md
test "$(sha256sum /workspace/invest/portfolio/optimizer/config/optimizer.yaml | awk '{print $1}')" \
  = "a9f44c2606b95b42bfb70c1c9400d4e5c39c1ce83f564be5ae3ab746e9c09c83" \
  || cp -a "$BK/optimizer.yaml" /workspace/invest/portfolio/optimizer/config/optimizer.yaml
```

Проверка: sha256 OPT/POS/QC/profile/yaml = BEFORE; «optimize» без явного CLI
→ «интеграция не настроена».

### 10b. Снятие регистрации skill (платформа, не rm -rf)

**Запрещено:** `rm -rf` каталога skill; удаление по одному лишь path;  
удаление одноимённого skill, который существовал **до** этого deploy.

```bash
# Нет ни одной записи create → skill не создавали; skip ок
if [ ! -f "$BK/CLI_SKILL_ID.txt" ] && [ ! -f "$BK/CLI_SKILL_PATH.txt" ]; then
  echo "no create record — skip skill delete"; exit 0
fi
# Частичная запись (N29): есть ID или PATH, но не полный набор → не молчать
if [ ! -f "$BK/CLI_SKILL_ID.txt" ] || [ ! -f "$BK/CLI_SKILL_PATH.txt" ] \
   || [ ! -f "$BK/CLI_SKILL_NAME.txt" ]; then
  echo "incomplete create record — refuse silent skip; operator must resolve"
  ls -la "$BK"/CLI_SKILL_*.txt 2>/dev/null || true
  exit 2
fi
CLI_ID=$(cat "$BK/CLI_SKILL_ID.txt")
CLI_PATH=$(realpath -m "$(cat "$BK/CLI_SKILL_PATH.txt")")
CLI_NAME=$(cat "$BK/CLI_SKILL_NAME.txt")
# 1) get платформы по CLI_ID: имя и path должны совпасть с $BK
# 2) имя == cli-analyst-bundle
# 3) path realpath под SKILL_ROOT и совпадает с CLI_PATH
# 4) path НЕ был в MANIFEST_BEFORE (создан этим deploy)
# 5) только тогда: штатный delete(skill_id=CLI_ID)
# Любой mismatch → НЕ удалять; сообщить ID/path оператору (exit 2)
```

Если delete платформы недоступен или отклонён — файлы уже восстановлены
(10a); skill может остаться в глобальной библиотеке → **exit 2**, явное
сообщение владельцу.

Артефакты CLI в изолированном DATA_DIR с профилем не откатываются.
