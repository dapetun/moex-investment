#!/usr/bin/env bash
# Изолированная регрессия SAFE_DEPLOY BL7/BL8/BL9/4c (без записи в live box).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PY="${PYTHON:-python3}"
GUARDS="$ROOT/scripts/safe_deploy_guards.py"

# На MSYS/Git Bash /tmp невидим для cmd mklink — брать Windows TEMP.
case "$(uname -s 2>/dev/null || echo unknown)" in
  MINGW*|MSYS*|CYGWIN*)
    _td="${TEMP:-${TMP:-}}"
    if [[ -n "$_td" ]] && command -v cygpath >/dev/null 2>&1; then
      _td="$(cygpath -u "$_td")"
    fi
    TMP="$(mktemp -d "${_td:-/tmp}/sdreg.XXXXXX")"
    # Windows CPython не понимает /c/... — аргументы в native-форме.
    native() { cygpath -w "$1"; }
    ;;
  *)
    TMP="$(mktemp -d "${TMPDIR:-/tmp}/sdreg.XXXXXX")"
    native() { printf '%s\n' "$1"; }
    ;;
esac
cleanup() { rm -rf "$TMP"; }
trap cleanup EXIT

echo "TMP=$TMP"
SAND="$TMP/sand-data"
mkdir -p "$SAND/workflows/skill-1791618014068"
echo opt >"$SAND/workflows/skill-1791618014068/SKILL.md"
mkdir -p "$TMP/box" "$TMP/outside"

# Ссылки: symlink где возможно, иначе Windows junction через python
$PY - <<PY
from pathlib import Path
import os, subprocess, sys

def to_native(p: str) -> str:
    try:
        r = subprocess.run(
            ["cygpath", "-w", p], capture_output=True, text=True, check=False
        )
        if r.returncode == 0 and r.stdout.strip():
            return r.stdout.strip()
    except FileNotFoundError:
        pass
    return p

sand = Path(to_native(r"$SAND"))
link = Path(to_native(r"$TMP/box/agent-data"))
outside = Path(to_native(r"$TMP/outside"))
trap = sand / "workflows" / "trap"
link.parent.mkdir(parents=True, exist_ok=True)
outside.mkdir(parents=True, exist_ok=True)
(sand / "workflows").mkdir(parents=True, exist_ok=True)

def dir_link(dst: Path, src: Path) -> None:
    try:
        dst.symlink_to(src, target_is_directory=True)
        return
    except OSError:
        pass
    r = subprocess.run(
        ["cmd", "/c", "mklink", "/J", str(dst), str(src)],
        capture_output=True, text=True,
    )
    if r.returncode != 0 or not dst.exists():
        raise SystemExit(f"link failed {dst}->{src}: {r.stdout}{r.stderr}")

dir_link(link, sand)
dir_link(trap, outside)
(sand / "workflows" / "cli-analyst-bundle").mkdir(parents=True, exist_ok=True)
print("links ok")
PY

WF_LOG="$TMP/box/agent-data/workflows"
AGENT_LOG="$TMP/box/agent-data"
CLI_LOG="$WF_LOG/cli-analyst-bundle"
N_WF="$(native "$WF_LOG")"
N_AGENT="$(native "$AGENT_LOG")"
N_CLI="$(native "$CLI_LOG")"
N_TRAP="$(native "$WF_LOG/trap")"
N_DOTDOT="$(native "$WF_LOG/../agents")"
N_NOPE="$(native "$TMP/nope")"
N_GUARDS="$(native "$GUARDS")"
N_SKILL="$(native "$WF_LOG/skill-1791618014068/SKILL.md")"

# --- BL7: platform symlink/junction must PASS ---
$PY "$N_GUARDS" path-check "$N_CLI" "$N_WF" "$N_AGENT" >/dev/null
echo "PASS BL7 platform symlink"

# --- BL7: escape must FAIL (nonzero) ---
set +e
$PY "$N_GUARDS" path-check "$N_TRAP" "$N_WF" "$N_AGENT" >/dev/null 2>&1
esc_rc=$?
set -e
if [[ $esc_rc -eq 0 ]]; then
  echo "FAIL: escape path returned 0"; exit 1
fi
echo "PASS BL7 escape rejected (rc=$esc_rc)"

# --- BL7: .. must FAIL ---
set +e
$PY "$N_GUARDS" path-check "$N_DOTDOT" "$N_WF" "$N_AGENT" >/dev/null 2>&1
dot_rc=$?
set -e
if [[ $dot_rc -eq 0 ]]; then
  echo "FAIL: .. path returned 0"; exit 1
