#!/usr/bin/env python3
"""Read-only lint for reverse-engineering claim ledgers.

Usage:
  python reverse_claim_lint.py claims.json
  python reverse_claim_lint.py --self-test
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


MODES = {"content_reverse", "copy_reverse", "source_replica", "rule_distill", "production_build"}
ACCESS = {"original_readback", "copy_readback", "public_media", "text_only", "none"}
EVIDENCE = {"source_readback", "copy_readback", "public_media", "text_explicit", "inferred", "unresolved"}
STATUS = {"verified", "proposed", "n/a", "undetermined"}


def lint_claim(claim: dict, index: int) -> list[str]:
    errors: list[str] = []
    for key in ("claim_id", "statement", "mode", "source_access", "evidence_class", "status"):
        if not claim.get(key):
            errors.append(f"claim[{index}] missing {key}")
    mode = claim.get("mode")
    access = claim.get("source_access")
    evidence = claim.get("evidence_class")
    status = claim.get("status")
    if mode and mode not in MODES:
        errors.append(f"claim[{index}] invalid mode: {mode}")
    if access and access not in ACCESS:
        errors.append(f"claim[{index}] invalid source_access: {access}")
    if evidence and evidence not in EVIDENCE:
        errors.append(f"claim[{index}] invalid evidence_class: {evidence}")
    if status and status not in STATUS:
        errors.append(f"claim[{index}] invalid status: {status}")
    if evidence == "unresolved" and status != "undetermined":
        errors.append(f"claim[{index}] unresolved evidence must be undetermined")
    if status == "verified" and evidence in {"inferred", "unresolved"}:
        errors.append(f"claim[{index}] verified claim cannot use {evidence}")
    if mode == "source_replica" and access != "original_readback":
        errors.append(f"claim[{index}] source_replica requires original_readback")
    if mode == "copy_reverse" and evidence == "source_readback":
        errors.append(f"claim[{index}] copy_reverse cannot use source_readback")
    if mode == "content_reverse" and claim.get("scope") == "original-level":
        errors.append(f"claim[{index}] content_reverse cannot claim original-level graph")
    if mode == "rule_distill":
        blind = claim.get("blind_test") or {}
        if not blind.get("train") or not blind.get("holdout") or not blind.get("score"):
            errors.append(f"claim[{index}] rule_distill requires blind_test train/holdout/score")
    return errors


def lint_payload(payload: object) -> list[str]:
    if isinstance(payload, dict):
        if "claim_id" in payload:
            claims = [payload]
        else:
            claims = payload.get("claims")
    else:
        claims = payload
    if not isinstance(claims, list):
        return ["payload must be a list or {claims: [...]}"]
    errors: list[str] = []
    for i, claim in enumerate(claims):
        if not isinstance(claim, dict):
            errors.append(f"claim[{i}] is not an object")
            continue
        errors.extend(lint_claim(claim, i))
    return errors


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("path", nargs="?")
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        sample = [
            {"claim_id": "C1", "statement": "copy readback", "mode": "copy_reverse", "source_access": "copy_readback", "evidence_class": "copy_readback", "status": "verified"},
            {"claim_id": "C2", "statement": "unknown", "mode": "copy_reverse", "source_access": "copy_readback", "evidence_class": "unresolved", "status": "undetermined"},
            {"claim_id": "C3", "statement": "bad", "mode": "source_replica", "source_access": "copy_readback", "evidence_class": "copy_readback", "status": "verified"},
            {"claim_id": "C4", "statement": "bad", "mode": "copy_reverse", "source_access": "copy_readback", "evidence_class": "inferred", "status": "verified"},
        ]
        errors = lint_payload(sample)
        expected = 2
        print(json.dumps({"self_test": "pass" if len(errors) == expected else "fail", "errors": errors}, ensure_ascii=False, indent=2))
        return 0 if len(errors) == expected else 1
    if not args.path:
        parser.error("path is required unless --self-test")
    text = Path(args.path).read_text(encoding="utf-8")
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        payload = [json.loads(line) for line in text.splitlines() if line.strip()]
    errors = lint_payload(payload)
    print(json.dumps({"status": "PASS" if not errors else "FAIL", "errors": errors}, ensure_ascii=False, indent=2))
    return 0 if not errors else 1


if __name__ == "__main__":
    raise SystemExit(main())
