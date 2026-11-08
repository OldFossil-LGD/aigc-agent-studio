"""Bind source/read/decision evidence to a current task and real artifacts.
This checks evidence consistency, not a model's private reasoning or artistic quality.
"""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
try:
    from .knowledge_catalog import validate_catalog
    from .knowledge_routes import check_read_evidence
except ImportError:
    from knowledge_catalog import validate_catalog
    from knowledge_routes import check_read_evidence

FEATURE_DOMAINS = {'camera': 'camera_space', 'visual': 'assets', 'assets': 'assets', 'sound': 'sound', 'silent': 'sound', 'no_dialogue': 'sound', 'look': 'look_lighting', 'stylized': 'look_lighting', 'direction': 'story_direction', 'performance': 'performance', 'motion': 'motion_physics', 'continuity': 'continuity', 'reverse': 'reverse', 'mirror': 'reverse', 'prompting': 'editing_delivery', 'maintenance': 'workflow_governance'}

def task_fingerprint(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False).encode('utf-8')).hexdigest()

def artifact_fingerprint(artifacts):
    normalized = {name: value.decode('utf-8') if isinstance(value, bytes) else str(value) for name, value in artifacts.items()}
    return task_fingerprint(normalized)

def evaluate_delivery_review(skill_root, task, artifacts, review, *, capture_root=None, session_id=None):
    root = Path(skill_root).resolve()
    failures = []
    result = {'status': 'REVIEW_REQUIRED', 'delivery_ready': False, 'failures': failures, 'creative_quality_verified': False, 'media_quality_verified': False, 'generation_authorized': False, 'scope': 'Source and decision evidence consistency; not proof of understanding or artistic quality'}
    if not isinstance(review, dict):
        failures.append('A current creative-review/v1 record is required')
        return result
    try:
        if review.get('review_format') != 'creative-review/v1': raise ValueError('Unknown review format')
        if not isinstance(review.get('unresolved'), list) or review['unresolved']:
            raise ValueError('Current-task unresolved facts/decisions must be explicitly empty for formal delivery')
        if review.get('task_sha256') != task_fingerprint(task): raise ValueError('Review belongs to a different task')
        if review.get('artifact_sha256') != artifact_fingerprint(artifacts): raise ValueError('Review belongs to different output')
        catalog = validate_catalog(root)
        if catalog['status'] != 'CATALOG_VALID': raise ValueError('Catalog invalid: ' + '; '.join(catalog['errors'][:5]))
        if review.get('catalog_sha256') != catalog['catalog_sha256']: raise ValueError('Catalog changed since consideration')
        plan = review.get('context_plan')
        if not isinstance(plan, dict): raise ValueError('Current context plan required')
        request = plan.get('request') or {}
        if task.get('intent_format'):
            if request.get('intent') != task: raise ValueError('Context plan omits or changes the intent')
        elif request.get('profile') != task.get('profile') or request.get('intent') is not None:
            raise ValueError('Text-task profile differs from its context plan')
        if not capture_root or not session_id: raise ValueError('Capture root and current session are required')
        checked = check_read_evidence(root, plan, review.get('read_receipt'), capture_root, session_id)
        if checked['status'] != 'SOURCE_EVIDENCE_VALID': raise ValueError('Full current source evidence required: ' + checked['status'])
        rows = review.get('consideration')
        if not isinstance(rows, list): raise ValueError('Domain consideration required')
        decisions_by_domain = {}
        for row in rows:
            domain = row.get('domain')
            if domain in decisions_by_domain: raise ValueError('Duplicate domain: ' + str(domain))
            if row.get('status') not in {'applicable', 'not_applicable'}: raise ValueError('Unresolved domain: ' + str(domain))
            if not str(row.get('reason', '')).strip(): raise ValueError('Missing applicability reason: ' + str(domain))
            decisions_by_domain[domain] = row
        if set(decisions_by_domain) != set(catalog['domains']): raise ValueError('Consideration must account for every catalog domain')
        mandatory = {'workflow_governance'} | {FEATURE_DOMAINS[x] for x in plan.get('features', []) if x in FEATURE_DOMAINS}
        for domain in mandatory:
            if decisions_by_domain[domain]['status'] != 'applicable': raise ValueError('Intent feature cannot be dismissed: ' + domain)
        selected = {item['path'] for item in plan.get('files', [])}
        entries = catalog['entries']
        for domain, row in decisions_by_domain.items():
            if row['status'] == 'applicable' and not any(domain in entries.get(path, {}).get('domains', []) for path in selected):
                raise ValueError('Applicable domain has no selected source: ' + domain)
        expected = {row['requirement_id'] for row in plan.get('coverage', [])}
        if not expected:
            expected = {row['id'] for row in task.get('requirements', [])}
        if not expected: raise ValueError('No explicit task requirements to review')
        covered = set()
        judgement = review.get('decisions')
        if not isinstance(judgement, list) or not judgement: raise ValueError('Decision-to-source-to-output evidence required')
        for decision in judgement:
            ids = decision.get('requirement_ids')
            if not isinstance(ids, list) or not ids or any(x not in expected for x in ids): raise ValueError('Unknown/missing decision requirement')
            rationale = str(decision.get('rationale', '')).strip()
            if not rationale: raise ValueError('Decision rationale missing')
            task_quotes = decision.get('task_evidence')
            task_text = json.dumps(task, ensure_ascii=False)
            if not isinstance(task_quotes, list) or not task_quotes or any(not isinstance(q, str) or len(q.strip()) < 4 or q not in task_text or q not in rationale for q in task_quotes):
                raise ValueError('Decision rationale must cite concrete current-task evidence, not a generic approval')
            sources = decision.get('source_evidence')
            if not isinstance(sources, list) or not sources: raise ValueError('A decision needs source evidence')
            for source in sources:
                path, quote = source.get('path'), source.get('quote')
                if path not in selected or not isinstance(quote, str) or not quote.strip(): raise ValueError('Source was not selected/read or has no excerpt')
                if quote not in (root / path).read_text(encoding='utf-8'): raise ValueError('Source excerpt is not in current original text')
            applied = decision.get('applied_to')
            if not isinstance(applied, list) or not applied: raise ValueError('A decision needs actual output evidence')
            for location in applied:
                name, text = location.get('artifact'), location.get('text')
                if name not in artifacts or not isinstance(text, str) or not text.strip(): raise ValueError('Output location/text is missing')
                actual = artifacts[name].decode('utf-8') if isinstance(artifacts[name], bytes) else str(artifacts[name])
                if text not in actual: raise ValueError('Claimed application is absent from actual output')
            covered.update(ids)
        if covered != expected: raise ValueError('Some task requirements have no decision evidence: ' + ', '.join(sorted(expected - covered)))
        result.update(status='REVIEW_EVIDENCE_VALID', delivery_ready=True, source_evidence_status=checked['status'], decision_count=len(judgement))
    except (ValueError, OSError, KeyError, TypeError, AttributeError) as exc:
        result['status'] = 'REVIEW_REJECTED'
        failures.append(str(exc))
    return result

def main():
    parser = argparse.ArgumentParser(description='Review a current text/plan artifact; no generation or quality approval')
    parser.add_argument('--task', required=True)
    parser.add_argument('--artifact', required=True)
    parser.add_argument('--review', required=True)
    parser.add_argument('--capture-root', required=True)
    parser.add_argument('--session', required=True)
    parser.add_argument('--out')
    args = parser.parse_args()
    try:
        task = json.loads(Path(args.task).read_text(encoding='utf-8'))
        review = json.loads(Path(args.review).read_text(encoding='utf-8'))
        path = Path(args.artifact)
        result = evaluate_delivery_review(Path(__file__).resolve().parents[1], task, {path.name: path.read_text(encoding='utf-8')}, review, capture_root=args.capture_root, session_id=args.session)
    except (OSError, ValueError) as exc:
        result = {'status': 'REVIEW_REJECTED', 'delivery_ready': False, 'failures': [str(exc)], 'generation_authorized': False}
    text = json.dumps(result, ensure_ascii=False, indent=2) + '\n'
    if args.out: Path(args.out).write_text(text, encoding='utf-8')
    print(text, end='')
    return 0 if result['delivery_ready'] else 1

if __name__ == '__main__':
    raise SystemExit(main())
