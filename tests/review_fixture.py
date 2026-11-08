"""Mechanical protocol fixture, not proof of a model's reading or judgement."""
import json
from pathlib import Path
from scripts.knowledge_catalog import validate_catalog
from scripts.knowledge_routes import plan_context
from scripts.delivery_review import task_fingerprint, artifact_fingerprint, FEATURE_DOMAINS

def mechanical_review(root, task, artifacts, capture_root, session='mechanical-test-session'):
    root, capture_root = Path(root), Path(capture_root)
    plan = plan_context(root, task.get('task_type') or task['profile'], intent=task if task.get('intent_format') else None)
    if plan['status'] != 'PLAN_ONLY': raise AssertionError(plan)
    reads = []
    for index, item in enumerate(plan['files']):
        name = 'capture_%03d.txt' % index
        (capture_root / name).write_bytes((root / item['path']).read_bytes())
        reads.append({'path': item['path'], 'sha256': item['sha256'], 'capture_path': name, 'complete': True})
    catalog = validate_catalog(root)
    if catalog['status'] != 'CATALOG_VALID': raise AssertionError(catalog['errors'])
    required = {'workflow_governance'} | {FEATURE_DOMAINS[x] for x in plan['features'] if x in FEATURE_DOMAINS}
    consideration = [{'domain': domain, 'status': 'applicable' if domain in required else 'not_applicable', 'reason': 'Mechanical protocol fixture only: ' + ('structured intent triggers ' if domain in required else 'no declared requirement for ') + domain} for domain in catalog['domains']]
    source = 'references/context-reading.md'
    quote = next(line for line in (root / source).read_text(encoding='utf-8').splitlines() if line.strip() and not line.startswith(('#', '>')))
    name = next(iter(artifacts))
    fragment = str(artifacts[name])[:100]
    goal = task['goal']
    decisions = [{'requirement_ids': [row['requirement_id']], 'rationale': 'Mechanical consistency fixture, not artistic judgement; current goal: ' + goal, 'task_evidence': [goal], 'source_evidence': [{'path': source, 'quote': quote}], 'applied_to': [{'artifact': name, 'text': fragment}]} for row in list(plan['coverage']) + [{'requirement_id': item['id']} for item in task.get('requirements', [])]]
    return {'review_format': 'creative-review/v1', 'unresolved': [], 'task_sha256': task_fingerprint(task), 'artifact_sha256': artifact_fingerprint(artifacts), 'catalog_sha256': catalog['catalog_sha256'], 'context_plan': plan, 'read_receipt': {'session_id': session, 'reads': reads}, 'consideration': consideration, 'decisions': decisions}
