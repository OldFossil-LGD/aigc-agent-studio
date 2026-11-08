"""On-demand knowledge route resolver for aigc-agent-studio."""

from __future__ import annotations

import ast
import hashlib
import json
import os
import re
from pathlib import Path
from typing import Any


MARKER_START = "<!-- knowledge-routes:v1 -->"
MARKER_END = "<!-- /knowledge-routes -->"
CATALOG_REL = "references/run-sheet-part2.md"

CORE_REFS = ("SKILL.md", "references/governance-law.md",
             "references/production-compiler.md", "references/agent-autonomy.md")


class CatalogError(Exception):
    pass


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _sha256_file(path: Path) -> str:
    return _sha256_bytes(path.read_bytes())


def _read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        raise CatalogError("cannot read file: %s" % exc)


def _parse_module_ast(root: Path, rel: str) -> ast.Module:
    path = root / rel
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        raise CatalogError("cannot read capability source %s: %s" % (rel, exc))
    try:
        return ast.parse(text)
    except SyntaxError as exc:
        raise CatalogError("cannot parse capability source %s: %s" % (rel, exc))


def _literal_assignment(root: Path, rel: str, name: str) -> Any:
    tree = _parse_module_ast(root, rel)
    for node in tree.body:
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == name:
                    try:
                        return ast.literal_eval(node.value)
                    except (ValueError, SyntaxError) as exc:
                        raise CatalogError(
                            "cannot evaluate %s in %s: %s" % (name, rel, exc))
    raise CatalogError("%s not found in %s" % (name, rel))


def _valid_task_types(root: Path) -> tuple[str, ...]:
    value = _literal_assignment(root, "scripts/production_task_profile.py",
                               "VALID_TASK_TYPES")
    if not isinstance(value, (tuple, list)):
        raise CatalogError("VALID_TASK_TYPES must be a tuple or list")
    result = []
    for item in value:
        if not isinstance(item, str):
            raise CatalogError("VALID_TASK_TYPES entries must be strings")
        result.append(item)
    return tuple(result)


def route_files(root: Any) -> tuple[str, ...]:
    root = Path(root).expanduser()
    try:
        root = root.resolve(strict=False)
    except (OSError, RuntimeError):
        pass
    try:
        value = _literal_assignment(root, "scripts/lib_doctor.py", "ROUTE_FILES")
    except CatalogError:
        raise
    if not isinstance(value, (tuple, list)):
        raise CatalogError("ROUTE_FILES must be a tuple or list")
    result = []
    for item in value:
        if not isinstance(item, str) or not item.strip():
            raise CatalogError("ROUTE_FILES entries must be non-empty strings")
        normalized = item.strip()
        result.append(normalized)
        path = root / "references" / normalized
        try:
            if not path.is_file():
                raise CatalogError("missing route source: %s" % normalized)
            path.read_bytes()
        except OSError as exc:
            raise CatalogError("cannot read route source %s: %s" % (normalized, exc))
    return tuple(result)


def _extract_shot_kind_aliases(root: Path) -> tuple[set[str], set[str]]:
    """Read the literal vocabularies actually used by the role resolver."""
    rel = "scripts/compile_shot_graph.py"
    tree = _parse_module_ast(root, rel)
    func = next((node for node in tree.body if isinstance(node, ast.FunctionDef)
                 and node.name == "resolve_shot_roles"), None)
    if func is None:
        raise CatalogError("resolve_shot_roles not found in %s" % rel)

    def membership(value):
        if not (isinstance(value, ast.Compare) and len(value.ops) == 1
                and isinstance(value.ops[0], ast.In)
                and isinstance(value.left, ast.Name) and value.left.id == "kind"):
            return None
        source = value.comparators[0]
        try:
            aliases = (_literal_assignment(root, rel, source.id)
                       if isinstance(source, ast.Name) else ast.literal_eval(source))
        except (ValueError, SyntaxError) as exc:
            raise CatalogError("cannot derive shot-kind aliases") from exc
        if not isinstance(aliases, (set, tuple, list)) or any(
                not isinstance(alias, str) or not alias for alias in aliases):
            raise CatalogError("shot-kind aliases must be non-empty strings")
        return set(aliases)

    empty, silent = set(), set()
    for node in ast.walk(func):
        if isinstance(node, ast.Assign) and any(
                isinstance(target, ast.Name) and target.id == "silent"
                for target in node.targets):
            aliases = membership(node.value)
            if aliases is not None:
                silent.update(aliases)
        elif isinstance(node, ast.If):
            aliases = membership(node.test)
            if aliases is not None:
                empty.update(aliases)
    return empty, silent


