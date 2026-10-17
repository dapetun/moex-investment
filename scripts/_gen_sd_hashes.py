"""Одноразово: сгенерировать tests/fixtures/safe_deploy_block_hashes.json."""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import safe_deploy_guards as g  # noqa: E402


def main() -> None:
    md = g.read_text_no_universal_newlines(
        ROOT / "docs/analyst_skill_patch/SAFE_DEPLOY.md"
    )
    blocks = g.critical_block_hashes(md)
    fences = g.fence_hashes(md)
    doc = g.document_sha256(md)
    for name, h in blocks.items():
        print(name, h[:16])
    print("document", doc[:16], "fences", len(fences))
    dest = ROOT / "tests/fixtures/safe_deploy_block_hashes.json"
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(
        json.dumps(
            {
                "algo": "sha256",
                "encoding": "utf-8",
                "document_sha256": doc,
                "fence_count": len(fences),
                "fences": fences,
                "blocks": blocks,
            },
            indent=2,
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )
    print("wrote", dest)


if __name__ == "__main__":
    main()