fi
echo "PASS BL7 dotdot rejected (rc=$dot_rc)"

# --- BL8: bash must not print 4b ok after python fail ---
set +e
out=$(
  $PY "$N_GUARDS" path-check "$N_NOPE" "$N_WF" "$N_AGENT" || exit 1
  echo "4b ok"
)
rc=$?
set -e
if [[ $rc -eq 0 ]] || [[ "$out" == *"4b ok"* ]]; then
  echo "FAIL BL8: rc=$rc out=$out"; exit 1
fi
echo "PASS BL8 fail-closed"

# --- BL9: manifest keys canonical ---
DEPLOY_ROOT="$TMP/deploy-root"
mkdir -p "$DEPLOY_ROOT"
MANIFEST="$DEPLOY_ROOT/MANIFEST_BEFORE.txt"
H=$(printf 'a%.0s' {1..64})
# в манифест — logical (как find на box); load_manifest канонизирует
echo "$H  $N_SKILL" >"$MANIFEST"
CANON=$($PY "$N_GUARDS" canon "$N_SKILL")
N_MANIFEST="$(native "$MANIFEST")"
N_ROOT="$(native "$ROOT")"
$PY - <<PY
from pathlib import Path
import sys
sys.path.insert(0, r"$N_ROOT" + r"\scripts" if sys.platform.startswith("win") else r"$N_ROOT/scripts")
# path insert: portable
import os
sys.path.insert(0, os.path.join(r"$N_ROOT", "scripts"))
import safe_deploy_guards as g
d = g.load_manifest(Path(r"$N_MANIFEST"))
assert r"$CANON" in d, d
print("PASS BL9 canonical manifest")
PY

# --- 4c: frontmatter fold OK, body change FAIL ---
REPO="$TMP/repo_SKILL.md"
LIVE="$TMP/live_SKILL.md"
cat >"$REPO" <<'EOF'
---
name: cli-analyst-bundle
description: >
  Даниила: читать moex_analyst_bundle.v1 и/или запускать разрешённую цепочку
  CLI moex_portfolio. отказ.

---

# Body
ok
EOF
cat >"$LIVE" <<'EOF'
---
name: cli-analyst-bundle
description: >-
  Даниила: читать moex_analyst_bundle.v1 и/или запускать разрешённую цепочку CLI
  moex_portfolio. отказ.
---
# Body
ok
EOF
N_REPO="$(native "$REPO")"
N_LIVE="$(native "$LIVE")"
$PY "$N_GUARDS" skill-compare "$N_REPO" "$N_LIVE" >/dev/null
echo "PASS 4c fold-equivalent"

cat >"$LIVE" <<'EOF'
---
name: cli-analyst-bundle
description: x
---
# Body
changed
EOF
set +e
$PY "$N_GUARDS" skill-compare "$N_REPO" "$N_LIVE" >/dev/null 2>&1
c4_rc=$?
set -e
if [[ $c4_rc -eq 0 ]]; then
  echo "FAIL 4c body change accepted"; exit 1
fi
echo "PASS 4c body mismatch rejected (rc=$c4_rc)"

# --- unified DEPLOY_ROOT ---
echo "$CLI_LOG" >"$DEPLOY_ROOT/CLI_SKILL_PATH.txt"
printf '%s\n' 'cli-analyst-bundle' >"$DEPLOY_ROOT/CLI_SKILL_ID.txt"
printf '%s\n' 'cli-analyst-bundle' >"$DEPLOY_ROOT/CLI_SKILL_NAME.txt"
test -f "$DEPLOY_ROOT/MANIFEST_BEFORE.txt"
test -f "$DEPLOY_ROOT/CLI_SKILL_PATH.txt"
echo "PASS unified DEPLOY_ROOT"

# --- rollback 10b: path-check на escape → nonzero ---
set +e
$PY "$N_GUARDS" path-check "$N_TRAP" "$N_WF" "$N_AGENT" >/dev/null 2>&1
rb_rc=$?
set -e
if [[ $rb_rc -eq 0 ]]; then
  echo "FAIL rollback path-check accepted escape"; exit 1
fi
echo "PASS rollback path-guard rejects escape (rc=$rb_rc)"

# --- partial create record ---
PARTIAL="$DEPLOY_ROOT/partial"
mkdir -p "$PARTIAL"
echo 'cli-analyst-bundle' >"$PARTIAL/CLI_SKILL_NAME.txt"
: >"$PARTIAL/CLI_SKILL_ID.txt"
echo "$CLI_LOG" >"$PARTIAL/CLI_SKILL_PATH.txt"
if [[ -s "$PARTIAL/CLI_SKILL_ID.txt" ]]; then
  echo "FAIL partial ID unexpectedly non-empty"; exit 1
