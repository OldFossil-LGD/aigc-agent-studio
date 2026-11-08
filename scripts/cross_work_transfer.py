#!/usr/bin/env python3
"""Cross-work transfer test: does work A's template predict work B?

The within-work blind test only proves that one work's template can be fitted.
This asks the harder question: take the fingerprint of work A and predict the
per-unit fields of a *different* work B, then score the misses.

Read-only. Consumes `work_units.py` output; no LibTV call, no generation.

Usage:
  python scripts/cross_work_transfer.py --train units_A.json --test units_B.json --out report.json
"""

from __future__ import annotations

import argparse
import collections
import json
import statistics
import sys
from pathlib import Path


EXACT_FIELDS = ("model", "modeType", "ratio", "enableSound", "duration")
COUNT_FIELDS = ("imageList", "audioList")
BLOCK_FIELDS = ("active_assets", "image_manifest", "output_contract", "timed_beats")

TRANSFERABLE = 0.85


def load(path: str) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def mode_of(values):
    values = [value for value in values if value not in (None, "")]
    if not values:
        return None
    return collections.Counter(values).most_common(1)[0][0]


def median_of(values):
    values = [value for value in values if isinstance(value, (int, float))]
    return statistics.median(values) if values else None


def fingerprint(units: list[dict]) -> dict:
    marks = {}
    for field in EXACT_FIELDS:
        marks[field] = mode_of([unit.get(field) for unit in units])
    for field in COUNT_FIELDS:
        marks[field] = median_of([unit.get(field) for unit in units])
    marks["prompt_len"] = median_of([unit.get("prompt_len") for unit in units])
    marks["blocks"] = {
        block: (sum(1 for unit in units if (unit.get("blocks") or {}).get(block)) / len(units))
        if units
        else None
        for block in BLOCK_FIELDS
    }
    return marks


def score(train_units: list[dict], test_units: list[dict]) -> dict:
    marks = fingerprint(train_units)
    metrics = {}
    for field in EXACT_FIELDS:
        expected = marks.get(field)
        hits = sum(1 for unit in test_units
                   if expected is not None and unit.get(field) == expected)
        metrics[field] = {
            "predicted": expected,
            "hit_rate": hits / len(test_units) if test_units and expected is not None else None,
            "hits": hits,
        }
    for field in COUNT_FIELDS + ("prompt_len",):
        expected = marks.get(field)
        errors = [
            abs(float(unit[field]) - float(expected))
            for unit in test_units
            if isinstance(expected, (int, float)) and isinstance(unit.get(field), (int, float))
        ]
        metrics[field] = {
            "predicted": expected,
            "mae": statistics.mean(errors) if errors else None,
        }
    block_rows = {}
    for block, rate in (marks.get("blocks") or {}).items():
        predicted = bool(rate is not None and rate >= 0.5)
        hits = sum(1 for unit in test_units if bool((unit.get("blocks") or {}).get(block)) == predicted)
        block_rows[block] = {
            "train_rate": rate,
            "predicted": predicted,
            "hit_rate": hits / len(test_units) if test_units else None,
            "reading": (
                "absent_in_train_agreement_on_absence"
                if not predicted
                else "present_in_train_predicted_present"
            ),
        }
    metrics["blocks"] = block_rows

    verdicts = {}
    for field in EXACT_FIELDS + BLOCK_FIELDS:
        if field in BLOCK_FIELDS:
            row = block_rows.get(field) or {}
            hit = row.get("hit_rate")
            # A block the training work never uses predicts "absent"; when the test work
            # is also absent the rate is 1.0 while proving nothing about transfer.
            if not row.get("predicted"):
                verdicts[field] = "vacuous_agreement"
                continue
        else:
            hit = (metrics.get(field) or {}).get("hit_rate")
            if hit is None:
                verdicts[field] = "no_signal"
                continue
        verdicts[field] = "transferable" if isinstance(hit, (int, float)) and hit >= TRANSFERABLE else "work_specific"
    for field in COUNT_FIELDS:
        mae = (metrics.get(field) or {}).get("mae")
        if mae is None:
            verdicts[field] = "no_signal"
        else:
            verdicts[field] = "transferable" if isinstance(mae, (int, float)) and mae <= 1.0 else "work_specific"
    return {"fingerprint": marks, "metrics": metrics, "verdicts": verdicts}


def self_test() -> int:
    cases = []
    train = [
        {"model": "Seedance 2.5", "modeType": "mixed2video", "ratio": "21:9", "enableSound": "on",
         "duration": 10, "imageList": 4, "audioList": 2, "prompt_len": 100,
         "blocks": {"active_assets": True, "image_manifest": True, "output_contract": True, "timed_beats": True}},
        {"model": "Seedance 2.5", "modeType": "mixed2video", "ratio": "21:9", "enableSound": "on",
         "duration": 10, "imageList": 4, "audioList": 2, "prompt_len": 120,
         "blocks": {"active_assets": True, "image_manifest": True, "output_contract": True, "timed_beats": True}},
    ]
    same = [dict(unit) for unit in train]
    result = score(train, same)
    cases.append(("self_transfer_is_perfect", result["metrics"]["model"]["hit_rate"] == 1.0))
    cases.append(("count_mae_zero", result["metrics"]["imageList"]["mae"] == 0))

    alien = [
        {"model": "Kling O3", "modeType": "text2video", "ratio": "16:9", "enableSound": None,
         "duration": 5, "imageList": 0, "audioList": 0, "prompt_len": 40,
         "blocks": {"active_assets": False, "image_manifest": False, "output_contract": False, "timed_beats": False}},
    ]
    missed = score(train, alien)
    cases.append(("alien_work_scores_zero", missed["metrics"]["model"]["hit_rate"] == 0.0))
    cases.append(("alien_marked_work_specific", missed["verdicts"]["model"] == "work_specific"))
    cases.append(("count_mae_visible", missed["metrics"]["imageList"]["mae"] == 4))

    failed = [name for name, ok in cases if not ok]
    print(json.dumps({"self_test": "pass" if not failed else "fail", "cases": cases, "failed": failed}, ensure_ascii=False, indent=2))
    return 0 if not failed else 1


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--train")
    parser.add_argument("--test")
    parser.add_argument("--out")
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()

    if args.self_test:
        return self_test()
    if not args.train or not args.test:
        parser.error("--train and --test are required unless --self-test")

    train = load(args.train)
    test = load(args.test)
    train_units = train.get("units") or []
    test_units = test.get("units") or []
    if not train_units or not test_units:
        print(json.dumps({"status": "NOT_VERIFIED", "reason": "train or test units empty",
                          "train_units": len(train_units), "test_units": len(test_units)}, ensure_ascii=False, indent=2))
        return 3

    report = {
        "train_project": train.get("project"),
        "test_project": test.get("project"),
        "train_units": len(train_units),
        "test_units": len(test_units),
        "sampled": {"train": train.get("sampled"), "test": test.get("sampled")},
    }
    report.update(score(train_units, test_units))
    report["status"] = "PASS"
    text = json.dumps(report, ensure_ascii=False, indent=2)
    if args.out:
        Path(args.out).write_text(text + "\n", encoding="utf-8")
    print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
