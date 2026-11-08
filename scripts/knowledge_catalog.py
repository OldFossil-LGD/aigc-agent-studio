"""Public-source discovery metadata; never evidence that a model understood a file."""
from __future__ import annotations
import argparse
import hashlib
import json
import os
from pathlib import Path

CATALOG = 'references/knowledge-catalog.json'
EXCLUDED = {'.git', '.snapshots', '.orchestrator_tmp', '__pycache__', '.pytest_cache', '.mypy_cache', '.cache', '.venv', 'node_modules', 'out', 'dist', 'build', '.context_reads'}
DOMAINS = {
    'story_direction': ['Narrative and direction', ['drama', 'story', 'direction', 'script', 'episode', 'plot', 'character-depth']],
    'performance': ['Character performance', ['performance', 'actor', 'expression', 'staging']],
    'camera_space': ['Camera, framing and space', ['camera', 'shot', 'spatial', 'geo', 'sequence']],
    'look_lighting': ['Visual craft, lighting and colour', ['style', 'look', 'light', 'color', 'skin', 'tone', 'package', 'carrier']],
    'motion_physics': ['Motion and physical causality', ['motion', 'movement', 'physics', 'feedback']],
    'assets': ['Characters, props and scene assets', ['asset', 'character', 'prop', 'scene']],
    'continuity': ['Continuity and state', ['continuity', 'sequence', 'world_state', 'cross-shot']],
    'sound': ['Sound and silence', ['sound', 'audio', 'mix', 'voice', 'loudness', 'music']],
    'editing_delivery': ['Editing, prompts and delivery', ['edit', 'delivery', 'export', 'prompt', 'render', 'transition']],
    'reverse': ['Reverse analysis and fidelity', ['reverse', 'fidelity', 'replica', 'blind']],
    'workflow_governance': ['Workflow, evidence and permissions', ['workflow', 'governance', 'law', 'context', 'knowledge', 'key-decisions', 'pitfalls', 'run-sheet']],
    'implementation_publication': ['Implementation, testing and publication', []],
}
ROLES = {'entry', 'active_reference', 'mixed_reference', 'historical_reference', 'example', 'implementation', 'test_support', 'schema', 'sample', 'evaluation', 'documentation', 'publishing', 'support'}

def public_files(root):
    root = Path(root).resolve()
    paths = []
    for directory, dirs, names in os.walk(root):
        dirs[:] = sorted(d for d in dirs if d not in EXCLUDED and not d.endswith('.egg-info'))
        for name in names:
            path = Path(directory) / name
            if path.suffix in {'.pyc', '.pyo'}:
                continue
            if path.is_symlink():
                raise ValueError('Symlink needs explicit publication review: ' + str(path))
            paths.append(path.relative_to(root).as_posix())
    return sorted(paths)

def _role(path):
    if path == 'SKILL.md': return 'entry'
    for prefix, role in [('scripts/', 'implementation'), ('tests/', 'test_support'), ('schemas/', 'schema'), ('samples/', 'sample'), ('evals/', 'evaluation'), ('docs/', 'documentation')]:
        if path.startswith(prefix): return role
    if path.startswith('references/unified-baseline/') or path.startswith('references/examples/'): return 'example'
    if 'legacy-feasibility' in path: return 'historical_reference'
    if path.startswith('references/'):
        if any(key in path for key in ('key-decisions', 'pitfalls', 'sources-and-credits')): return 'mixed_reference'
        return 'active_reference'
    return 'publishing'

def build_catalog(root):
    root = Path(root).resolve()
    paths = sorted(set(public_files(root)) | {CATALOG})
    entries = {}
    for rel in paths:
        role = _role(rel)
        headings = []
        path = root / rel
        if rel.endswith('.md') and path.exists():
            headings = [line.lstrip('# ').strip() for line in path.read_text(encoding='utf-8-sig').splitlines() if line.startswith('#')][:6]
        text = (rel.removeprefix('scripts/') + ' ' + ' '.join(headings)).lower()
        domains = [key for key, (_, words) in DOMAINS.items() if words and any(word in text for word in words)]
        if role in {'implementation', 'test_support', 'schema', 'sample', 'evaluation', 'documentation', 'publishing', 'support'}:
            domains = sorted(set(domains) | {'implementation_publication'})
        if not domains: domains = ['workflow_governance']
        entries[rel] = {'role': role, 'domains': domains, 'headings': headings, 'sha256': None if rel == CATALOG else hashlib.sha256(path.read_bytes()).hexdigest()}
    return {'format': 'knowledge-catalog/v1', 'scope': 'Candidate discovery metadata, not authority or semantic approval; read applicable full sources and exceptions.', 'domains': {key: {'title': value[0]} for key, value in DOMAINS.items()}, 'entries': entries}

def validate_catalog(root):
    root = Path(root).resolve()
    errors = []
    try:
        catalog = json.loads((root / CATALOG).read_text(encoding='utf-8'))
        if catalog.get('format') != 'knowledge-catalog/v1': raise ValueError('Unknown catalog format')
        entries = catalog['entries']
        domains = catalog['domains']
        actual = set(public_files(root))
        for rel in sorted(actual - set(entries)): errors.append('Unregistered source: ' + rel)
        for rel in sorted(set(entries) - actual): errors.append('Missing source: ' + rel)
        for rel, item in entries.items():
            if item.get('role') not in ROLES: errors.append('Invalid role: ' + rel)
            selected = item.get('domains')
            if not isinstance(selected, list) or not selected or any(d not in domains for d in selected): errors.append('Invalid domains: ' + rel)
            if rel == CATALOG: continue  # A catalog cannot contain its own byte hash. Plans hash the real catalog separately.
            if rel not in actual: continue
            if item.get('sha256') != hashlib.sha256((root / rel).read_bytes()).hexdigest(): errors.append('Changed source requires catalog refresh/review: ' + rel)
        return {'status': 'CATALOG_VALID' if not errors else 'INVALID_CATALOG', 'errors': errors, 'domains': domains, 'entries': entries, 'catalog_sha256': hashlib.sha256((root / CATALOG).read_bytes()).hexdigest(), 'semantic_applicability': 'AGENT_MUST_REVIEW'}
    except (OSError, ValueError, KeyError, TypeError) as exc:
        return {'status': 'INVALID_CATALOG', 'errors': [str(exc)], 'semantic_applicability': 'NOT_EVALUATED'}

def main():
    parser = argparse.ArgumentParser(description='Source discovery catalog; no creative or generation approval')
    parser.add_argument('--build', action='store_true', help='Maintainer operation; inspect changed classifications before release')
    parser.add_argument('--skill-root', default=str(Path(__file__).resolve().parents[1]))
    args = parser.parse_args()
    root = Path(args.skill_root)
    if args.build:
        data = build_catalog(root)
        (root / CATALOG).write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
        print(json.dumps({'status': 'CATALOG_BUILT_REVIEW_CLASSIFICATIONS', 'files': len(data['entries'])}))
        return 0
    result = validate_catalog(root)
    print(json.dumps({key: value for key, value in result.items() if key != 'entries'}, ensure_ascii=False, indent=2))
    return 0 if result['status'] == 'CATALOG_VALID' else 1

if __name__ == '__main__':
    raise SystemExit(main())
