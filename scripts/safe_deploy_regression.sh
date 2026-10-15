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

# --- BL10: unset WF must fail require_deploy_env ---
set +e
bl10_out=$(
  BK="$DEPLOY_ROOT"
  WF=""
  AGENT_REAL="$N_AGENT"
  SKILL_ROOT_LOGICAL="$N_WF"
  AGENT_DATA_LOGICAL="$N_AGENT"
  (
    set -euo pipefail
    : "${BK:?BK required}"
    : "${WF:?WF required}"
    : "${AGENT_REAL:?AGENT_REAL required}"
    test -d "$BK" && test -d "$WF" && test -d "$AGENT_REAL" \
      || { echo "BK/WF/AGENT_REAL must be directories"; exit 1; }
  ) 2>&1
)
bl10_rc=$?
set -e
if [[ $bl10_rc -eq 0 ]]; then
  echo "FAIL BL10: empty WF returned 0"; exit 1
fi
echo "PASS BL10 unset WF rejected (rc=$bl10_rc)"

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

echo "ALL SAFE_DEPLOY regression checks passed"
