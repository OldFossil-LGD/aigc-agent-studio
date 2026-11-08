#!/usr/bin/env python3
"""Run every case in evals/fidelity/manifest.json against source_fidelity_lint.

Read-only. No LibTV call, no generation.
"""

from __future__ import annotations

import json
from pathlib import Path

try:
    from .source_fidelity_lint import evaluate
    from .make_fidelity_fixtures import DERIVATIONS
except ImportError:
    from source_fidelity_lint import evaluate
    from make_fidelity_fixtures import DERIVATIONS


FIXTURE_DIR = Path(__file__).resolve().parents[1] / "evals" / "fidelity"


def run() -> int:
    manifest_path = FIXTURE_DIR / "manifest.json"
    results: list[tuple[str, bool]] = []
    if not manifest_path.is_file():
        print(json.dumps({"status": "FAIL", "cases": [], "failed": ["manifest_missing"]}, ensure_ascii=False, indent=2))
        return 1
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    results.append(("manifest_has_cases", bool(manifest.get("cases"))))
    results.append(("manifest_records_provenance", bool((manifest.get("provenance") or {}).get("source_uuid"))))

    for case in manifest.get("cases") or []:
        name = case.get("name")
        source_path = FIXTURE_DIR / str(case.get("source"))
        derive = case.get("derive")
        plan_path = FIXTURE_DIR / str(case.get("plan")) if case.get("plan") else None
        if not source_path.is_file() or (plan_path is not None and not plan_path.is_file()):
            results.append(("fixture:%s:files_present" % name, False))
            continue
        source_graph = json.loads(source_path.read_text(encoding="utf-8"))
        if derive:
            if derive not in DERIVATIONS:
                results.append(("fixture:%s:derive_known" % name, False))
                continue
            plan_graph = DERIVATIONS[derive](source_graph)
        else:
            plan_graph = json.loads(plan_path.read_text(encoding="utf-8"))
        result = evaluate(
            source_graph,
            plan_graph,
            mode=case.get("mode", "copy_reverse"),
            deliverable=case.get("deliverable", "auto"),
            lineage=case.get("lineage", "auto"),
        )
        codes = {failure.get("code") for failure in result.get("failures") or []}
        ok = result.get("status") == case.get("expected_status")
        missing = [code for code in case.get("expect_codes") or [] if code not in codes]
        if missing:
            ok = False
        results.append(("fixture:%s" % name, ok))
        if not ok:
            results.append(
                (
                    "fixture:%s:detail" % name,
                    False,
                )
            )
            print(
                json.dumps(
                    {
                        "fixture": name,
                        "expected": case.get("expected_status"),
                        "actual": result.get("status"),
                        "expected_codes_missing": missing,
                        "actual_codes": sorted(codes),
                        "why": case.get("why"),
                    },
                    ensure_ascii=False,
                )
            )

    failed = [name for name, ok in results if not ok]
    print(json.dumps({"status": "PASS" if not failed else "FAIL", "cases": results, "failed": failed}, ensure_ascii=False, indent=2))
    return 0 if not failed else 1


if __name__ == "__main__":
    raise SystemExit(run())
