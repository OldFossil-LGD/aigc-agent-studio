import contextlib
import copy
import io
import json
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts import audit_prompt
from scripts import knowledge_routes as routes

ROOT = Path(__file__).resolve().parents[1]
TEMP = Path(tempfile.gettempdir())


class ContextReadingTests(unittest.TestCase):
    def setUp(self):
        TEMP.mkdir(exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(dir=TEMP)
        self.work = Path(self.temp.name)
        self.assertTrue(self.work.resolve().is_relative_to(TEMP.resolve()))

    def tearDown(self):
        self.temp.cleanup()

    def plan(self, profile="prompt_only", features=(), root=ROOT, **kw):
        self.assertTrue(callable(getattr(routes, "plan_context", None)),
                        "task closure planner is missing")
        return routes.plan_context(root, profile, features, **kw)

    def clone(self):
        target = self.work / "skill"
        target.mkdir()
        for name in ("SKILL.md", "scripts", "references", "schemas", "samples"):
            source = ROOT / name
            if source.is_dir():
                shutil.copytree(source, target / name,
                                ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
            else:
                shutil.copy2(source, target / name)
        return target

    def captures(self, plan):
        capture_root = self.work / "captures"
        capture_root.mkdir()
        reads = []
        for i, item in enumerate(plan["files"]):
            name = "%03d.txt" % i
            (capture_root / name).write_bytes((ROOT / item["path"]).read_bytes())
            reads.append({"path": item["path"], "sha256": item["sha256"],
                          "capture_path": name, "complete": True})
        return capture_root, {"session_id": "s1", "reads": reads}

    def check(self, plan, receipt, captures, session="s1", root=ROOT):
        self.assertTrue(callable(getattr(routes, "check_read_evidence", None)))
        return routes.check_read_evidence(root, plan, receipt, captures, session)

    def test_clone_uses_runtime_package_not_nested_historical_archives(self):
        source = self.work / "installed_like_skill"
        source.mkdir()
        (source / "SKILL.md").write_text("entry", encoding="utf-8")
        for name in ("scripts", "references", "schemas", "samples"):
            (source / name).mkdir()
            (source / name / "kept.txt").write_text(name, encoding="utf-8")
        archive = source / ".snapshots/backup-before-tidy/.snapshots"
        archive.mkdir(parents=True)
        (archive / "history.json").write_text("{}", encoding="utf-8")
        with patch(__name__ + ".ROOT", source):
            target = self.clone()
        self.assertFalse((target / ".snapshots").exists())
        self.assertEqual((target / "SKILL.md").read_text(encoding="utf-8"), "entry")
        for name in ("scripts", "references", "schemas", "samples"):
            self.assertTrue((target / name / "kept.txt").is_file())

    def test_aliases_are_derived_from_graph_constants_in_use(self):
        from scripts.compile_shot_graph import EMPTY_SHOT_KINDS, SILENT_SHOT_KINDS
        self.assertEqual(routes._extract_shot_kind_aliases(ROOT),
                         (EMPTY_SHOT_KINDS, SILENT_SHOT_KINDS))
        for alias in EMPTY_SHOT_KINDS | SILENT_SHOT_KINDS:
            with self.subTest(alias=alias):
                self.assertEqual(routes.resolve_route(ROOT, alias)["status"], "matched")
        target = self.clone()
        graph = target / "scripts/compile_shot_graph.py"
        original = graph.read_text(encoding="utf-8")
        graph.write_text(original.replace('"visual_only"}', '"visual_only", "new_empty_alias"}'),
                         encoding="utf-8")
        self.assertIn("new_empty_alias", routes._extract_shot_kind_aliases(target)[0])
        self.assertEqual(routes.resolve_route(target, "prompt_only")["status"], "invalid_catalog")

    def test_coverage_includes_profile_rules_and_transitive_dependencies(self):
        result = self.plan(intent={"shots": [{"id": "s1", "shot_kind": "silent",
                                              "asset_refs": []}]})
        self.assertEqual(result["status"], "PLAN_ONLY", result)
        rows = {row["requirement_id"]: set(row["refs"]) for row in result["coverage"]}
        self.assertIn("references/sound-craft.md", rows["s1:silence"])
        self.assertIn("references/asset-prompt-spec-part2.md", rows["s1:asset_refs"])

    def test_six_task_contexts_keep_mode_specific_rules(self):
        cases = [
            ("prompt_only", [], "references/stage1-delivery-entry.md", {}),
            ("single_shot", ["performance"], "references/performance-craft.md", {}),
            ("prompt_only", ["empty", "silent", "camera", "stylized"],
             "references/motion-control.md", {}),
            ("full_film", ["continuity"], "references/offline-continuity-entry.md", {}),
            ("prompt_only", ["sound"], "references/sound-narrative.md", {}),
            ("mirror", ["reverse"], "references/reverse-fidelity-contract.md",
             {"reverse_spec": {"mode": "copy_reverse", "deliverable": "mirror",
                               "source_access": "copy_readback"}}),
        ]
        for profile, features, required, kw in cases:
            with self.subTest(profile=profile, features=features):
                result = self.plan(profile, features, **kw)
                self.assertEqual(result["status"], "PLAN_ONLY", result)
                paths = [x["path"] for x in result["files"]]
                self.assertIn(required, paths)
                self.assertEqual(len(paths), len(set(paths)))
                self.assertFalse(result["generation_authorized"])
                self.assertEqual(result["reading_compliance"], "NOT_EVALUATED")

    def test_fixed_silent_stylized_empty_context_is_joint_not_alternative(self):
        plan = self.plan(features=["empty", "silent", "camera", "stylized"])
        paths = {x["path"] for x in plan["files"]}
        self.assertTrue({"references/sound-craft.md", "references/motion-control.md",
                         "references/style-library-index.md",
                         "references/stylized-look-craft.md"}.issubset(paths))
        self.assertIn("user_lock_precedes_craft_default", plan["applicability_rules"])

    def test_unknown_feature_and_unknown_requirement_do_not_disappear(self):
        self.assertNotEqual(self.plan(features=["unknown_feature"])["status"], "PLAN_ONLY")
        intent = {"task_type": "prompt_only", "constraints": [
            {"id": "alien", "kind": "unknown_requirement", "text": "a locked requirement",
             "source": "user_explicit", "locked": True}]}
        result = self.plan(intent=intent)
        self.assertNotEqual(result["status"], "PLAN_ONLY")
        self.assertTrue(result["unresolved"])

    def test_intent_fields_trigger_dependencies_and_coverage(self):
        intent = {"task_type": "prompt_only", "decisions": {
            "visual_style": {"value": {"text": "水墨", "register": "stylized"},
                             "source": "user_explicit", "locked": True}},
            "constraints": [{"id": "camera1", "kind": "camera", "text": "固定机位",
                             "source": "user_explicit", "locked": True}],
            "shots": [{"id": "s1", "shot_kind": "empty", "sound": {"mode": "silent"},
                       "performance": "眼片回避对方"}]}
        result = self.plan(intent=intent)
        self.assertEqual(result["status"], "PLAN_ONLY", result)
        self.assertTrue({"camera", "silent", "stylized", "performance", "empty"}
                        .issubset(result["features"]))
        self.assertTrue(any(x["requirement_id"] == "camera1" for x in result["coverage"]))

    def test_unmapped_decision_and_shot_kind_are_unresolved(self):
        for intent in [
                {"decisions": {"unknown_lens_prohibition": {"value": "no anamorphic", "locked": True}}},
                {"shots": [{"id": "s1", "shot_kind": "unknown_macro_empty"}]}]:
            with self.subTest(intent=intent):
                result = self.plan(intent=intent)
                self.assertEqual(result["status"], "NEEDS_DECISION", result)
                self.assertTrue(result["unresolved"])

    def test_shot_dialogue_lock_and_craft_consumer_entry_are_routed(self):
        result = self.plan(intent={"shots": [{"id": "s1", "no_dialogue": True}]})
        self.assertEqual(result["status"], "PLAN_ONLY", result)
        self.assertIn("no_dialogue", result["features"])
        self.assertIn("s1:no_dialogue", [row["requirement_id"] for row in result["coverage"]])
        self.assertIn("references/craft-delivery-entry.md", [row["path"] for row in result["files"]])

    def test_existing_sample_decisions_and_standard_shot_remain_supported(self):
        for source in [ROOT / "samples/papercut_empty_shot_intent.json",
                       *(ROOT / "samples/craft_pairs/intents").glob("*.json")]:
            with self.subTest(source=source.name):
                intent = json.loads(source.read_text(encoding="utf-8"))
                result = self.plan(intent=intent)
                self.assertEqual(result["status"], "PLAN_ONLY", result.get("unresolved"))
        self.assertEqual(self.plan(intent={"shots": [{"id": "s1", "shot_kind": "standard"}]})["status"],
                         "PLAN_ONLY")

    def test_structured_sound_at_project_and_shot_levels_is_covered(self):
        for intent, requirement in [
                ({"sound": {"mode": "ambience_only"}}, "sound"),
                ({"sound": {"mode": "silent"}}, "sound"),
                ({"shots": [{"id": "s1", "sound": {"mode": "dialogue_allowed"}}]}, "s1:sound")]:
            with self.subTest(intent=intent):
                result = self.plan(intent=intent)
                self.assertEqual(result["status"], "PLAN_ONLY", result)
                rows = {row["requirement_id"]: row for row in result["coverage"]}
                self.assertIn(requirement, rows)
                self.assertIn("references/sound-craft.md", rows[requirement]["refs"])
                if intent.get("sound", {}).get("mode") == "silent":
                    self.assertIn("silence_overrides_default_ambience", result["applicability_rules"])

    def test_unsafe_extra_reference_and_unknown_task_fail(self):
        self.assertNotEqual(self.plan(extra_refs=["../external.md"])["status"], "PLAN_ONLY")
        self.assertNotEqual(self.plan("unknown_task")["status"], "PLAN_ONLY")

    def test_missing_direct_exception_dependency_fails(self):
        target = self.clone()
        (target / "references/performance-vocabulary.md").unlink()
        result = self.plan("single_shot", ["performance"], target)
        self.assertNotEqual(result["status"], "PLAN_ONLY")

    def test_existing_L1_cannot_be_bypassed_by_router(self):
        target = self.clone()
        law = target / "references/governance-law.md"
        law.write_text(law.read_text(encoding="utf-8").replace(
            "<!-- reading-policy: task-closure/v1 -->", ""), encoding="utf-8")
        self.assertNotEqual(self.plan(root=target)["status"], "PLAN_ONLY")

    def test_copy_access_never_authorizes_original_source_replica(self):
        result = self.plan("mirror", ["reverse"], reverse_spec={
            "mode": "source_replica", "deliverable": "mirror",
            "source_access": "copy_readback"})
        self.assertNotEqual(result["status"], "PLAN_ONLY")
        self.assertTrue(result["unresolved"])

    def test_full_capture_only_reuses_same_session_unchanged_sources(self):
        plan = self.plan()
        captures, receipt = self.captures(plan)
        result = self.check(plan, receipt, captures)
        self.assertEqual(result["status"], "SOURCE_EVIDENCE_VALID", result)
        self.assertEqual(set(result["reusable"]), {x["path"] for x in plan["files"]})
        other = self.check(plan, receipt, captures, "another_session")
        self.assertEqual(other["reusable"], [])
        self.assertEqual(other["status"], "READS_REQUIRED")

    def test_hash_only_partial_and_traversal_captures_are_not_read_evidence(self):
        plan = self.plan()
        captures, receipt = self.captures(plan)
        for mutation in ("hash_only", "partial", "traversal"):
            with self.subTest(mutation=mutation):
                bad = copy.deepcopy(receipt)
                if mutation == "hash_only":
                    bad["reads"][0].pop("capture_path")
                elif mutation == "partial":
                    (captures / bad["reads"][0]["capture_path"]).write_text("partial", encoding="utf-8")
                else:
                    bad["reads"][0]["capture_path"] = "../outside.txt"
                result = self.check(plan, bad, captures)
                self.assertNotEqual(result["status"], "SOURCE_EVIDENCE_VALID")
                self.assertTrue(result["needs_full_read"])

    def test_plan_tampering_cannot_claim_zero_required_reads(self):
        plan = self.plan()
        captures, receipt = self.captures(plan)
        bad = copy.deepcopy(plan)
        bad["files"] = []
        self.assertNotEqual(self.check(bad, receipt, captures)["status"], "SOURCE_EVIDENCE_VALID")

    def test_dependency_changed_requires_new_plan_and_full_new_text(self):
        target = self.clone()
        plan = self.plan(root=target)
        capture_root = self.work / "local_caps"
        capture_root.mkdir()
        receipt = {"session_id": "s1", "reads": []}
        for i, item in enumerate(plan["files"]):
            name = "%d.txt" % i
            (capture_root / name).write_bytes((target / item["path"]).read_bytes())
            receipt["reads"].append({"path": item["path"], "sha256": item["sha256"],
                                     "capture_path": name, "complete": True})
        changed = target / "references/stage1-delivery-entry.md"
        changed.write_text(changed.read_text(encoding="utf-8") + "\n新增适用例外。\n",
                           encoding="utf-8")
        stale = self.check(plan, receipt, capture_root, root=target)
        self.assertEqual(stale["status"], "REPLAN_REQUIRED")
        fresh = self.plan(root=target)
        result = self.check(fresh, receipt, capture_root, root=target)
        self.assertIn("references/stage1-delivery-entry.md", result["needs_full_read"])

    def test_new_context_mode_does_not_make_production_rework_supported(self):
        plan = self.plan("rework", ["continuity"])
        self.assertEqual(plan["production_support"], "UNSUPPORTED")
        self.assertFalse(plan["generation_authorized"])


class MovedIndexTests(unittest.TestCase):
    def fixture(self):
        TEMP.mkdir(exist_ok=True)
        folder = tempfile.TemporaryDirectory(dir=TEMP)
        root = Path(folder.name)
        (root / "references").mkdir()
        (root / "SKILL.md").write_text(
            "# Entry\n<!-- library-index: references/workflow.md -->\n",
            encoding="utf-8")
        return folder, root

    def invoke(self, fn, root):
        with contextlib.redirect_stdout(io.StringIO()):
            return fn(str(root))

    def test_declared_navigation_keeps_leaf_coverage(self):
        folder, root = self.fixture()
        with folder:
            (root / "references/workflow.md").write_text(
                "# Workflow\n" + chr(96) + "references/leaf.md" + chr(96) + "\n",
                encoding="utf-8")
            (root / "references/leaf.md").write_text("# Leaf\n", encoding="utf-8")
            self.assertEqual(self.invoke(audit_prompt.cmd_index, root), 0)
            (root / "references/orphan.md").write_text("# Orphan\n", encoding="utf-8")
            self.assertEqual(self.invoke(audit_prompt.cmd_index, root), 1)

    def test_moved_claims_do_not_escape_numeric_check(self):
        folder, root = self.fixture()
        with folder:
            (root / "references/workflow.md").write_text(
                "**全库 999 条分属三个量级系**\n" + chr(96) +
                "references/pitfalls.md" + chr(96) + "\n", encoding="utf-8")
            (root / "references/pitfalls.md").write_text("### PF1 · x\n", encoding="utf-8")
            self.assertEqual(self.invoke(audit_prompt.cmd_claims, root), 1)

    def test_duplicate_and_nested_index_fail(self):
        folder, root = self.fixture()
        with folder:
            entry = (root / "SKILL.md").read_text(encoding="utf-8")
            (root / "references/workflow.md").write_text("# Workflow\n", encoding="utf-8")
            (root / "SKILL.md").write_text(entry + "<!-- library-index: -->\n", encoding="utf-8")
            self.assertNotEqual(self.invoke(audit_prompt.cmd_index, root), 0)
            (root / "SKILL.md").write_text(entry, encoding="utf-8")
            (root / "references/workflow.md").write_text(
                "<!-- library-index: SKILL.md -->\n", encoding="utf-8")
            self.assertNotEqual(self.invoke(audit_prompt.cmd_index, root), 0)

    def test_missing_or_unsafe_navigation_is_not_success(self):
        folder, root = self.fixture()
        with folder:
            self.assertNotEqual(self.invoke(audit_prompt.cmd_index, root), 0)
            (root / "SKILL.md").write_text(
                "# Entry\n<!-- library-index: ../outside.md -->\n", encoding="utf-8")
            self.assertNotEqual(self.invoke(audit_prompt.cmd_index, root), 0)


if __name__ == "__main__":
    unittest.main()
