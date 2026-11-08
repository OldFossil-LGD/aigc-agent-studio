"""Offline fixtures test dependency/version binding, never media quality."""

import copy
import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from scripts.compile_asset_graph import compile_asset_graph
from scripts.compile_production import compile_production
from scripts.intent_handoff import to_compiler_input
from scripts import compile_shot_graph as graph
from scripts import film_qc_gate as qc


def contract():
    return {
        "aspect_ratio": "16:9",
        "entities": [
            {"id": "coat", "kind": "prop", "description": "red coat", "state": "dry", "version": 1},
            {"id": "cup", "kind": "prop", "description": "white cup", "state": "intact", "version": 1},
        ],
        "shots": [
            {"id": "s1", "version": 1, "duration_sec": 5, "description": "coat shot", "asset_refs": [{"entity_id": "coat", "version": 1}]},
            {"id": "s2", "version": 1, "duration_sec": 5, "description": "cup shot", "asset_refs": [{"entity_id": "cup", "version": 1}]},
        ],
    }


def compile_graph(source):
    return graph.compile_shot_graph(source, compile_asset_graph(source))


class ContinuityTests(unittest.TestCase):
    def test_explicit_shot_references_exclude_unrelated_assets(self):
        plan = compile_graph(contract())
        actual = {(e["source"], e["target"]) for e in plan["edges"] if e["purpose"] == "asset_prop"}
        self.assertEqual(actual, {("coat__asset_anchor", "s1__candidate_image_A"),
                                  ("cup__asset_anchor", "s2__candidate_image_A")})

    def test_empty_explicit_references_mean_no_asset_input(self):
        source = contract()
        source["shots"][0]["asset_refs"] = []
        plan = compile_graph(source)
        self.assertFalse(any(e["target"] == "s1__candidate_image_A" and e["purpose"] == "asset_prop"
                             for e in plan["edges"]))

    def test_unknown_or_unpinned_asset_reference_is_rejected(self):
        for ref in ({"entity_id": "missing", "version": 1}, {"entity_id": "coat"},
                    {"entity_id": "coat", "version": 9}):
            with self.subTest(ref=ref):
                source = contract()
                source["shots"][0]["asset_refs"] = [ref]
                with self.assertRaises(ValueError):
                    compile_graph(source)

    def test_old_calls_keep_legacy_links_but_do_not_claim_explicit_scope(self):
        source = contract()
        del source["shots"][0]["asset_refs"]
        plan = compile_graph(source)
        self.assertEqual(next(s for s in plan["shots"] if s["id"] == "s1").get("asset_reference_scope"),
                         "legacy_all_unconfirmed")
        self.assertTrue(any(e["source"] == "cup__asset_anchor" and e["target"] == "s1__candidate_image_A"
                            for e in plan["edges"]))

    def test_asset_and_shot_revisions_survive_compilation(self):
        source = contract()
        source["entities"][0]["version"] = 3
        source["shots"][0]["version"] = 2
        source["shots"][0]["asset_refs"][0]["version"] = 3
        assets = compile_asset_graph(source)
        self.assertEqual(assets["assets"][0].get("version"), 3)
        plan = graph.compile_shot_graph(source, assets)
        self.assertEqual(next(n for n in plan["nodes"] if n["id"] == "coat__asset_anchor")["version"], 3)
        self.assertEqual(next(n for n in plan["nodes"] if n["id"] == "s1__video_candidate_A")["version"], 2)

    def test_state_change_invalidates_only_dependency_descendants(self):
        before = compile_graph(contract())
        source = contract()
        source["entities"][0].update(state="wet", version=2)
        source["shots"][0]["asset_refs"][0]["version"] = 2
        after = compile_graph(source)
        planner = getattr(graph, "plan_rework", None)
        self.assertTrue(callable(planner), "existing graph module must expose rework traversal")
        result = planner(before, after)
        self.assertEqual(result["status"], "PASS")
        self.assertIn("s1__video_candidate_A", result["affected_record_ids"])
        self.assertIn("global__final_composite", result["affected_record_ids"])
        self.assertFalse(any(n.startswith("s2__") or n.startswith("cup__") for n in result["affected_record_ids"]))
        self.assertFalse(result["generation_authorized"])

    def test_rework_rejects_broken_edges_and_preserves_inputs(self):
        before = compile_graph(contract())
        after = copy.deepcopy(before)
        after["edges"].append({"source": "missing", "target": "s1__video_candidate_A", "purpose": "state"})
        snapshot = copy.deepcopy(after)
        planner = getattr(graph, "plan_rework", None)
        self.assertTrue(callable(planner), "existing graph module must expose rework traversal")
        result = planner(before, after)
        self.assertEqual(result["status"], "FAIL")
        self.assertIn("DANGLING_EDGE", {f["code"] for f in result["failures"]})
        self.assertEqual(after, snapshot)

    def test_layout_change_does_not_invalidate_content(self):
        before = compile_graph(contract())
        after = copy.deepcopy(before)
        after["groups"][0]["name"] = "new label"
        after["nodes"][0].update(x=200, y=300)
        planner = getattr(graph, "plan_rework", None)
        self.assertTrue(callable(planner), "existing graph module must expose rework traversal")
        self.assertEqual(planner(before, after)["affected_record_ids"], [])

    def test_removed_reference_still_invalidates_its_former_consumer(self):
        before = compile_graph(contract())
        after = copy.deepcopy(before)
        after["edges"] = [e for e in after["edges"] if e["source"] != "coat__asset_anchor"]
        result = graph.plan_rework(before, after)
        self.assertIn("s1__video_candidate_A", result["affected_record_ids"])
        self.assertNotIn("s2__video_candidate_A", result["affected_record_ids"])

    def test_rework_cli_emits_only_affected_plan_without_generation(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = contract()
            (root / "before.json").write_text(json.dumps(compile_graph(source)), encoding="utf-8")
            source["entities"][0].update(state="wet", version=2)
            source["shots"][0]["asset_refs"][0]["version"] = 2
            (root / "contract.json").write_text(json.dumps(source), encoding="utf-8")
            (root / "assets.json").write_text(json.dumps(compile_asset_graph(source)), encoding="utf-8")
            proc = subprocess.run([
                sys.executable, str(Path(graph.__file__)), str(root / "contract.json"), str(root / "assets.json"),
                "--previous-graph", str(root / "before.json"), "--out", str(root / "rework.json"),
            ], capture_output=True, text=True, encoding="utf-8")
            self.assertEqual(proc.returncode, 0, proc.stderr)
            result = json.loads((root / "rework.json").read_text(encoding="utf-8"))
            self.assertFalse(result["generation_authorized"])
            self.assertIn("s1__video_candidate_A", result["affected_record_ids"])
            self.assertNotIn("s2__video_candidate_A", result["affected_record_ids"])

    def test_empty_graphs_are_not_a_verified_rework_plan(self):
        result = graph.plan_rework({"nodes": [], "edges": []}, {"nodes": [], "edges": []})
        self.assertEqual(result["status"], "FAIL")
        self.assertIn("EMPTY_GRAPH", {item["code"] for item in result["failures"]})

    def test_reconnecting_one_reference_does_not_invalidate_other_consumers(self):
        before = compile_graph(contract())
        after = copy.deepcopy(before)
        for edge in after["edges"]:
            if edge["source"] == "coat__asset_anchor" and edge["target"] == "s1__candidate_image_A":
                edge["source"] = "cup__asset_anchor"
        result = graph.plan_rework(before, after)
        self.assertIn("s1__video_candidate_A", result["affected_record_ids"])
        self.assertNotIn("s2__video_candidate_A", result["affected_record_ids"])

    def test_intent_to_main_compiler_preserves_pinned_versions_and_consumed_references(self):
        source = contract()
        source["entities"][0]["version"] = 3
        source["shots"][0]["version"] = 2
        source["shots"][0]["asset_refs"][0]["version"] = 3
        values = {"duration_sec": 10, "aspect_ratio": "16:9",
                  "visual_style": {"text": "paper cut", "register": "stylized"}}
        handoff = {
            "intent_format": "intent-handoff/v1", "goal": "offline continuity fixture", "task_type": "full_film",
            "decisions": {key: {"value": value, "source": "user_explicit", "locked": True}
                          for key, value in values.items()},
            "entities": source["entities"], "shots": source["shots"],
        }
        with tempfile.TemporaryDirectory() as tmp:
            result = compile_production(to_compiler_input(handoff), Path(tmp))
            self.assertEqual(result["gate"]["status"], "PASS", result["gate"])
            self.assertEqual(result["contract"]["shots"][0].get("version"), 2)
            self.assertEqual(result["assets"]["assets"][0]["version"], 3)
            shot = next(s for s in result["graph"]["shots"] if s["id"] == "s1")
            self.assertEqual(shot["asset_reference_scope"], "explicit")
            package = next(p for p in result["prompts"] if p["node_id"] == "s1__candidate_image_A")
            self.assertIn("coat__asset_anchor", {r["source"] for r in package["references"]})
            self.assertNotIn("cup__asset_anchor", {r["source"] for r in package["references"]})


class ReviewBindingTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / "bytes.fixture"
        self.path.write_bytes(b"local fixture bytes; not a video")
        self.digest = hashlib.sha256(self.path.read_bytes()).hexdigest()
        self.record = {"record_id": "s1", "version": 1, "state": "generated", "media_sha256": self.digest}
        self.review = {
            "record_id": "s1", "version": 1, "media_sha256": self.digest,
            "layers": {name: {"status": "PASS", "evidence": "fixture observation", "decision": "retain"}
                       for name in ("structure", "instruction", "technical", "creative")},
        }
        self.review["layers"]["creative"]["passes"] = [
            {"pass": number, "status": "PASS", "evidence": "fixture observation", "decision": "retain"}
            for number in range(1, 7)
        ]

    def verify(self, review=None):
        verifier = getattr(qc, "verify_review_binding", None)
        self.assertTrue(callable(verifier), "existing QC module must bind reviews to local bytes")
        return verifier(str(self.path), self.record, review)

    def test_generated_without_review_remains_unreviewed(self):
        result = self.verify()
        self.assertEqual((result["status"], result["state"]), ("NOT_VERIFIED", "generated"))

    def test_consistent_bound_fixture_receipt_is_mechanically_accepted(self):
        result = self.verify(self.review)
        self.assertEqual((result["status"], result["state"]), ("PASS", "generated"))
        self.assertEqual(result.get("review_status"), "NOT_VERIFIED")
        self.assertEqual(result["scope"], "review_binding_only")

    def test_prior_revision_cannot_approve_current_record(self):
        self.record["version"] = 2
        result = self.verify(self.review)
        self.assertEqual(result["status"], "FAIL")
        self.assertIn("REVIEW_VERSION_MISMATCH", {f["code"] for f in result["failures"]})

    def test_replaced_local_bytes_cannot_reuse_receipt(self):
        self.path.write_bytes(b"different local fixture bytes")
        result = self.verify(self.review)
        self.assertEqual(result["status"], "FAIL")
        self.assertIn("MEDIA_HASH_MISMATCH", {f["code"] for f in result["failures"]})

    def test_missing_media_cannot_be_approved(self):
        self.path.unlink()
        result = self.verify(self.review)
        self.assertEqual(result["state"], "generated")
        self.assertNotEqual(result["status"], "PASS")

    def test_top_level_pass_and_technical_qc_do_not_replace_creative_review(self):
        for review in ({"status": "PASS"}, {**self.review, "layers": {"technical": {"status": "PASS"}}}):
            with self.subTest(review=review):
                result = self.verify(review)
                self.assertNotEqual(result["status"], "PASS")
                self.assertEqual(result["state"], "generated")

    def test_forged_pass_without_observations_is_rejected(self):
        self.review["layers"]["creative"]["passes"][0]["evidence"] = ""
        result = self.verify(self.review)
        self.assertEqual(result["status"], "FAIL")

    def test_inconclusive_review_is_not_pass(self):
        self.review["layers"]["creative"]["passes"][2]["status"] = "INCONCLUSIVE"
        result = self.verify(self.review)
        self.assertEqual((result["status"], result["state"]), ("NOT_VERIFIED", "generated"))

    def test_empty_local_file_is_not_reviewed_media(self):
        self.path.write_bytes(b"")
        self.record["media_sha256"] = hashlib.sha256(b"").hexdigest()
        self.review["media_sha256"] = self.record["media_sha256"]
        self.assertNotEqual(self.verify(self.review)["status"], "PASS")

    def test_all_creative_passes_skipped_cannot_approve(self):
        for item in self.review["layers"]["creative"]["passes"]:
            item.update(status="NOT_APPLICABLE", reason="skip")
        self.assertNotEqual(self.verify(self.review)["status"], "PASS")

    def test_negative_summary_cannot_be_overridden_by_green_layers(self):
        self.review["status"] = "FAIL"
        self.assertEqual(self.verify(self.review)["status"], "FAIL")

    def test_binding_cli_rejects_technical_expectations_instead_of_ignoring_them(self):
        root = Path(self.tmp.name)
        (root / "record.json").write_text(json.dumps(self.record), encoding="utf-8")
        (root / "review.json").write_text(json.dumps(self.review), encoding="utf-8")
        proc = subprocess.run([
            sys.executable, str(Path(qc.__file__)), "--video", str(self.path),
            "--review-record", str(root / "record.json"), "--review-receipt", str(root / "review.json"),
            "--expect-duration", "99",
        ], capture_output=True, text=True, encoding="utf-8")
        self.assertEqual(proc.returncode, 2, proc.stdout + proc.stderr)
        self.assertIn("cannot be combined", proc.stderr)


if __name__ == "__main__":
    unittest.main()