fi
echo "PASS partial-create incomplete ID detected"

# --- BL10: isolated shell, empty/missing WF — тот же inline, что в SAFE_DEPLOY ---
run_bl10_inline() {
  # симуляция: отдельный bash -c без функций из других блоков
  env -i PATH="$PATH" HOME="$HOME" bash --noprofile --norc -c '
    set -euo pipefail
    BK="'"$1"'"
    WF="'"$2"'"
    AGENT_REAL="'"$3"'"
    SKILL_ROOT_LOGICAL="'"$4"'"
    AGENT_DATA_LOGICAL="'"$5"'"
    : "${BK:?}" "${WF:?}" "${AGENT_REAL:?}" "${SKILL_ROOT_LOGICAL:?}" "${AGENT_DATA_LOGICAL:?}"
    case "$WF" in ""|"/"|".") echo "WF unsafe: <$WF>"; exit 1;; esac
    test -d "$BK" && test -d "$WF" && test -d "$AGENT_REAL" \
      || { echo "BK/WF/AGENT_REAL must be directories"; exit 1; }
    echo "bl10 inline ok"
  '
}
set +e
run_bl10_inline "$DEPLOY_ROOT" "" "$N_AGENT" "$N_WF" "$N_AGENT" >/dev/null 2>&1
bl10_empty=$?
run_bl10_inline "$DEPLOY_ROOT" "/" "$N_AGENT" "$N_WF" "$N_AGENT" >/dev/null 2>&1
bl10_slash=$?
# без WF вовсе
env -i PATH="$PATH" bash --noprofile --norc -c '
  set -euo pipefail
  BK="'"$DEPLOY_ROOT"'"
  AGENT_REAL="'"$N_AGENT"'"
  : "${BK:?}" "${WF:?}" "${AGENT_REAL:?}"
' >/dev/null 2>&1
bl10_unset=$?
set -e
if [[ $bl10_empty -eq 0 || $bl10_slash -eq 0 || $bl10_unset -eq 0 ]]; then
  echo "FAIL BL10: empty=$bl10_empty slash=$bl10_slash unset=$bl10_unset"; exit 1
fi
echo "PASS BL10 isolated shell rejects empty/slash/unset WF (rc $bl10_empty/$bl10_slash/$bl10_unset)"

# --- N34: missing path nonzero ---
set +e
$PY "$N_GUARDS" path-check "$N_NOPE" "$N_WF" "$N_AGENT" >/dev/null 2>&1
n34_rc=$?
set -e
if [[ $n34_rc -eq 0 ]]; then
  echo "FAIL N34: missing path returned 0"; exit 1
fi
echo "PASS N34 missing path rejected (rc=$n34_rc)"

# --- N35: extra frontmatter key ---
cat >"$REPO" <<'EOF'
---
name: cli-analyst-bundle
description: x
---
# Body
ok
EOF
cat >"$LIVE" <<'EOF'
---
name: cli-analyst-bundle
description: x
allowed-agents: all
---
# Body
ok
EOF
set +e
$PY "$N_GUARDS" skill-compare "$N_REPO" "$N_LIVE" >/dev/null 2>&1
n35_rc=$?
set -e
if [[ $n35_rc -eq 0 ]]; then
  echo "FAIL N35: extra FM key accepted"; exit 1
fi
echo "PASS N35 extra frontmatter rejected (rc=$n35_rc)"

# --- N41: orphan indented after plain scalar ---
cat >"$LIVE" <<'EOF'
---
name: cli-analyst-bundle
description: x
  allowed: all
---
# Body
ok
EOF
set +e
$PY "$N_GUARDS" skill-compare "$N_REPO" "$N_LIVE" >/dev/null 2>&1
n41_rc=$?
set -e
if [[ $n41_rc -eq 0 ]]; then
  echo "FAIL N41: orphan indented accepted"; exit 1
fi
echo "PASS N41 orphan indented rejected (rc=$n41_rc)"

# --- N39: extract steps from actual SAFE_DEPLOY.md ---
SD="$ROOT/docs/analyst_skill_patch/SAFE_DEPLOY.md"
N_COUNT=$($PY "$N_GUARDS" extract-steps "$(native "$SD")")
test "$N_COUNT" -ge 6 || { echo "FAIL N39: too few bash blocks ($N_COUNT)"; exit 1; }
echo "PASS N39 extract-steps count=$N_COUNT"

