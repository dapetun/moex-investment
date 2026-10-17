"""Одноразово: сгенерировать tests/fixtures/safe_deploy_block_hashes.json."""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import safe_deploy_guards as g  # noqa: E402

PREDS = {
    "roots_deploy": lambda b: "DEPLOY_ROOT=" in b and "STAMP=" in b and "mkdir -p" in b,
    "roots_canon": lambda b: (
        "AGENT_DATA_LOGICAL=/home/box/agent-data" in b
        and "SKILL_ROOT_REAL=" in b
        and "export BK" in b
        and "validate-env" in b
    ),
    "step2": lambda b: "BEFORE_MARKER" in b,
    "step3": lambda b: "MANIFEST_BEFORE" in b and "noclobber" in b,
    "step4b": lambda b: "4b ok" in b,
    "step4c": lambda b: "skill-compare" in b and "LIVE_SKILL" in b,
    "step6": lambda b: "allowed_exact" in b and "MANIFEST_AFTER" in b,
    "step10a": lambda b: 'cp -a "$BK/profile.json"' in b,
    "step10b": lambda b: "refuse delete" in b and "path-check" in b,
}


def main() -> None:
    md = (ROOT / "docs/analyst_skill_patch/SAFE_DEPLOY.md").read_text(encoding="utf-8")
    blocks = g.extract_bash_steps(md)
    out: dict[str, str] = {}
    for name, pred in PREDS.items():
        hits = [b for b in blocks if pred(b)]
        if len(hits) != 1:
            raise SystemExit(f"{name}: expected 1 block, got {len(hits)}")
        norm = "\n".join(ln.rstrip() for ln in hits[0].splitlines()).strip() + "\n"
        out[name] = hashlib.sha256(norm.encode("utf-8")).hexdigest()
        print(name, out[name][:16], "len", len(norm))
    dest = ROOT / "tests/fixtures/safe_deploy_block_hashes.json"
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(
        json.dumps(
            {"algo": "sha256", "encoding": "utf-8", "blocks": out},
            indent=2,
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )
    print("wrote", dest)


if __name__ == "__main__":
    main()