def _no_dialogue_capable(root: Path) -> bool:
    path = root / "schemas" / "production_contract.schema.json"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        raise CatalogError("cannot read/parse schema: %s" % exc)

    def _has(obj):
        if isinstance(obj, dict):
            props = obj.get("properties")
            if isinstance(props, dict) and "no_dialogue" in props:
                return True
            for value in obj.values():
                if _has(value):
                    return True
        elif isinstance(obj, list):
            for value in obj:
                if _has(value):
                    return True
        return False

    return _has(data)


def _mirror_capable(root: Path) -> bool:
    rel = "scripts/compile_production_contract.py"
    tree = _parse_module_ast(root, rel)
    for node in tree.body:
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == "DELIVERABLES":
                    try:
                        value = ast.literal_eval(node.value)
                    except (ValueError, SyntaxError) as exc:
                        raise CatalogError("cannot evaluate DELIVERABLES in %s: %s" % (rel, exc))
                    if isinstance(value, (tuple, list, set)):
                        return "mirror" in value
    return False


def _expected_profiles(root: Path) -> set[str]:
    expected = set(_valid_task_types(root))
    empty, silent = _extract_shot_kind_aliases(root)
    if empty:
        expected.add("empty")
    if silent:
        expected.add("silent")
    if _no_dialogue_capable(root):
        expected.add("no_dialogue")
    if _mirror_capable(root):
        expected.add("mirror")
    expected.add("rework")
    return expected


def _normalize_ref(ref):
    if not isinstance(ref, str) or not ref.strip():
        raise CatalogError("reference must be a non-empty string")
    value = ref.strip().replace("\\", "/")
    if value.startswith("/") or value.startswith("\\"):
        raise CatalogError("absolute reference is not allowed: %r" % ref)
    if len(value) >= 2 and value[1] == ":":
        raise CatalogError("absolute reference is not allowed: %r" % ref)
    parts = value.split("/")
    if any(part in ("", ".", "..") for part in parts):
        raise CatalogError("unsafe reference path: %r" % ref)
    return value


def _resolve_under_root(root, ref):
    normalized = _normalize_ref(ref)
    target = root.joinpath(*normalized.split("/"))
    try:
        resolved_target = target.resolve(strict=False)
        resolved_root = root.resolve(strict=False)
    except (OSError, RuntimeError):
        raise CatalogError("cannot resolve reference: %r" % ref)
    try:
        if not resolved_target.is_relative_to(resolved_root):
            raise CatalogError("reference escapes skill root: %r" % ref)
    except AttributeError:
        if str(resolved_target).lower() != str(resolved_root).lower() and \
                not str(resolved_target).lower().startswith(
                    str(resolved_root).lower() + os.sep):
            raise CatalogError("reference escapes skill root: %r" % ref)
    try:
        if target.is_symlink():
            real = target.resolve(strict=True)
            if not real.is_relative_to(resolved_root):
                raise CatalogError("reference escapes skill root: %r" % ref)
    except OSError:
        pass
    return target


def _read_ref_bytes(root, ref):
    target = _resolve_under_root(root, ref)
    if not target.exists():
        raise CatalogError("missing reference: %s" % ref)
    if not target.is_file():
        raise CatalogError("reference is not a readable file: %s" % ref)
    try:
        data = target.read_bytes()
    except OSError:
        raise CatalogError("unreadable reference: %s" % ref)
    return data


class _Row:
    def __init__(self, profile, kind, aliases, refs, reason, line_no):
        self.profile = profile
        self.kind = kind
        self.aliases = aliases
        self.refs = refs
        self.reason = reason
        self.line_no = line_no


def _split_cells(line):
    return [c.strip() for c in line.strip().strip("|").split("|")]


def _is_separator(cells):
    return bool(cells) and all(re.fullmatch(r":?-{2,}:?", c or "-") for c in cells)


