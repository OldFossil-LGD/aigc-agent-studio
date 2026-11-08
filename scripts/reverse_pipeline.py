#!/usr/bin/env python3
"""One-command reverse pipeline: compile, claim gate, optional blind gate.

No ignition, generation, upload, export, or network operation is performed.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent

try:
    from scripts.blind_test_gate import evaluate as evaluate_blind
    from scripts.compile_production import compile_production
except ImportError:
    from blind_test_gate import evaluate as evaluate_blind
    from compile_production import compile_production


def _load(path: str):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _blind_result(args) -> tuple[dict | None, int]:
    required = [args.blind_spec, args.blind_inputs, args.blind_predictions, args.blind_truth, args.blind_score]
    if not any(required):
        return None, 0
    if not all(required):
        return {"status": "USAGE", "exit_code": 2, "failures": [{"code": "BLIND_ARGS_INCOMPLETE"}]}, 2
    result = evaluate_blind(
        _load(args.blind_spec),
        _load(args.blind_inputs),
        _load(args.blind_predictions),
        _load(args.blind_truth),
        _load(args.blind_score),
        _load(args.blind_diff) if args.blind_diff else None,
    )
    return result, int(result.get("exit_code", 3))


def _source_result(args) -> tuple[dict | None, int]:
    if not args.source and not args.plan:
        return None, 0
    if not args.source or not args.plan:
        return {"status": "USAGE", "exit_code": 2,
                "failures": [{"code": "SOURCE_ARGS_INCOMPLETE"}]}, 2
    cmd = [
        sys.executable,
        str(HERE / "source_fidelity_lint.py"),
        "--source", args.source,
        "--plan", args.plan,
        "--mode", args.source_mode,
    ]
    if args.contract:
        cmd += ["--contract", args.contract]
    proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    try:
        result = json.loads(proc.stdout.decode("utf-8", "replace"))
    except Exception:
        result = {"status": "FAIL", "failures": [{"code": "SOURCE_GATE_PARSE_FAILED"}], "stdout": proc.stdout.decode("utf-8", "replace")}
    return result, proc.returncode


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("input")
    parser.add_argument("--out", required=True)
    parser.add_argument("--contract")
    parser.add_argument("--source")
    parser.add_argument("--plan")
    parser.add_argument("--source-mode", choices=["source_replica", "copy_reverse", "content_reverse"], default="copy_reverse")
    parser.add_argument("--blind-spec")
    parser.add_argument("--blind-inputs")
    parser.add_argument("--blind-predictions")
    parser.add_argument("--blind-truth")
    parser.add_argument("--blind-score")
    parser.add_argument("--blind-diff")
    parser.add_argument("--allow-gate-fail", action="store_true")
    args = parser.parse_args()
    out_dir = Path(args.out)
    data = _load(args.input)
    compiled = compile_production(data, out_dir)
    production_rc = 0 if compiled["gate"]["status"] == "PASS" else 1
    claim_rc = 0 if compiled["claim_gate"]["status"] == "PASS" else 1
    source_result, source_rc = _source_result(args)
    blind_result, blind_rc = _blind_result(args)
    if source_result is not None:
        (out_dir / "11_source_gate.json").write_text(json.dumps(source_result, ensure_ascii=False, indent=2), encoding="utf-8")
    if blind_result is not None:
        (out_dir / "12_blind_gate.json").write_text(json.dumps(blind_result, ensure_ascii=False, indent=2), encoding="utf-8")
    status = "PASS" if not production_rc and not claim_rc and not source_rc and not blind_rc else "FAIL"
    summary = {
        "status": status,
        "production_gate": compiled["gate"],
        "claim_gate": compiled["claim_gate"],
        "source_gate": source_result,
        "blind_gate": blind_result,
        "out": str(out_dir),
    }
    (out_dir / "13_reverse_pipeline_summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    if status == "FAIL" and not args.allow_gate_fail:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
