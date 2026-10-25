"""Сгенерировать внешний pin JSON для задания Permission A (не доверять из архива)."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import minimal_deploy as md  # noqa: E402


def main() -> None:
    head = subprocess.check_output(
        ["git", "-C", str(ROOT), "rev-parse", "HEAD"], text=True
    ).strip()
    files: dict[str, str] = {}
    for rel in md.PACKAGE_CRITICAL:
        p = ROOT / rel
        if not p.is_file():
            raise SystemExit(f"missing {rel}")
        data = p.read_bytes()
        if b"\r" in data:
            raise SystemExit(f"CR in {rel}: normalize to LF before pinning")
        files[rel] = md.sha256_bytes(data)
    out = {
        "note": "EXTERNAL pin for assignment — pass via --expect-json OUTSIDE PKG",
        "expect_head": head,
        "files": files,
    }
    dest = ROOT / "tests/fixtures/minimal_deploy_external_pin.json"
    dest.write_bytes(
        (json.dumps(out, indent=2, ensure_ascii=False) + "\n").encode("utf-8")
    )
    print("wrote", dest)
    print("expect_head", head)
    for k, v in files.items():
        print(k, v[:16])


if __name__ == "__main__":
    main()
