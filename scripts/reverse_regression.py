#!/usr/bin/env python3
"""Self-test for reverse mode, claim, source-access and blind gates."""

from __future__ import annotations

import json
from pathlib import Path

from blind_test_gate import evaluate as blind_evaluate
from reverse_claim_lint import lint_payload
from reverse_contract import evidence_default, mode_errors, normalize_mode

FIXTURES = Path(__file__).resolve().parents[1] / "evals" / "reverse_fixtures.json"

REQUIRED_FIXTURES = (
    "valid_copy_reverse",
    "invalid_source_replica_from_copy",
    "invalid_unresolved_verified",
    "invalid_rule_distill_without_blind",
    "invalid_source_replica_without_original_permission",
)


def valid_claim():
    return [{
        "claim_id": "C1",
        "statement": "copy-level result",
        "mode": "copy_reverse",
        "source_access": "copy_readback",
        "evidence_class": "copy_readback",
        "source_project_uuid": "source",
        "copy_project_uuid": "copy",
        "status": "verified",
        "scope": "copy-level",
        "evidence": ["copy.json"],
        "test": "blind_test_gate",
    }]


def valid_blind_inputs():
    spec = {"blind_test": {"train": 8, "holdout": 2, "thresholds": {
        "model_mode": 0.85, "duration": 0.85, "sound": 0.90,
        "audio_exact": 0.85, "image_exact": 0.75,
        "image_mae_max": 1.0, "prompt_blocks": 0.90,
    }}}
    inputs = [{"group": "A", "text": "spec A"}, {"group": "B", "text": "spec B"}]
    pred = [{"group": "A"}, {"group": "B"}]
    truth = [{"group": "A"}, {"group": "B"}]
    score = {
        "units": 2, "model_mode": 1.0, "duration": 1.0, "sound": 1.0,
        "audio_exact": 1.0, "image_exact": 1.0, "image_mae": 0.0,
        "unresolved_false_positive": 0, "block_active_assets": 2,
        "block_image_manifest": 2, "block_output_contract": 2,
        "block_timed_beats": 2,
    }
    return spec, inputs, pred, truth, score


def fixture_claim(case: dict) -> dict:
    """Build the claim a fixture case describes."""
    mode = case.get("mode")
    access = case.get("source_access")
    evidence = case.get("evidence_class") or evidence_default(mode, access)
    claim = {
        "claim_id": case.get("name"),
        "statement": case.get("name"),
        "mode": mode,
        "source_access": access,
        "evidence_class": evidence,
        "status": case.get("status") or ("undetermined" if evidence == "unresolved" else "verified"),
        "scope": "copy-level",
        "evidence": [case.get("name")],
        "test": "reverse_regression",
    }
    if "blind_test" in case:
        claim["blind_test"] = case["blind_test"]
    return claim


def fixture_cases() -> list[tuple[str, bool]]:
    """Run every case in evals/reverse_fixtures.json against the claim lint."""
    if not FIXTURES.is_file():
        return [("fixtures_file_present", False)]
    payload = json.loads(FIXTURES.read_text(encoding="utf-8"))
    cases = (payload.get("cases") if isinstance(payload, dict) else payload) or []
    names = {case.get("name") for case in cases if isinstance(case, dict)}
    results: list[tuple[str, bool]] = [
        ("fixtures_cover_required_cases", set(REQUIRED_FIXTURES) <= names),
    ]
    for case in cases:
        if not isinstance(case, dict):
            results.append(("fixture_entry_is_object", False))
            continue
        expected = case.get("expected")
        if expected not in {"PASS", "FAIL"}:
            results.append((f"fixture:{case.get('name')}", False))
            continue
        errors = lint_payload(fixture_claim(case))
        ok = (not errors) if expected == "PASS" else bool(errors)
        must_contain = case.get("expect_error_contains")
        if ok and must_contain:
            ok = any(must_contain in error for error in errors)
        results.append((f"fixture:{case.get('name')}", ok))
    return results


def run() -> int:
    results = []

    mode, warnings = normalize_mode("film_reverse")
    results.append(("legacy_mode_mapping", mode == "content_reverse" and bool(warnings)))

    bad_source = valid_claim()
    bad_source[0].update({"mode": "source_replica", "source_access": "copy_readback"})
    results.append(("copy_cannot_claim_source_replica", bool(lint_payload(bad_source))))

    bad_unresolved = valid_claim()
    bad_unresolved[0].update({"evidence_class": "unresolved", "status": "verified"})
    results.append(("unresolved_cannot_be_verified", bool(lint_payload(bad_unresolved))))

    bad_rule = valid_claim()
    bad_rule[0].update({"mode": "rule_distill", "blind_test": {}})
    results.append(("rule_distill_requires_blind_test", bool(lint_payload(bad_rule))))

    spec, inputs, pred, truth, score = valid_blind_inputs()
    valid_gate = blind_evaluate(spec, inputs, pred, truth, score)
    results.append(("blind_gate_pass", valid_gate["exit_code"] == 0))

    low = dict(score)
    low["model_mode"] = 0.5
    results.append(("blind_gate_low_score_fails", blind_evaluate(spec, inputs, pred, truth, low)["exit_code"] == 1))

    no_threshold = {"blind_test": {"train": 8, "holdout": 2}}
    results.append(("blind_gate_no_threshold_not_verified", blind_evaluate(no_threshold, inputs, pred, truth, score)["exit_code"] == 3))

    leaked = [dict(inputs[0], model="leak"), inputs[1]]
    results.append(("blind_gate_leakage_fails", blind_evaluate(spec, leaked, pred, truth, score)["exit_code"] == 1))

    fp = dict(score)
    fp["unresolved_false_positive"] = 1
    results.append(("blind_gate_unresolved_fp_fails", blind_evaluate(spec, inputs, pred, truth, fp)["exit_code"] == 1))

    reverse_contract = {"mode": "copy_reverse", "source_access": "copy_readback",
                        "source_project_uuid": "s", "copy_project_uuid": "c"}
    results.append(("work_profile_required_for_reverse", "WORK_PROFILE_MISSING" in mode_errors(reverse_contract)))
    results.append((
        "work_profile_present_clears_error",
        "WORK_PROFILE_MISSING" not in mode_errors(dict(reverse_contract, work_profile={"work": "x"})),
    ))
    results.append(("production_build_needs_no_profile", "WORK_PROFILE_MISSING" not in mode_errors({"mode": "production_build"})))

    results.extend(fixture_cases())

    failed = [name for name, ok in results if not ok]
    print(json.dumps({"status": "PASS" if not failed else "FAIL", "cases": results, "failed": failed}, ensure_ascii=False, indent=2))
    return 0 if not failed else 1


if __name__ == "__main__":
    raise SystemExit(run())