# --- N43/N44: validate-env rejects AGENT_REAL=/ and WF mismatch ---
AGENTS_DIR="$SAND/agents/5bda2f3d-a61a-48d6-8663-2441802d68de"
mkdir -p "$AGENTS_DIR"
N_AGENTS="$(native "$AGENTS_DIR")"
N_SKILL_REAL="$(native "$SAND/workflows")"
N_DEPLOY="$(native "$DEPLOY_ROOT")"
N_REPO_ROOT="$(native "$ROOT")"
# BL11: передаём переменные в environ явно (как в SAFE_DEPLOY после export)
run_validate() {
  BK="$N_DEPLOY" DEPLOY_ROOT="$N_DEPLOY" WF="$N_SKILL_REAL" \
    SKILL_ROOT_REAL="$N_SKILL_REAL" SKILL_ROOT_LOGICAL="$N_WF" \
    AGENT_DATA_LOGICAL="$N_AGENT" AGENT_REAL="$1" REPO_ROOT="$N_REPO_ROOT" \
    $PY "$N_GUARDS" validate-env --need-repo
}
run_validate "$N_AGENTS" >/dev/null
echo "PASS validate-env ok on mock (BL11 env pass-through)"

# без env — должен упасть
set +e
env -i PATH="$PATH" $PY "$N_GUARDS" validate-env --need-repo >/dev/null 2>&1
bl11_rc=$?
set -e
if [[ $bl11_rc -eq 0 ]]; then echo "FAIL BL11: validate-env ok without env"; exit 1; fi
echo "PASS BL11 validate-env fails without env (rc=$bl11_rc)"

mkdir -p "$TMP/other-wf"
set +e
AGENT_REAL="/" BK="$N_DEPLOY" DEPLOY_ROOT="$N_DEPLOY" WF="$N_SKILL_REAL" \
  SKILL_ROOT_REAL="$N_SKILL_REAL" SKILL_ROOT_LOGICAL="$N_WF" \
  AGENT_DATA_LOGICAL="$N_AGENT" REPO_ROOT="$N_REPO_ROOT" \
  $PY "$N_GUARDS" validate-env --need-repo >/dev/null 2>&1
n43_rc=$?
BK="$N_DEPLOY" DEPLOY_ROOT="$N_DEPLOY" WF="$(native "$TMP/other-wf")" \
  SKILL_ROOT_REAL="$N_SKILL_REAL" SKILL_ROOT_LOGICAL="$N_WF" \
  AGENT_DATA_LOGICAL="$N_AGENT" AGENT_REAL="$N_AGENTS" REPO_ROOT="$N_REPO_ROOT" \
  $PY "$N_GUARDS" validate-env --need-repo >/dev/null 2>&1
n44_rc=$?
# N45: AGENT_REAL = корень sand-data
BK="$N_DEPLOY" DEPLOY_ROOT="$N_DEPLOY" WF="$N_SKILL_REAL" \
  SKILL_ROOT_REAL="$N_SKILL_REAL" SKILL_ROOT_LOGICAL="$N_WF" \
  AGENT_DATA_LOGICAL="$N_AGENT" AGENT_REAL="$(native "$SAND")" REPO_ROOT="$N_REPO_ROOT" \
  $PY "$N_GUARDS" validate-env --need-repo >/dev/null 2>&1
n45_rc=$?
set -e
if [[ $n43_rc -eq 0 ]]; then echo "FAIL N43 AGENT_REAL=/ accepted"; exit 1; fi
if [[ $n44_rc -eq 0 ]]; then echo "FAIL N44 WF mismatch accepted"; exit 1; fi
if [[ $n45_rc -eq 0 ]]; then echo "FAIL N45 AGENT_REAL=sand root accepted"; exit 1; fi
echo "PASS N43/N44/N45 validate-env rejects (rc $n43_rc/$n44_rc/$n45_rc)"

# N39: извлечь шаг 2 из SD и выполнить preamble (case+validate) в env -i
STEP2_FILE="$TMP/step2_preamble.sh"
PY_FOR_SD="$PY"
# Git Bash: Windows-пути → forward slash для вставки в sh
case "$(uname -s 2>/dev/null || echo unknown)" in
  MINGW*|MSYS*|CYGWIN*) PY_FOR_SD=$(cygpath -u "$PY" 2>/dev/null || echo "$PY");;
