#!/usr/bin/env python3
"""Read-only gate for a frozen blind-reverse test.

Exit codes:
  0 PASS, 1 FAIL, 2 usage, 3 not_verified / not enough evidence.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

RC_OK, RC_FAIL, RC_USAGE, RC_EMPTY = 0, 1, 2, 3

DEFAULT_THRESHOLDS = {
    "model_mode": 0.85,
    "duration": 0.85,
    "sound": 0.90,
    "audio_exact": 0.85,
    "image_exact": 0.75,
    "image_mae_max": 1.0,
    "prompt_blocks": 0.90,
}

FORBIDDEN_INPUT_KEYS = {
    "model", "modeType", "mode_type", "settings", "prompt", "video_prompt",
    "imageList", "videoList", "audioList", "taskId", "task_id", "url", "params",
}


def load(path: str):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def find_forbidden(value, path="$") -> list[str]:
    hits: list[str] = []
    if isinstance(value, dict):
        for key, item in value.items():
            if key in FORBIDDEN_INPUT_KEYS:
                hits.append(f"{path}.{key}")
            hits.extend(find_forbidden(item, f"{path}.{key}"))
    elif isinstance(value, list):
        for i, item in enumerate(value):
            hits.extend(find_forbidden(item, f"{path}[{i}]"))
    return hits


def normalized_score(score: dict, units: int) -> dict:
    out = dict(score)
    for key in ("model_mode", "duration", "sound", "audio_exact", "image_exact"):
        value = out.get(key)
        if isinstance(value, (int, float)) and value > 1 and units:
            out[key] = float(value) / units
    if "prompt_blocks" not in out:
        block_keys = [k for k in out if k.startswith("block_")]
        if block_keys:
            denom = len(block_keys) * max(1, units or out.get("units", 1))
            values = [float(out[k]) for k in block_keys]
            out["prompt_blocks"] = (sum(values) / denom) if max(values, default=0) > 1 else (sum(values) / len(values))
    if "unresolved_false_positive" not in out:
        out["unresolved_false_positive"] = None
    return out


def evaluate(spec, inputs, predictions, truth, score, diff=None) -> dict:
    failures, warnings = [], []
    blind = spec.get("blind_test") or {}
    if blind.get("train") is None or blind.get("holdout") is None:
        return {"status": "NOT_VERIFIED", "exit_code": RC_EMPTY, "failures": [{"code": "BLIND_SPLIT_MISSING"}], "warnings": warnings}
    thresholds = blind.get("thresholds")
    if not thresholds:
        return {"status": "NOT_VERIFIED", "exit_code": RC_EMPTY, "failures": [{"code": "THRESHOLDS_NOT_DECLARED"}], "warnings": warnings}
    if not predictions or not truth:
        return {"status": "NOT_VERIFIED", "exit_code": RC_EMPTY, "failures": [{"code": "PREDICTIONS_OR_TRUTH_EMPTY"}], "warnings": warnings}
    if len(predictions) != len(truth):
        failures.append({"code": "HOLDOUT_SIZE_MISMATCH", "predictions": len(predictions), "truth": len(truth)})
    leaks = find_forbidden(inputs)
    if leaks:
        failures.append({"code": "BLIND_INPUT_LEAKAGE", "paths": leaks[:20]})
    s = normalized_score(score or {}, len(truth))
    checks = [
        ("model_mode", "MODEL_MODE_BELOW_THRESHOLD", thresholds.get("model_mode", DEFAULT_THRESHOLDS["model_mode"])),
        ("duration", "DURATION_BELOW_THRESHOLD", thresholds.get("duration", DEFAULT_THRESHOLDS["duration"])),
        ("sound", "SOUND_BELOW_THRESHOLD", thresholds.get("sound", DEFAULT_THRESHOLDS["sound"])),
        ("audio_exact", "AUDIO_EXACT_BELOW_THRESHOLD", thresholds.get("audio_exact", DEFAULT_THRESHOLDS["audio_exact"])),
        ("image_exact", "IMAGE_EXACT_BELOW_THRESHOLD", thresholds.get("image_exact", DEFAULT_THRESHOLDS["image_exact"])),
        ("prompt_blocks", "PROMPT_BLOCKS_BELOW_THRESHOLD", thresholds.get("prompt_blocks", DEFAULT_THRESHOLDS["prompt_blocks"])),
    ]
    metrics = {}
    for key, code, minimum in checks:
        value = s.get(key)
        metrics[key] = value
        if value is None:
            return {"status": "NOT_VERIFIED", "exit_code": RC_EMPTY, "failures": [{"code": "SCORE_METRIC_MISSING", "metric": key}], "warnings": warnings}
        if float(value) < float(minimum):
            failures.append({"code": code, "value": value, "minimum": minimum})
    mae = s.get("image_mae")
    metrics["image_mae"] = mae
    if mae is None:
        return {"status": "NOT_VERIFIED", "exit_code": RC_EMPTY, "failures": [{"code": "SCORE_METRIC_MISSING", "metric": "image_mae"}], "warnings": warnings}
    if float(mae) > float(thresholds.get("image_mae_max", DEFAULT_THRESHOLDS["image_mae_max"])):
        failures.append({"code": "IMAGE_MAE_ABOVE_MAX", "value": mae, "maximum": thresholds.get("image_mae_max", DEFAULT_THRESHOLDS["image_mae_max"])})
    unresolved_fp = s.get("unresolved_false_positive")
    if unresolved_fp is None and isinstance(diff, dict):
        unresolved_fp = (diff.get("summary") or {}).get("unresolved_false_positive")
    if unresolved_fp is None:
        return {"status": "NOT_VERIFIED", "exit_code": RC_EMPTY, "failures": [{"code": "UNRESOLVED_FALSE_POSITIVE_NOT_MEASURED"}], "warnings": warnings}
    if int(unresolved_fp) != 0:
        failures.append({"code": "UNRESOLVED_FALSE_POSITIVE", "value": unresolved_fp})
    return {
        "status": "FAIL" if failures else "PASS",
        "exit_code": RC_FAIL if failures else RC_OK,
        "blind_test": {"train": blind.get("train"), "holdout": blind.get("holdout")},
        "thresholds": thresholds,
        "metrics": metrics,
        "unresolved_false_positive": unresolved_fp,
        "failures": failures,
        "warnings": warnings,
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--spec")
    ap.add_argument("--inputs")
    ap.add_argument("--predictions")
    ap.add_argument("--truth")
    ap.add_argument("--score")
    ap.add_argument("--diff")
    ap.add_argument("--out")
    ap.add_argument("--self-test", action="store_true")
    args = ap.parse_args()
    if args.self_test:
        spec = {"blind_test": {"train": 8, "holdout": 2, "thresholds": {
            "model_mode": 0.85, "duration": 0.85, "sound": 0.90,
            "audio_exact": 0.85, "image_exact": 0.75,
            "image_mae_max": 1.0, "prompt_blocks": 0.90,
        }}}
        inputs = [{"group": "A", "text": "x"}, {"group": "B", "text": "y"}]
        pred = [{"group": "A"}, {"group": "B"}]
        truth = [{"group": "A"}, {"group": "B"}]
        score = {"units": 2, "model_mode": 2, "duration": 2, "sound": 2,
                 "audio_exact": 2, "image_exact": 2, "image_mae": 0.0,
                 "unresolved_false_positive": 0,
                 "block_active_assets": 2, "block_image_manifest": 2,
                 "block_output_contract": 2, "block_timed_beats": 2}
        ok = evaluate(spec, inputs, pred, truth, score)["exit_code"] == 0
        low = dict(score, model_mode=0.5)
        ok = ok and evaluate(spec, inputs, pred, truth, low)["exit_code"] == 1
        missing = evaluate({"blind_test": {"train": 8, "holdout": 2}}, inputs, pred, truth, score)["exit_code"] == 3
        print(json.dumps({"self_test": "pass" if ok and missing else "fail"}, ensure_ascii=False))
        return 0 if ok and missing else 1
    missing_args = [name for name in ("spec", "inputs", "predictions", "truth", "score") if not getattr(args, name)]
    if missing_args:
        ap.error("missing required arguments: " + ", ".join("--" + x for x in missing_args))
    result = evaluate(load(args.spec), load(args.inputs), load(args.predictions), load(args.truth), load(args.score), load(args.diff) if args.diff else None)
    text = json.dumps(result, ensure_ascii=False, indent=2)
    if args.out:
        Path(args.out).write_text(text, encoding="utf-8")
    print(text)
    return result["exit_code"]


if __name__ == "__main__":
    raise SystemExit(main())
