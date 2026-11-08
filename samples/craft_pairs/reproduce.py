"""Reproduce the ten offline prompt deliveries through the public entry point."""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent


def snapshot() -> dict[str, str]:
    files = [ROOT / "SKILL.md", Path(__file__).resolve()]
    for folder in ("scripts", "schemas", "references", "templates"):
        files.extend(p for p in (ROOT / folder).rglob("*") if p.is_file() and p.suffix != ".pyc" and "__pycache__" not in p.parts)
    files.extend(p for p in HERE.rglob("*") if p.is_file() and p.suffix != ".pyc" and "__pycache__" not in p.parts)
    return {p.relative_to(ROOT).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(set(files))}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    output = args.out.resolve()
    output.mkdir(parents=True, exist_ok=False)
    (output / "logs").mkdir()
    initial = snapshot()
    rows = []
    for path in sorted((HERE / "intents").glob("*.json")):
        case_id = path.stem
        target = output / "products" / case_id
        argv = [sys.executable, str(ROOT / "scripts" / "compile_intent_delivery.py"), str(path), "--out", str(target)]
        start = dt.datetime.now(dt.timezone.utc).isoformat()
        result = subprocess.run(argv, cwd=ROOT, capture_output=True, check=False)
        end = dt.datetime.now(dt.timezone.utc).isoformat()
        out_log = output / "logs" / (case_id + ".stdout.log")
        err_log = output / "logs" / (case_id + ".stderr.log")
        out_log.write_bytes(result.stdout)
        err_log.write_bytes(result.stderr)
        rows.append({"case_id": case_id, "argv": argv, "cwd": str(ROOT),
            "started_at": start, "ended_at": end, "exit_code": result.returncode,
            "stdout": str(out_log), "stderr": str(err_log), "product_dir": str(target),
            "intent_sha256": hashlib.sha256(path.read_bytes()).hexdigest()})
        print(f"{case_id}: exit={result.returncode}", flush=True)
    final = snapshot()
    report = {"boundary": "offline text delivery only; exit zero does not prove creative quality or media effects",
              "source_manifest_before": initial, "source_manifest_after": final,
              "source_unchanged_during_run": initial == final, "runs": rows}
    (output / "run_results.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if initial != final:
        print("Source changed during the run; these products are provisional.", flush=True)
    raise SystemExit(1 if any(row["exit_code"] != 0 for row in rows) else 0)


if __name__ == "__main__":
    main()
