# Безопасный deploy Permission A (не выполнять без подтверждения)

Пакет: `cli-analyst-bundle` + `live_patches/*` @ репо SHA, зафиксированный в задании.  
**В этой подготовке deploy не выполняется.**

## 0. Предусловия

- Permission A утверждено владельцем.
- Permission B **не** подразумевается.
- `optimizer.yaml` остаётся `enabled: false` (sha256 из AUDIT_BASELINE).
- PR #2 не сливать ради этого шага.
- Аналитик **неактивен** на всё время deploy (нет активного анализа;
  иначе store.db* / settings шумят; store.* из манифеста исключены,
  но settings.json агента — нет).

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
# description отдельно (если jq доступен):
python3 -c "import json,hashlib,pathlib; p=pathlib.Path('$AGENT/profile.json'); d=json.loads(p.read_text())['description']; print(hashlib.sha256(d.encode()).hexdigest(), 'description')"
```

Сверить с `live_patches/AUDIT_BASELINE.md`.  
Любое расхождение → **стоп**, новый аудит, патчи не применять.

## 2. Резервная копия

```bash
STAMP=$(date +%Y%m%dT%H%M%S)
BK=/tmp/analyst-cli-backup-$STAMP
mkdir -p "$BK"
touch "$BK/BEFORE_MARKER"
cp -a /home/box/agent-data/agents/5bda2f3d-a61a-48d6-8663-2441802d68de/profile.json "$BK/"
cp -a /home/box/agent-data/workflows/skill-1791618014068/SKILL.md "$BK/OPT_SKILL.md"
cp -a /home/box/agent-data/workflows/skill-1791618006478/SKILL.md "$BK/POS_SKILL.md"
cp -a /home/box/agent-data/workflows/skill-1791617999761/SKILL.md "$BK/QC_SKILL.md"
cp -a /workspace/invest/portfolio/analysis_spec.md "$BK/"
# optimizer.yaml только копировать для контроля, не менять
cp -a /workspace/invest/portfolio/optimizer/config/optimizer.yaml "$BK/"
cp -a /workspace/invest/portfolio/optimizer/run_optimizer.example.py "$BK/"
sha256sum "$BK"/* > "$BK/SHA256SUMS"
```

Обязательно скопировать `$BK` в устойчивое место:
`cp -a "$BK" "/workspace/handoffs/backups/analyst-cli-$STAMP/"`
(`/tmp` может очиститься при перезагрузке).

## 3. Контрольные суммы и MANIFEST_BEFORE (до любых правок)

Записать в `$BK/BEFORE.txt` вывод шага 1 + `ls -la` skill-каталогов.

Снять манифест **один раз**, без перезаписи (`noclobber`):

```bash
AGENT=/home/box/agent-data/agents/5bda2f3d-a61a-48d6-8663-2441802d68de
WF=/home/box/agent-data/workflows
set -o noclobber
(
  find "$WF" "$AGENT" -type f \
    ! -name 'store.db' ! -name 'store.db-wal' ! -name 'store.db-shm' \
    | sort | xargs -r sha256sum
  # Рекурсивно (без -maxdepth): optimizer, config, schemas, handoff —
  # иначе optimizer.yaml и handoff/radar_to_analyst/* выпадают (BL5).
  find /workspace/invest/portfolio/optimizer /workspace/invest/config \
       /workspace/invest/schemas /workspace/invest/handoff \
       -type f 2>/dev/null | sort | xargs -r sha256sum
  # Только верхний уровень portfolio/ (csv и analysis_spec; не reports/).
  find /workspace/invest/portfolio -maxdepth 1 -type f 2>/dev/null | sort | xargs -r sha256sum
  sha256sum /workspace/invest/news/events_latest.json \
    /workspace/invest/portfolio/optimizer/config/optimizer.yaml
) > "$BK/MANIFEST_BEFORE.txt" || { echo "MANIFEST_BEFORE write failed (exists?)"; exit 1; }
set +o noclobber
```

## 4. Применение только утверждённых изменений

Порядок:

1. Создать skill-каталог платформы для нового skill (имя из frontmatter
   `cli-analyst-bundle`; фактический путь `skill-<id>/` назначает платформа —
   зафиксировать путь в `$BK/CLI_SKILL_PATH.txt` сразу после создания).
2. Скопировать содержимое `docs/analyst_skill_patch/cli-analyst-bundle/` репо
   на **зафиксированном SHA** в этот каталог.
3. Применить `OPT_SKILL.patch.md` к OPT.
4. Применить `POS_SKILL.patch.md` к POS.
5. Применить `QC_SKILL.patch.md` к QC (fixture/user_csv исключения для пути B).
6. Применить `PROFILE_DESCRIPTION.patch.md` к полю `description`.
7. Применить `SPEC_analysis_spec.patch.md` (если входит в утверждённый набор A).
8. **Не** менять: `optimizer.yaml`, settings радара, `portfolio.csv`, store.db,
   news/*, handoff/* (кроме чтения).

## 5. Проверка синтаксиса / корректности

- `profile.json` — валидный JSON после правки description.
- Frontmatter OPT/POS/cli-analyst-bundle — валидный YAML.
- Имя skill в D08 (`cli-analyst-bundle`) совпадает с frontmatter `name`
  нового skill; путь каталога `skill-<id>` записан в `$BK/CLI_SKILL_PATH.txt`.
- `optimizer.yaml`: `enabled: false`, command пуст (байт-в-байт или тот же sha256).

## 6. Проверка отсутствия побочных изменений (MANIFEST_AFTER)

Только **после** шага 5. `MANIFEST_BEFORE.txt` уже снят на шаге 3 и
не перезаписывать.

```bash
AGENT=/home/box/agent-data/agents/5bda2f3d-a61a-48d6-8663-2441802d68de
WF=/home/box/agent-data/workflows
test -f "$BK/MANIFEST_BEFORE.txt" || { echo "MANIFEST_BEFORE missing"; exit 1; }
CLI_PATH=$(realpath -m "$(cat "$BK/CLI_SKILL_PATH.txt")")
# N16: новый skill = …/workflows/skill-<digits>, отсутствовал в BEFORE, не OPT/POS/QC/EV
case "$CLI_PATH" in
  "$WF"/skill-[0-9]*) ;;
  *) echo "bad CLI_SKILL_PATH: $CLI_PATH"; exit 1 ;;
esac
echo "$CLI_PATH" | grep -Eq '^/home/box/agent-data/workflows/skill-[0-9]+$' \
  || { echo "CLI_PATH not canonical skill id dir"; exit 1; }
for known in skill-1791618014068 skill-1791618006478 skill-1791617999761 \
             skill-1791617992518 skill-1791617966204 skill-1791617976741; do
  [ "$CLI_PATH" = "$WF/$known" ] && { echo "CLI_PATH collides with existing $known"; exit 1; }
done
grep -F " $CLI_PATH/" "$BK/MANIFEST_BEFORE.txt" && { echo "CLI_PATH existed before"; exit 1; }

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
# Не сверяем штатный шум радара/отчётов (не в манифесте):
# news/digest*, news/events_history.jsonl, logs/, portfolio/reports/
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

Любое unexpected → rollback.  
В манифесте (не в allow-list): `events_latest.json`, skills радара,
`invest/config/**`, `schemas/**`, `handoff/**` (вкл. `radar_to_analyst/`),
`portfolio/optimizer/**` (вкл. `optimizer.yaml`).  
Не в манифесте (штатный шум): `news/digest*`, `news/events_history.jsonl`,
`logs/`, `portfolio/reports/`.

## 7. One-shot на fixture (явный запрос Даниила)

В чате Аналитика, явно: CLI-анализ на fixture / синтетике, SHA репо в задании,
`MOEX_DATA_SOURCE=fixture`, `MOEX_ISS_ENABLED=false`, без user_csv.
Для fixture: stale/не-ISS — warn «синтетика», не fail (см. QC_SKILL.patch).

Критерий успеха:

- цепочка exit 0; bundle `schema=moex_analyst_bundle.v1`;
- в отчёте баннер ДЕМОНСТРАЦИЯ; есть `run_id` (и `event_id` если события были);
- формат 9 разделов; yaml не включался;
- запись в portfolio/reports и logs по правилам профиля.

## 7b. Dry-run формы user_csv (между A и B, ещё не Permission B)

На искусственных данных той же структуры (не боевые файлы):

```bash
MOEX_ISS_ENABLED=false python scripts/dry_run_real_shaped_analysis.py
```

Критерий: exit 0, все шаги ok, пути без абсолютных home.  
Боевые portfolio/prices не используются.

## 8. Программная сверка отчёта

Сверка claims отчёта с числами bundle (как verify_report / ручная таблица
весов, Sharpe, drift). Расхождение → rollback или стоп без Permission B.

## 9. Контрольные суммы после изменения

Записать AFTER sha256 изменённых файлов + каталога cli-analyst-bundle в `$BK/AFTER.txt`.

## 10. Rollback при ошибке

Сначала восстановить известные файлы из бэкапа. `rm -rf` нового skill —
только после полного guard (копия проверок шага 6). При отказе guard —
**не удалять** каталог, сообщить путь оператору.

```bash
AGENT=/home/box/agent-data/agents/5bda2f3d-a61a-48d6-8663-2441802d68de
WF=/home/box/agent-data/workflows
cp -a "$BK/profile.json" "$AGENT/profile.json"
cp -a "$BK/OPT_SKILL.md" "$WF/skill-1791618014068/SKILL.md"
cp -a "$BK/POS_SKILL.md" "$WF/skill-1791618006478/SKILL.md"
cp -a "$BK/QC_SKILL.md" "$WF/skill-1791617999761/SKILL.md"
cp -a "$BK/analysis_spec.md" /workspace/invest/portfolio/analysis_spec.md

# yaml контроль / восстановление
test "$(sha256sum /workspace/invest/portfolio/optimizer/config/optimizer.yaml | awk '{print $1}')" \
  = "a9f44c2606b95b42bfb70c1c9400d4e5c39c1ce83f564be5ae3ab746e9c09c83" \
  || cp -a "$BK/optimizer.yaml" /workspace/invest/portfolio/optimizer/config/optimizer.yaml

# Guard rm (BL4): тот же набор, что шаг 6
test -f "$BK/MANIFEST_BEFORE.txt" || { echo "no MANIFEST_BEFORE — skip rm"; exit 0; }
test -f "$BK/CLI_SKILL_PATH.txt" || { echo "no CLI_SKILL_PATH — skip rm"; exit 0; }
CLI_PATH=$(realpath -m "$(cat "$BK/CLI_SKILL_PATH.txt")")
case "$CLI_PATH" in
  "$WF"/skill-[0-9]*) ;;
  *) echo "refusing rm -rf (bad path): $CLI_PATH"; exit 1 ;;
esac
echo "$CLI_PATH" | grep -Eq '^/home/box/agent-data/workflows/skill-[0-9]+$' \
  || { echo "refusing rm -rf (not canonical): $CLI_PATH"; exit 1; }
for known in skill-1791618014068 skill-1791618006478 skill-1791617999761 \
             skill-1791617992518 skill-1791617966204 skill-1791617976741; do
  [ "$CLI_PATH" = "$WF/$known" ] && {
    echo "refusing rm of known skill $known — restore done, leave dir"; exit 1
  }
done
# Удалять только каталог, которого не было до deploy
if grep -Fq " $CLI_PATH/" "$BK/MANIFEST_BEFORE.txt" \
   || grep -Eq " ${CLI_PATH}$" "$BK/MANIFEST_BEFORE.txt"; then
  echo "refusing rm of path that existed before deploy: $CLI_PATH"; exit 1
fi
rm -rf --one-file-system "$CLI_PATH"
```

Проверка отката: «optimize» без явного CLI → «интеграция не настроена»;
sha256 OPT/POS/QC/profile/yaml = BEFORE. Артефакты CLI в изолированном
DATA_DIR не откатываются с профилем.
