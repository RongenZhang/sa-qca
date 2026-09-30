"""Verify a replication bundle: check manifest checksums, then re-run replication/replicate.R and confirm that
every stored QCA result is reproduced exactly.   Usage: python -m app.exports.verify bundle.zip"""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path
from typing import Any


def verify_bundle(zip_bytes: bytes, rscript: str = "Rscript") -> dict[str, Any]:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        try:
            with zipfile.ZipFile(__import__("io").BytesIO(zip_bytes)) as z:
                for name in z.namelist():
                    if name.startswith("/") or ".." in Path(name).parts:
                        return {"ok": False, "error": f"unsafe path in archive: {name}"}
                z.extractall(root)
        except zipfile.BadZipFile:
            return {"ok": False, "error": "not a valid zip file"}
        try:
            manifest = json.loads((root / "manifest.json").read_text())
        except (OSError, ValueError):
            return {"ok": False, "error": "manifest.json is missing or unreadable"}
        problems = []
        listed = {f["path"] for f in manifest["files"]}
        for f in manifest["files"]:
            p = root / f["path"]
            if not p.exists():
                problems.append(f"missing: {f['path']}")
            elif hashlib.sha256(p.read_bytes()).hexdigest() != f["sha256"]:
                problems.append(f"checksum differs: {f['path']}")
        extra = [str(p.relative_to(root)) for p in root.rglob("*") if p.is_file() and str(p.relative_to(root)) not in listed
                 and str(p.relative_to(root)) != "manifest.json"]
        problems += [f"not in manifest: {e}" for e in extra]
        result: dict[str, Any] = {"manifest_ok": not problems, "manifest_problems": problems,
                                  "n_files": len(manifest["files"]), "run_config_id": manifest.get("run_config_id")}
        if problems:
            return {**result, "ok": False, "error": "manifest check failed; replication not attempted"}
        proc = subprocess.run([rscript, "replication/replicate.R", "."], cwd=root, capture_output=True, text=True)
        chk_path = root / "results" / "replication_check.json"
        if not chk_path.exists():
            return {**result, "ok": False, "error": "replication script failed", "stderr": proc.stderr[-2000:]}
        chk = json.loads(chk_path.read_text())
        return {**result, "ok": proc.returncode == 0 and chk["n_mismatch"] == 0, "n_runs": chk["n_runs"],
                "n_match": chk["n_match"], "n_mismatch": chk["n_mismatch"], "mismatched_run_ids": chk["mismatched_run_ids"],
                "replication_environment": chk["replication_environment"], "original_environment": chk["original_environment"]}


def main() -> None:
    if len(sys.argv) != 2:
        print(__doc__)
        sys.exit(2)
    res = verify_bundle(Path(sys.argv[1]).read_bytes())
    if res.get("ok"):
        print(f"VERIFIED: {res['n_match']} of {res['n_runs']} runs reproduced exactly; {res['n_files']} files match the manifest.")
        sys.exit(0)
    print("NOT VERIFIED:", json.dumps({k: v for k, v in res.items() if k != "ok"}, indent=2))
    sys.exit(1)


if __name__ == "__main__":
    main()