def _parse_catalog(root):
    path = root / CATALOG_REL
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        raise CatalogError("cannot read route catalog: %s" % exc)
    if text.count(MARKER_START) != 1 or text.count(MARKER_END) != 1:
        raise CatalogError("route catalog markers must occur exactly once")
    start = text.index(MARKER_START) + len(MARKER_START)
    end = text.index(MARKER_END)
    if end < start:
        raise CatalogError("route catalog markers are out of order")
    block = text[start:end]
    marker_line_start = text[:text.index(MARKER_START)].count("\n") + 1

    lines = block.splitlines()
    header_idx = None
    for i, line in enumerate(lines):
        if not line.strip().startswith("|"):
            continue
        if i + 1 >= len(lines) or not lines[i + 1].strip().startswith("|"):
            continue
        if not _is_separator(_split_cells(lines[i + 1])):
            continue
        cells = _split_cells(line)
        if [c.lower() for c in cells] == ["profile", "kind", "aliases",
                                          "required_refs", "reason"]:
            header_idx = i
            break
    if header_idx is None:
        raise CatalogError("route catalog table header is missing or malformed")

    rows = []
    seen_profiles = set()
    for i, line in enumerate(lines):
        if i <= header_idx + 1:
            continue
        if not line.strip():
            break
        if not line.strip().startswith("|"):
            break
        cells = _split_cells(line)
        if _is_separator(cells):
            continue
        if len(cells) != 5:
            raise CatalogError("route catalog row must have 5 columns")
        profile, kind, aliases_cell, refs_cell, reason = [c.strip() for c in cells]
        if not profile or not kind or not reason:
            raise CatalogError("route catalog row has an empty required field")
        if profile in seen_profiles:
            raise CatalogError("duplicate profile in route catalog: %s" % profile)
        seen_profiles.add(profile)
        aliases = [a.strip() for a in aliases_cell.split(";") if a.strip()]
        refs = [r.strip() for r in refs_cell.split(";") if r.strip()]
        if not aliases:
            raise CatalogError("route catalog row has no aliases: %s" % profile)
        if not refs:
            raise CatalogError("route catalog row has no required_refs: %s" % profile)
        source_line_no = marker_line_start + i
        rows.append(_Row(profile, kind, aliases, refs, reason, source_line_no))
    return rows, text


def _source_versions(root):
    versions = {}
    candidates = {
        "scripts/lib_doctor.py": root / "scripts" / "lib_doctor.py",
        "scripts/production_task_profile.py": root / "scripts" / "production_task_profile.py",
        "scripts/compile_shot_graph.py": root / "scripts" / "compile_shot_graph.py",
        "schemas/production_contract.schema.json": root / "schemas" / "production_contract.schema.json",
        "scripts/compile_production_contract.py": root / "scripts" / "compile_production_contract.py",
        "references/run-sheet-part2.md": root / "references" / "run-sheet-part2.md",
    }
    try:
        route_refs = route_files(root)
    except CatalogError:
        route_refs = ()
    for rel in route_refs:
        candidates["references/" + rel] = root / "references" / rel
    for rel, path in candidates.items():
        try:
            versions[rel] = _sha256_file(path)
        except (OSError, RuntimeError):
            versions[rel] = ""
    return versions


