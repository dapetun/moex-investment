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

## 3. Контрольные суммы до изменения

Записать в `$BK/BEFORE.txt` вывод шага 1 (включая description-хеш,
QC SKILL.md и `run_optimizer.example.py`) + `ls -la` skill-каталогов.  
Снять `MANIFEST_BEFORE.txt` по процедуре шага 6 **до** любых правок.

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

## 6. Проверка отсутствия побочных изменений (манифест sha256)

Не использовать `find -newer` + широкий grep по `skill-*` (ложные срабатывания
на mtime `workflows/` и маскировка чужих skills). Вместо этого — манифест.

```bash
AGENT=/home/box/agent-data/agents/5bda2f3d-a61a-48d6-8663-2441802d68de
WF=/home/box/agent-data/workflows
CLI_PATH=$(cat "$BK/CLI_SKILL_PATH.txt")

# До apply (шаг 3): полный манифест workflows + агент + критичные invest-файлы
(
  find "$WF" "$AGENT" -type f | sort | xargs -r sha256sum
  sha256sum \
    /workspace/invest/portfolio/optimizer/config/optimizer.yaml \
    /workspace/invest/portfolio/optimizer/run_optimizer.example.py \
    /workspace/invest/portfolio/analysis_spec.md \
    /workspace/invest/news/events_latest.json
) > "$BK/MANIFEST_BEFORE.txt"

# После apply: тот же снимок
(
  find "$WF" "$AGENT" -type f | sort | xargs -r sha256sum
  sha256sum \
    /workspace/invest/portfolio/optimizer/config/optimizer.yaml \
    /workspace/invest/portfolio/optimizer/run_optimizer.example.py \
    /workspace/invest/portfolio/analysis_spec.md \
    /workspace/invest/news/events_latest.json
) > "$BK/MANIFEST_AFTER.txt"

# Разрешённые отличия AFTER vs BEFORE (точные пути):
# - $AGENT/profile.json
# - $WF/skill-1791618014068/SKILL.md
# - $WF/skill-1791618006478/SKILL.md
# - $WF/skill-1791617999761/SKILL.md
# - /workspace/invest/portfolio/analysis_spec.md (если SPEC в наборе A)
# - любые файлы под $CLI_PATH/ (новый skill)
# Всё остальное, включая skills радара и events_latest.json — должно совпадать.

BK="$BK" python3 - <<'PY'
import os, pathlib, sys
bk = pathlib.Path(os.environ["BK"])
cli = pathlib.Path((bk / "CLI_SKILL_PATH.txt").read_text().strip())
allowed_exact = {
    "/home/box/agent-data/agents/5bda2f3d-a61a-48d6-8663-2441802d68de/profile.json",
    "/home/box/agent-data/workflows/skill-1791618014068/SKILL.md",
    "/home/box/agent-data/workflows/skill-1791618006478/SKILL.md",
    "/home/box/agent-data/workflows/skill-1791617999761/SKILL.md",
    "/workspace/invest/portfolio/analysis_spec.md",
}
def load(p):
    d = {}
    for line in p.read_text().splitlines():
        h, f = line.split(None, 1)
        d[f] = h
    return d
before, after = load(bk/"MANIFEST_BEFORE.txt"), load(bk/"MANIFEST_AFTER.txt")
bad = []
for f, h in after.items():
    if f == str(cli) or f.startswith(str(cli) + "/"):
        continue
    if f in allowed_exact:
        continue
    if before.get(f) != h:
        bad.append(("changed", f, before.get(f), h))
for f in before:
    if f not in after and not (f == str(cli) or f.startswith(str(cli) + "/")):
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
`events_latest.json` и skills радара **не** в allow-list: их изменение во время deploy = стоп.

Манифест BEFORE снимать **до** шага 4; AFTER — после шага 5.

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

```bash
cp -a "$BK/profile.json" /home/box/agent-data/agents/5bda2f3d-a61a-48d6-8663-2441802d68de/profile.json
cp -a "$BK/OPT_SKILL.md" /home/box/agent-data/workflows/skill-1791618014068/SKILL.md
cp -a "$BK/POS_SKILL.md" /home/box/agent-data/workflows/skill-1791618006478/SKILL.md
cp -a "$BK/QC_SKILL.md" /home/box/agent-data/workflows/skill-1791617999761/SKILL.md
cp -a "$BK/analysis_spec.md" /workspace/invest/portfolio/analysis_spec.md
CLI_PATH=$(cat "$BK/CLI_SKILL_PATH.txt")
case "$CLI_PATH" in
  /home/box/agent-data/workflows/skill-[0-9]*) ;;
  *) echo "refusing rm -rf: $CLI_PATH"; exit 1 ;;
esac
rm -rf "$CLI_PATH"
# optimizer.yaml не должен был меняться; при отличии — восстановить из $BK
test "$(sha256sum /workspace/invest/portfolio/optimizer/config/optimizer.yaml | awk '{print $1}')" \
  = "a9f44c2606b95b42bfb70c1c9400d4e5c39c1ce83f564be5ae3ab746e9c09c83" \
  || cp -a "$BK/optimizer.yaml" /workspace/invest/portfolio/optimizer/config/optimizer.yaml
```

Проверка отката: запрос «optimize» без явного CLI → «интеграция не настроена»;
sha256 OPT/POS/QC/profile/yaml = BEFORE. Артефакты CLI в изолированном
DATA_DIR/клоне не откатываются вместе с профилем — не использовать их
как боевые.