esac
export ROOT PY_FOR_SD STEP2_FILE
$PY - <<'PY'
from pathlib import Path
import os, sys
root = Path(os.environ["ROOT"])
sys.path.insert(0, str(root / "scripts"))
import safe_deploy_guards as g
from safe_deploy_guards import read_text_no_universal_newlines as _r
md = _r(root / "docs/analyst_skill_patch/SAFE_DEPLOY.md")
step2 = next(b for b in g.extract_bash_steps(md) if "BEFORE_MARKER" in b)
pre = step2.split("touch")[0]
pre = pre.replace("python3 ", os.environ["PY_FOR_SD"] + " ")
Path(os.environ["STEP2_FILE"]).write_text(pre, encoding="utf-8")
print("wrote", len(pre))
PY
set +e
env -i PATH="$PATH" BK="$N_DEPLOY" DEPLOY_ROOT="$N_DEPLOY" WF="$N_SKILL_REAL" \
  AGENT_REAL="$N_AGENTS" SKILL_ROOT_LOGICAL="$N_WF" SKILL_ROOT_REAL="$N_SKILL_REAL" \
  AGENT_DATA_LOGICAL="$N_AGENT" REPO_ROOT="$N_REPO_ROOT" \
  bash --noprofile --norc "$STEP2_FILE" >/dev/null 2>&1
n39_ok=$?
env -i PATH="$PATH" BK="$N_DEPLOY" DEPLOY_ROOT="$N_DEPLOY" WF="$N_SKILL_REAL" \
  AGENT_REAL="/" SKILL_ROOT_LOGICAL="$N_WF" SKILL_ROOT_REAL="$N_SKILL_REAL" \
  AGENT_DATA_LOGICAL="$N_AGENT" REPO_ROOT="$N_REPO_ROOT" \
  bash --noprofile --norc "$STEP2_FILE" >/dev/null 2>&1
n39_bad=$?
set -e
if [[ $n39_ok -ne 0 ]]; then echo "FAIL N39: real step2 preamble failed rc=$n39_ok"; exit 1; fi
if [[ $n39_bad -eq 0 ]]; then echo "FAIL N39: step2 preamble accepted AGENT_REAL=/"; exit 1; fi
echo "PASS N39 executed SAFE_DEPLOY step2 preamble (ok=$n39_ok bad=$n39_bad)"

# N39 integrity + мутации M1–M4
$PY - <<'PY'
import os, re, sys
from pathlib import Path
sys.path.insert(0, str(Path(os.environ["ROOT"]) / "scripts"))
import safe_deploy_guards as g
from safe_deploy_guards import read_text_no_universal_newlines as _r
md = _r(Path(os.environ["ROOT"]) / "docs/analyst_skill_patch/SAFE_DEPLOY.md")
g.assert_safe_deploy_integrity(md)
blocks = g.extract_bash_steps(md)
step4b = next(b for b in blocks if "4b ok" in b)
bad = re.sub(r"(path-check[\s\S]{0,200}?)\|\|\s*exit\s+1", r"\1", step4b, count=1)
try:
    g.assert_safe_deploy_integrity(md.replace(step4b, bad))
except SystemExit as e:
    assert "path-check missing" in str(e), e
else:
    raise SystemExit("M3 mutation not detected")
print("PASS N39 integrity + M3 mutation detected")
PY

$PY "$N_GUARDS" check-hashes "$(native "$ROOT/docs/analyst_skill_patch/SAFE_DEPLOY.md")" \
  "$(native "$ROOT/tests/fixtures/safe_deploy_block_hashes.json")"
echo "PASS N39 SAFE_DEPLOY block hashes pinned"

# --- N39: run AGENT_REAL=/ case from SAFE_DEPLOY step-2 preface in env -i ---
set +e
env -i PATH="$PATH" BK="$N_DEPLOY" WF="$N_SKILL_REAL" AGENT_REAL="/" \
  SKILL_ROOT_LOGICAL="$N_WF" AGENT_DATA_LOGICAL="$N_AGENT" \
  SKILL_ROOT_REAL="$N_SKILL_REAL" DEPLOY_ROOT="$N_DEPLOY" REPO_ROOT="$(native "$ROOT")" \
  bash --noprofile --norc -c '
    set -euo pipefail
    case "$AGENT_REAL" in ""|"/"|"."|"..") echo "AGENT_REAL unsafe"; exit 1;; esac
    echo should_not_reach
  ' >/dev/null 2>&1
sd_agent_rc=$?
set -e
if [[ $sd_agent_rc -eq 0 ]]; then
  echo "FAIL N39/N43: SAFE_DEPLOY case AGENT_REAL=/ returned 0"; exit 1
fi
echo "PASS N39 SAFE_DEPLOY inline AGENT_REAL=/ rejected (rc=$sd_agent_rc)"

echo "ALL SAFE_DEPLOY regression checks passed"