def resolve_route(skill_root, key):
    root = Path(skill_root).expanduser()
    try:
        root = root.resolve(strict=False)
    except (OSError, RuntimeError):
        pass

    base_result = {
        "scope": "knowledge_routing_recommendation",
        "production_readiness": "not_evaluated",
        "generation_authorized": False,
        "key": key,
    }

    empty_load = {"raw_bytes": 0, "unique_bytes": 0, "duplicate_bytes": 0}

    try:
        route_files(root)
    except CatalogError as exc:
        return dict(base_result, status="invalid_catalog", exit_code=1,
                    error=str(exc), matched=False, profile=None,
                    matched_profile=None, aliases=[], required_refs=[], reason="",
                    files=[], raw_bytes=0, unique_bytes=0, duplicate_bytes=0,
                    load=dict(empty_load), source_versions=_source_versions(root))

    try:
        rows, catalog_text = _parse_catalog(root)
    except CatalogError as exc:
        return dict(base_result, status="invalid_catalog", exit_code=1,
                    error=str(exc), matched=False, profile=None,
                    matched_profile=None, aliases=[], required_refs=[],
                    reason="", files=[], raw_bytes=0, unique_bytes=0,
                    duplicate_bytes=0, load=dict(empty_load),
                    source_versions=_source_versions(root))

    try:
        expected = _expected_profiles(root)
    except Exception as exc:
        return dict(base_result, status="invalid_catalog", exit_code=1,
                    error="cannot derive capabilities: %s" % exc, matched=False,
                    profile=None, matched_profile=None, aliases=[],
                    required_refs=[], reason="", files=[], raw_bytes=0,
                    unique_bytes=0, duplicate_bytes=0, load=dict(empty_load),
                    source_versions=_source_versions(root))
    actual = {row.profile for row in rows}
    if actual != expected:
        return dict(base_result, status="invalid_catalog", exit_code=1,
                    error="catalog profiles %r do not match derived capabilities %r"
                    % (sorted(actual), sorted(expected)), matched=False,
                    profile=None, matched_profile=None, aliases=[],
                    required_refs=[], reason="", files=[], raw_bytes=0,
                    unique_bytes=0, duplicate_bytes=0, load=dict(empty_load),
                    source_versions=_source_versions(root))

    for row in rows:
        ref_set = set(row.refs)
        for core in CORE_REFS:
            if core not in ref_set:
                return dict(base_result, status="invalid_catalog", exit_code=1,
                            error="profile %s is missing required core reference %s"
                            % (row.profile, core), matched=False, profile=None,
                            matched_profile=None, aliases=[], required_refs=[],
                            reason="", files=[], raw_bytes=0, unique_bytes=0,
                            duplicate_bytes=0, load=dict(empty_load),
                            source_versions=_source_versions(root))

    alias_owner = {}
    rows_by_profile = {row.profile: row for row in rows}
    for row in rows:
        for alias in row.aliases:
            norm = alias.strip().lower()
            if norm in alias_owner and alias_owner[norm] != row.profile:
                return dict(base_result, status="invalid_catalog", exit_code=1,
                            error="alias collision: %r" % alias, matched=False,
                            profile=None, matched_profile=None, aliases=[],
                            required_refs=[], reason="", files=[], raw_bytes=0,
                            unique_bytes=0, duplicate_bytes=0,
                            load=dict(empty_load),
                            source_versions=_source_versions(root))
            alias_owner[norm] = row.profile
        if row.profile.lower() not in [a.strip().lower() for a in row.aliases]:
            return dict(base_result, status="invalid_catalog", exit_code=1,
                        error="profile is not queryable by its own name: %s"
                        % row.profile, matched=False, profile=None,
                        matched_profile=None, aliases=[], required_refs=[],
                        reason="", files=[], raw_bytes=0, unique_bytes=0,
                        duplicate_bytes=0, load=dict(empty_load),
                        source_versions=_source_versions(root))

    empty_aliases, silent_aliases = _extract_shot_kind_aliases(root)
    if "empty" in rows_by_profile:
        for alias in empty_aliases:
            if alias not in rows_by_profile["empty"].aliases:
                return dict(base_result, status="invalid_catalog", exit_code=1,
                            error="missing derived empty-shot alias: %s" % alias,
                            matched=False, profile=None, matched_profile=None,
                            aliases=[], required_refs=[], reason="", files=[],
                            raw_bytes=0, unique_bytes=0, duplicate_bytes=0,
                            load=dict(empty_load),
                            source_versions=_source_versions(root))
    if "silent" in rows_by_profile:
        for alias in silent_aliases:
            if alias not in rows_by_profile["silent"].aliases:
                return dict(base_result, status="invalid_catalog", exit_code=1,
                            error="missing derived silent-shot alias: %s" % alias,
                            matched=False, profile=None, matched_profile=None,
                            aliases=[], required_refs=[], reason="", files=[],
                            raw_bytes=0, unique_bytes=0, duplicate_bytes=0,
                            load=dict(empty_load),
                            source_versions=_source_versions(root))

    file_bytes = {}
    file_sha = {}
    file_origins = {}
    for row in rows:
        for ref in row.refs:
            try:
                normalized = _normalize_ref(ref)
            except CatalogError as exc:
                return dict(base_result, status="invalid_catalog", exit_code=1,
                            error=str(exc), matched=False, profile=None,
                            matched_profile=None, aliases=[], required_refs=[],
                            reason="", files=[], raw_bytes=0, unique_bytes=0,
                            duplicate_bytes=0, load=dict(empty_load),
                            source_versions=_source_versions(root))
            try:
                data = _read_ref_bytes(root, normalized)
            except CatalogError as exc:
                return dict(base_result, status="invalid_catalog", exit_code=1,
                            error=str(exc), matched=False, profile=None,
                            matched_profile=None, aliases=[], required_refs=[],
                            reason="", files=[], raw_bytes=0, unique_bytes=0,
                            duplicate_bytes=0, load=dict(empty_load),
                            source_versions=_source_versions(root))
            if normalized not in file_bytes:
                file_bytes[normalized] = data
                file_sha[normalized] = _sha256_bytes(data)
                file_origins[normalized] = []
            file_origins[normalized].append({
                "source": CATALOG_REL,
                "line": row.line_no,
                "reason": "required_refs entry for profile %s" % row.profile,
            })

    query = "" if key is None else str(key).strip()
    query_norm = query.lower()
    matched_profile = alias_owner.get(query_norm)
    matched = matched_profile is not None
    if matched and matched_profile not in rows_by_profile:
        matched = False
        matched_profile = None

    if not matched:
        return dict(base_result, status="no_match", exit_code=3, matched=False,
                    profile=None, matched_profile=None, aliases=[],
                    required_refs=[], reason="", files=[], raw_bytes=0,
                    unique_bytes=0, duplicate_bytes=0, load=dict(empty_load),
                    source_versions=_source_versions(root))

    row = rows_by_profile[matched_profile]
    normalized_matched = [_normalize_ref(r) for r in row.refs]
    matched_unique = sorted(set(normalized_matched))
    matched_files = []
    for name in matched_unique:
        matched_files.append({
            "path": name,
            "bytes": len(file_bytes[name]),
            "sha256": file_sha[name],
            "origins": file_origins.get(name, []),
        })
    raw_bytes = sum(len(file_bytes[name]) for name in normalized_matched)
    unique_bytes = sum(len(file_bytes[name]) for name in matched_unique)
    duplicate_bytes = raw_bytes - unique_bytes

    supported = set(_expected_profiles(root))
    if "rework" not in _valid_task_types(root):
        supported.discard("rework")
    status = "matched" if matched_profile in supported else "unsupported"
    exit_code = 0 if status == "matched" else 3

    load = {
        "raw_bytes": raw_bytes,
        "unique_bytes": unique_bytes,
        "duplicate_bytes": duplicate_bytes,
    }

    return dict(
        base_result,
        status=status,
        exit_code=exit_code,
        matched=True,
        profile=matched_profile,
        matched_profile=matched_profile,
        aliases=list(row.aliases),
        required_refs=normalized_matched,
        reason=row.reason,
        files=matched_files,
        raw_bytes=raw_bytes,
        unique_bytes=unique_bytes,
        duplicate_bytes=duplicate_bytes,
        load=load,
        source_versions=_source_versions(root),
    )


def library_index_text(skill_root):
    """Read the entry and its one explicitly declared navigation index."""
    root = Path(skill_root).resolve()
    entry = _read_ref_bytes(root, "SKILL.md").decode("utf-8")
    markers = re.findall(r"<!--\s*library-index:\s*([^\s>]+)\s*-->", entry)
    if "library-index:" not in entry:
        return entry
    if len(markers) != 1 or entry.count("library-index:") != 1:
        raise CatalogError("exactly one library-index is required")
    ref = _normalize_ref(markers[0])
    if ref == "SKILL.md":
        raise CatalogError("library-index cannot reference itself")
    index = _read_ref_bytes(root, ref).decode("utf-8")
    if "library-index:" in index:
        raise CatalogError("nested or cyclic library-index is not allowed")
    return entry + "\n" + index


def _context_fingerprint(value):
    return _sha256_bytes(json.dumps(value, ensure_ascii=False, sort_keys=True,
                                   separators=(",", ":")).encode("utf-8"))


def plan_context(skill_root, profile, features=(), *, intent=None,
                 reverse_spec=None, extra_refs=()):
    """Plan complete source files, not understanding, readiness or permission."""
    root = Path(skill_root).resolve()
    request = {"profile": profile, "features": list(features) if not isinstance(features, str)
               else [features], "intent": intent, "reverse_spec": reverse_spec,
               "extra_refs": list(extra_refs)}
    result = {"scope": "task_context_plan", "status": "INVALID_CONTEXT_PLAN",
              "reading_compliance": "NOT_EVALUATED",
              "production_readiness": "NOT_EVALUATED", "generation_authorized": False,
              "request": request, "files": [], "features": [], "coverage": [],
              "unresolved": [], "applicability_rules": [],
              "dependency_completeness": "AGENT_MUST_REVIEW_APPLICABILITY"}

    try:
        law = _read_ref_bytes(root, "references/governance-law.md").decode("utf-8")
        if "<!-- reading-policy: task-closure/v1 -->" not in law:
            raise CatalogError("L1 task-closure policy has not been adopted")
        meta_ref = "references/context-dependencies.json"
        meta = json.loads(_read_ref_bytes(root, meta_ref).decode("utf-8"))
        if meta.get("format") != "context-dependencies/v1":
            raise CatalogError("unknown context dependency format")
        if set(meta["profile_extensions"]) != _expected_profiles(root):
            raise CatalogError("context profiles do not match actual routing capabilities")
        kinds = set(_literal_assignment(root, "scripts/compile_prompt_packages.py",
                                        "CONSTRAINT_DELIVERY_BY_KIND"))
        if set(meta["constraint_features"]) != kinds:
            raise CatalogError("constraint context mapping is incomplete")
        if not {"references/context-reading.md", meta_ref}.issubset(meta["common"]):
            raise CatalogError("required context sources are missing")

        base = resolve_route(root, profile)
        if base["status"] not in ("matched", "unsupported"):
            raise CatalogError(base.get("error") or "unknown task profile")
        resolved_profile = base["profile"]
        result.update(profile=resolved_profile, production_support=(
            "UNSUPPORTED" if base["status"] == "unsupported" else "NOT_EVALUATED"))
        selected = set(request["features"])
        coverage = result["coverage"]

        def cover(key, triggers, source="structured_intent"):
            selected.update(triggers)
            coverage.append({"requirement_id": key, "features": list(triggers),
                             "source": source})

        if resolved_profile in ("empty", "silent", "no_dialogue"):
            selected.add(resolved_profile)
        if resolved_profile == "mirror":
            selected.add("reverse")
        if intent is not None:
            if not isinstance(intent, dict):
                raise CatalogError("intent must be an object")
            task = intent.get("task_type")
            if task and resolved_profile in _valid_task_types(root) and task != resolved_profile:
                result["unresolved"].append("task profile contradicts intent task_type")
            empty_aliases, silent_aliases = _extract_shot_kind_aliases(root)

            def kind_features(key, value):
                kind = str(value or "").strip().lower()
                if kind in empty_aliases:
                    return ["empty"]
                if kind in silent_aliases:
                    return ["silent"]
                if kind not in ("", "standard"):
                    result["unresolved"].append("unknown shot_kind %s (%s)" % (key, kind))
                return []

            def dialogue_features(key, value):
                if not isinstance(value, bool):
                    result["unresolved"].append("no_dialogue must be boolean: " + key)
                    return []
                return ["no_dialogue"] if value else ["sound"]

            for key, decision in (intent.get("decisions") or {}).items():
                triggers = meta["decision_features"].get(key)
                if triggers is None:
                    result["unresolved"].append("unmapped decision: " + key)
                    continue
                triggers = list(triggers)
                value = decision.get("value") if isinstance(decision, dict) else decision
                if key == "visual_style" and isinstance(value, dict) and value.get("register") in (
                        "stylized", "graphic", "illustration"):
                    triggers.append("stylized")
                elif key == "no_dialogue":
                    triggers = dialogue_features("decision:" + key, value)
                elif key == "shot_kind":
                    triggers = kind_features("decision:" + key, value)
                elif key == "sound_mode" and value == "silent":
                    triggers.append("silent")
                cover("decision:" + key, triggers)
            if "no_dialogue" in intent:
                cover("no_dialogue", dialogue_features("no_dialogue", intent["no_dialogue"]))
            for i, constraint in enumerate(intent.get("constraints") or []):
                key = constraint.get("id") or "constraint:%d" % i
                kind = constraint.get("kind")
                triggers = meta["constraint_features"].get(kind)
                if triggers is None:
                    result["unresolved"].append("unmapped requirement %s (%s)" % (key, kind))
                else:
                    cover(key, triggers)
            def cover_state(key, values):
                state_kinds = set(_literal_assignment(root, "scripts/compile_shot_graph.py", "WORLD_STATE_KINDS"))
                triggers = {"continuity"}
                if not isinstance(values, dict):
                    result["unresolved"].append("world state must be an object: " + key)
                    return
                for value in values.values():
                    if value == "unchanged":
                        continue
                    kind = value.get("kind") if isinstance(value, dict) else None
                    if not isinstance(kind, str) or kind not in state_kinds:
                        result["unresolved"].append("unknown world-state kind: " + key)
                    elif kind == "dialogue":
                        triggers.add("sound")
                    elif kind in ("identity", "prop"):
                        triggers.add("assets")
                    elif kind == "physical":
                        triggers.add("motion")
                    elif kind == "frame":
                        triggers.add("camera")
                cover(key, sorted(triggers))
            if "world_state_initial" in intent:
                cover_state("world_state_initial", intent["world_state_initial"])
            project_sound = intent.get("sound")
            if project_sound:
                if not isinstance(project_sound, dict):
                    raise CatalogError("project sound must be an object")
                cover("sound", ["sound"] + (["silent"] if project_sound.get("mode") == "silent" else []))
            for i, shot in enumerate(intent.get("shots") or []):
                key = str(shot.get("id") or i)
                if "world_state_delta" in shot:
                    cover_state(key + ":world_state_delta", shot["world_state_delta"])
                if "world_state_refs" in shot:
                    cover(key + ":world_state_refs", ["continuity"])
                kind = str(shot.get("shot_kind") or shot.get("kind") or "").lower()
                if kind:
                    cover(key + ":shot_kind", kind_features(key, kind))
                if "no_dialogue" in shot:
                    cover(key + ":no_dialogue", dialogue_features(key, shot["no_dialogue"]))
                shot_sound = shot.get("sound")
                if shot_sound:
                    if not isinstance(shot_sound, dict):
                        raise CatalogError("shot sound must be an object")
                    cover(key + ":sound", ["sound"])
                if kind in silent_aliases or (shot_sound or {}).get("mode") == "silent":
                    cover(key + ":silence", ["silent"])
                for field, feature in meta["craft_features"].items():
                    if shot.get(field):
                        cover(key + ":" + field, [feature])
                if shot.get("asset_refs") is not None:
                    cover(key + ":asset_refs", ["assets", "continuity"])
            if intent.get("entities"):
                cover("entities", ["assets"])

        refs = set(base["required_refs"]) | set(meta["common"])
        refs.update(meta["profile_extensions"][resolved_profile])
        feature_refs = {}
        for feature in sorted(selected):
            if feature in meta["feature_profiles"]:
                route = resolve_route(root, meta["feature_profiles"][feature])
                if route["status"] not in ("matched", "unsupported"):
                    raise CatalogError("invalid feature route: " + feature)
                feature_refs[feature] = (set(route["required_refs"]) |
                                         set(meta["profile_extensions"][route["profile"]]))
                refs.update(feature_refs[feature])
            elif feature in meta["features"]:
                feature_refs[feature] = set(meta["features"][feature])
                refs.update(feature_refs[feature])
            else:
                raise CatalogError("unknown feature: " + str(feature))
        for rule, details in meta["applicability"].items():
            if not details["features"] or selected.intersection(details["features"]):
                result["applicability_rules"].append(rule)
                refs.update(details["refs"])
        refs.update(extra_refs)

        if "reverse" in selected:
            spec = reverse_spec or {}
            for key in ("mode", "deliverable", "source_access"):
                if not spec.get(key):
                    result["unresolved"].append("reverse declaration missing " + key)
            mode, access = spec.get("mode"), spec.get("source_access")
            if mode and mode not in ("content_reverse", "copy_reverse", "source_replica",
                                     "rule_distill", "production_build"):
                result["unresolved"].append("unknown reverse mode")
            if spec.get("deliverable") and spec["deliverable"] not in ("mirror", "production_plan"):
                result["unresolved"].append("unknown reverse deliverable")
            if access and access not in ("original_readback", "copy_readback",
                                        "public_media", "text_only", "none"):
                result["unresolved"].append("unknown source access")
            if mode == "source_replica" and access != "original_readback":
                result["unresolved"].append(
                    "source_replica: original access unresolved; contract sections2/3 conflict for copies")
            if mode == "copy_reverse" and access not in ("copy_readback", "original_readback"):
                result["unresolved"].append("copy readback has not been declared")
            if str(profile) in ("source_replica", "copy_reverse") and mode != profile:
                result["unresolved"].append("reverse alias contradicts declared mode")
            result["declared_reverse_spec"] = spec
            result["fidelity_permission"] = "NOT_EVALUATED"

        def closure(sources):
            pending, normalized = list(sources), set()
            while pending:
                ref = _normalize_ref(pending.pop())
                if ref not in normalized:
                    normalized.add(ref)
                    pending.extend(meta["requires"].get(ref, []))
            return normalized

        for ref in sorted(closure(refs)):
            data = _read_ref_bytes(root, ref)
            try:
                data.decode("utf-8")
            except UnicodeError as exc:
                raise CatalogError("context source is not UTF8: " + ref) from exc
            result["files"].append({"path": ref, "sha256": _sha256_bytes(data),
                                    "bytes": len(data)})
        result["features"] = sorted(selected)
        for row in coverage:
            sources = set(base["required_refs"]) | set(meta["common"])
            sources.update(meta["profile_extensions"][resolved_profile])
            for feature in row["features"]:
                sources.update(feature_refs[feature])
            for details in meta["applicability"].values():
                if not details["features"] or set(row["features"]).intersection(details["features"]):
                    sources.update(details["refs"])
            row["refs"] = sorted(closure(sources))
        result["source_versions"] = dict(base["source_versions"])
        result["source_versions"][meta_ref] = _sha256_file(root / meta_ref)
        for source in ("scripts/knowledge_routes.py", "scripts/compile_prompt_packages.py"):
            result["source_versions"][source] = _sha256_file(root / source)
        result["bytes"] = sum(item["bytes"] for item in result["files"])
        result["status"] = "NEEDS_DECISION" if result["unresolved"] else "PLAN_ONLY"
    except (CatalogError, OSError, ValueError, KeyError, TypeError) as exc:
        result["error"] = str(exc)
        result["unresolved"].append(str(exc))
    result["plan_fingerprint"] = _context_fingerprint(result)
    return result


def check_read_evidence(skill_root, plan, receipt, capture_root, session_id):
    """Validate source captures only; never certify that an Agent understood."""
    request = plan.get("request") or {}
    fresh = plan_context(skill_root, request.get("profile"),
                         request.get("features", ()), intent=request.get("intent"),
                         reverse_spec=request.get("reverse_spec"),
                         extra_refs=request.get("extra_refs", ()))
    paths = [item["path"] for item in fresh["files"]]
    base = {"reading_compliance": "NOT_EVALUATED",
            "production_readiness": "NOT_EVALUATED", "generation_authorized": False,
            "reusable": [], "needs_full_read": list(paths), "failures": []}
    if plan != fresh or fresh["status"] != "PLAN_ONLY":
        return dict(base, status="REPLAN_REQUIRED")
    if not isinstance(receipt, dict) or not session_id or receipt.get("session_id") != session_id:
        return dict(base, status="READS_REQUIRED")
    reads = receipt.get("reads")
    if not isinstance(reads, list):
        return dict(base, status="READS_REQUIRED")
    mapping = {}
    for row in reads:
        if not isinstance(row, dict) or row.get("path") in mapping:
            return dict(base, status="READS_REQUIRED", failures=["invalid or duplicate read record"])
        mapping[row.get("path")] = row
    root = Path(capture_root).resolve()
    for item in fresh["files"]:
        ref = item["path"]
        row = mapping.get(ref) or {}
        try:
            if row.get("complete") is not True or row.get("sha256") != item["sha256"]:
                raise CatalogError("complete source evidence is missing")
            capture = _read_ref_bytes(root, row.get("capture_path"))
            if _sha256_bytes(capture) != item["sha256"]:
                raise CatalogError("capture is partial, stale or changed")
            base["reusable"].append(ref)
            base["needs_full_read"].remove(ref)
        except (CatalogError, OSError, TypeError, ValueError) as exc:
            base["failures"].append({"path": ref, "reason": str(exc)})
    return dict(base, status="SOURCE_EVIDENCE_VALID" if not base["needs_full_read"] else "READS_REQUIRED")


def _context_main():
    import argparse
    parser = argparse.ArgumentParser(description="AIGC source-context planning; no production or generation")
    parser.add_argument("--profile")
    parser.add_argument("--feature", action="append", default=[])
    parser.add_argument("--extra-ref", action="append", default=[])
    parser.add_argument("--intent")
    parser.add_argument("--reverse-spec")
    parser.add_argument("--plan")
    parser.add_argument("--receipt")
    parser.add_argument("--capture-root")
    parser.add_argument("--session")
    parser.add_argument("--out")
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    def load(path):
        return json.loads(Path(path).read_text(encoding="utf-8")) if path else None
    if args.plan:
        if not all((args.receipt, args.capture_root, args.session)):
            parser.error("--plan requires --receipt, --capture-root and --session")
        result = check_read_evidence(root, load(args.plan), load(args.receipt),
                                     args.capture_root, args.session)
    else:
        if not args.profile:
            parser.error("--profile is required for a new plan")
        result = plan_context(root, args.profile, args.feature, intent=load(args.intent),
                              reverse_spec=load(args.reverse_spec), extra_refs=args.extra_ref)
    text = json.dumps(result, ensure_ascii=False, indent=2) + "\n"
    if args.out:
        Path(args.out).write_text(text, encoding="utf-8")
    else:
        print(text, end="")
    return 0 if result["status"] in ("PLAN_ONLY", "SOURCE_EVIDENCE_VALID") else 1


if __name__ == "__main__":
    raise SystemExit(_context_main())
