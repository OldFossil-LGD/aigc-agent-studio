#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""End-to-end acceptance tests for the stage-1 intent → prompt delivery chain.

These tests exercise the *real* entry point on the *real* artefacts. They
never trust the compiler's self-reported status: every acceptance decision is
re-derived from the files that were actually written.

The tests are additive. No existing test is modified and no existing gate is
relaxed.

Run with the candidate root on sys.path:

    python -m unittest tests.test_intent_delivery -v
"""

import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SKILL_ROOT = Path(__file__).resolve().parent.parent
if str(SKILL_ROOT) not in sys.path:
    sys.path.insert(0, str(SKILL_ROOT))

from scripts.compile_intent_delivery import (  # noqa: E402
    DRAFT_MARKDOWN as COPYABLE_MARKDOWN,  # rendering/constraint tests use explicit non-final artifacts
    DELIVERY_PACKAGE,
    VERIFICATION_REPORT,
    compile_intent_delivery,
)
from scripts.intent_handoff import IntentHandoffError  # noqa: E402
from scripts.constraint_semantics import evaluate_constraint  # noqa: E402
from scripts.verify_delivery_semantics import verify_delivery  # noqa: E402

SAMPLE = SKILL_ROOT / "samples" / "papercut_empty_shot_intent.json"


def load_sample() -> dict:
    return json.loads(SAMPLE.read_text(encoding="utf-8"))


class PublicSampleDeliveryTests(unittest.TestCase):
    """The public user input must produce a complete, copyable delivery."""

    @classmethod
    def setUpClass(cls):
        cls._tmp = tempfile.mkdtemp(prefix="intent_delivery_")
        cls.out = Path(cls._tmp) / "out"
        cls.result = compile_intent_delivery(load_sample(), cls.out)
        cls.markdown = (cls.out / COPYABLE_MARKDOWN).read_text(encoding="utf-8")
        cls.report = json.loads((cls.out / VERIFICATION_REPORT).read_text(encoding="utf-8"))
        cls.delivery = json.loads((cls.out / DELIVERY_PACKAGE).read_text(encoding="utf-8"))

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls._tmp, ignore_errors=True)

    # --- A: the explicit user values survive ------------------------------
    def test_explicit_values_are_preserved_verbatim(self):
        contract = self.result["contract"]
        self.assertEqual(contract["duration_sec"], 5)
        self.assertEqual(contract["aspect_ratio"], "9:16")
        self.assertEqual(contract["task_type"], "prompt_only")
        self.assertIn("剪纸", contract["visual_style"])
        self.assertNotEqual(contract["duration_sec"], 120)
        self.assertNotEqual(contract["aspect_ratio"], "16:9")

    def test_every_user_value_keeps_its_source_and_lock(self):
        log = {item["field"]: item for item in self.result["contract"]["decision_log"]}
        for field in ("duration_sec", "aspect_ratio", "visual_style"):
            self.assertEqual(log[field]["source"], "user_explicit")
            self.assertTrue(log[field]["locked"])
            self.assertEqual(log[field]["status"], "locked")

    def test_unknown_values_are_not_claimed_as_locked(self):
        # An agent-supplied constraint must stay unlocked and must not be
        # smuggled into the locked decision set.
        proposed = [
            item
            for item in self.result["contract"].get("decision_log", [])
            if item["source"] != "user_explicit"
        ]
        for item in proposed:
            self.assertFalse(item["locked"])
        self.assertEqual(self.result["contract"].get("proposed_decisions", []), [])

    # --- B: the canonical package is the single source --------------------
    def test_prompt_packages_carry_the_canonical_format_version(self):
        packages = self.result["prompts"]
        self.assertTrue(packages)
        for package in packages:
            self.assertEqual(package["prompt_format"], "prompt-package/v1")

    def test_legacy_renderer_is_fed_from_the_canonical_packages(self):
        rendered = (self.out / "rendered" / "03_Prompt_Packages.jsonl").read_text(
            encoding="utf-8"
        )
        canonical = (self.out / "04_prompt_packages.jsonl").read_text(encoding="utf-8")
        self.assertEqual(rendered, canonical)
        manifest = json.loads(
            (self.out / "rendered" / "prompt_render_manifest.json").read_text(encoding="utf-8")
        )
        self.assertEqual(manifest["canonical_format"], "prompt-package/v1")

    def test_empty_input_is_not_a_success(self):
        # 8 packages and 0 documents must never read as a delivery.
        empty = verify_delivery(load_sample(), [], None, None)
        self.assertEqual(empty["status"], "FAIL")
        self.assertFalse(empty["checks"]["packages_present"])

    # --- C: the constraints actually land in the delivered text ------------
    def test_constraints_are_consumed_by_the_prompt_packages(self):
        self.assertEqual(self.result["gate"]["status"], "PASS")
        self.assertEqual(self.report["status"], "PASS")
        self.assertEqual(self.report["failures"], [])

    def test_real_judgements_happened(self):
        # 0 judgements is not a pass. There must be actual per-role verdicts.
        self.assertGreater(self.report["checks"]["judgements_performed"], 0)
        self.assertEqual(self.report["checks"]["judgements_performed"], len(self.report["semantic_results"]))
        self.assertGreater(self.report["checks"]["delivery_text_judgements"], 0)
        for record in self.report["semantic_results"]:
            self.assertTrue(record["ok"])

    def test_every_judged_constraint_reached_a_consuming_role(self):
        judged = {item["constraint_id"] for item in self.report["semantic_results"]}
        self.assertEqual(
            judged,
            {"c_camera", "c_composition", "c_sound", "c_subject", "c_empty"},
        )

    def test_delivered_text_carries_the_real_constraints(self):
        self.assertIn("俯拍", self.markdown)
        self.assertIn("右上角留白", self.markdown)
        self.assertIn("雨声", self.markdown)
        self.assertIn("剪纸", self.markdown)

    def test_delivered_text_names_no_unlanded_reference_image(self):
        # No reference image was produced in this stage; the copyable text must
        # not promise one.
        self.assertNotIn("{{Node", self.markdown)
        self.assertNotIn("引用：", self.markdown)

    def test_empty_shot_carries_no_identity_wardrobe_or_voice(self):
        for marker in ("人物", "面孔"):
            # The negative block may legitimately *forbid* people; what must
            # not appear is a person being introduced.
            self.assertNotIn("角色描述", self.markdown)
            self.assertNotIn("服装：", self.markdown)
        self.assertNotIn("旁白朗读", self.markdown)

    def test_no_silent_downgrade_to_text_to_video(self):
        self.assertNotIn("文生视频", self.markdown)

    # --- D: prompt_only stops at the right place --------------------------
    def test_prompt_only_produces_no_execution_plan(self):
        self.assertFalse((self.out / "05_platform_execution_plan.json").exists())
        self.assertFalse((self.out / "08_libtv_command_plan.json").exists())

    def test_prompt_only_creates_no_canvas_and_no_media(self):
        self.assertTrue(self.delivery["no_media_generated"])
        self.assertTrue(self.delivery["no_platform_write"])
        self.assertTrue(self.delivery["no_ignition"])
        self.assertFalse(self.delivery["claims"]["media_quality_verified"])

    def test_required_artefacts_are_on_disk(self):
        for name in (
            "01_production_contract.json",
            "03_shot_graph_plan.json",
            "04_prompt_packages.jsonl",
            DELIVERY_PACKAGE,
            COPYABLE_MARKDOWN,
            VERIFICATION_REPORT,
        ):
            self.assertTrue((self.out / name).exists(), name)

    def test_copyable_markdown_is_non_empty_and_clean(self):
        self.assertTrue(self.markdown.strip())
        self.assertNotIn("TODO", self.markdown)
        self.assertNotIn("待补充", self.markdown)
        self.assertIn("未生成任何参考图或素材", self.markdown)

    # --- E: the acceptance is independent of the generator's self-report --
    def test_tampered_camera_angle_fails(self):
        tampered = self._tampered({"俯拍": "平视"})
        report = verify_delivery(load_sample(), tampered, self.result["graph"], None)
        self.assertEqual(report["status"], "FAIL")
        codes = {item["code"] for item in report["failures"]}
        self.assertIn("CONSTRAINT_SEMANTICS_VIOLATED", codes)

    def test_removed_negative_space_fails(self):
        tampered = self._tampered({"右上角留白": ""})
        report = verify_delivery(load_sample(), tampered, self.result["graph"], None)
        self.assertEqual(report["status"], "FAIL")

    def test_narration_instead_of_ambience_fails(self):
        tampered = self._tampered({"雨声": "旁白朗读解说"})
        report = verify_delivery(load_sample(), tampered, self.result["graph"], None)
        self.assertEqual(report["status"], "FAIL")

    def test_tampered_structure_fails(self):
        tampered = self._tampered({})
        for package in tampered:
            package["role"] = "assembly"
        report = verify_delivery(load_sample(), tampered, self.result["graph"], None)
        self.assertEqual(report["status"], "FAIL")
        codes = {item["code"] for item in report["failures"]}
        self.assertIn("PROMPT_PACKAGE_ROLE_MISMATCH", codes)

    def test_tampered_provenance_fails(self):
        tampered = self._tampered({})
        for package in tampered:
            for evidence in package.get("constraint_evidence") or []:
                evidence["locked"] = not evidence.get("locked")
        report = verify_delivery(load_sample(), tampered, self.result["graph"], None)
        self.assertEqual(report["status"], "FAIL")
        codes = {item["code"] for item in report["failures"]}
        self.assertIn("CONSTRAINT_PROVENANCE_TAMPERED", codes)

    def test_legal_synonym_is_accepted(self):
        tampered = self._tampered({"相机固定俯拍": "正上方俯视，固定机位。"})
        report = verify_delivery(load_sample(), tampered, self.result["graph"], None)
        self.assertEqual(report["status"], "PASS", report["failures"])

    def test_final_document_contradicting_a_constraint_fails(self):
        report = verify_delivery(
            load_sample(), self.result["prompts"], self.result["graph"], "## shot_01\n相机平视。"
        )
        self.assertEqual(report["status"], "FAIL")
        codes = {item["code"] for item in report["failures"]}
        self.assertIn("DELIVERY_TEXT_CONSTRAINT_VIOLATED", codes)

    def _tampered(self, replacements: dict) -> list:
        """Copy the real packages and corrupt the delivered text."""
        packages = json.loads(json.dumps(self.result["prompts"]))
        for package in packages:
            blocks = package.get("blocks") or {}
            for key, value in list(blocks.items()):
                if not isinstance(value, str):
                    continue
                new = value
                for old, replacement in replacements.items():
                    new = new.replace(old, replacement)
                if new != value:
                    blocks[key] = new
        return packages


class RoutingTableTests(unittest.TestCase):
    """The verifier must never judge nothing and call it a pass."""

    def test_routing_table_is_loaded(self):
        import scripts.verify_delivery_semantics as module

        self.assertTrue(module.CONSTRAINT_DELIVERY_BY_KIND)
        for kind in ("camera", "composition", "sound", "visual", "negative"):
            self.assertIn(kind, module.CONSTRAINT_DELIVERY_BY_KIND)

    def test_zero_judgements_is_a_failure(self):
        intent = load_sample()
        report = verify_delivery(intent, [], None, None)
        codes = {item["code"] for item in report["failures"]}
        self.assertIn("NO_PROMPT_PACKAGES", codes)


class CliBehaviourTests(unittest.TestCase):
    """The real command line must succeed on the real sample."""

    def test_explicit_draft_cli_exit_code_is_zero_on_the_public_sample(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "out"
            proc = subprocess.run(
                [
                    sys.executable,
                    str(SKILL_ROOT / "scripts" / "compile_intent_delivery.py"),
                    str(SAMPLE),
                    "--draft",
                    "--out",
                    str(out),
                ],
                cwd=str(SKILL_ROOT),
                capture_output=True,
                text=True,
                encoding="utf-8",
            )
            self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
            payload = json.loads(proc.stdout)
            self.assertEqual(payload["gate_status"], "PASS")
            self.assertEqual(payload["verification_status"], "PASS")

    def test_cli_rejects_an_invalid_handoff(self):
        with tempfile.TemporaryDirectory() as tmp:
            bad = Path(tmp) / "bad.json"
            payload = load_sample()
            payload["intent_format"] = "intent-handoff/v99"
            bad.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
            proc = subprocess.run(
                [
                    sys.executable,
                    str(SKILL_ROOT / "scripts" / "compile_intent_delivery.py"),
                    str(bad),
                    "--out",
                    str(Path(tmp) / "out"),
                ],
                cwd=str(SKILL_ROOT),
                capture_output=True,
                text=True,
                encoding="utf-8",
            )
            self.assertNotEqual(proc.returncode, 0)
            self.assertIn("intent handoff invalid", proc.stderr)

    def test_cli_refuses_to_lock_an_agents_own_proposal(self):
        with tempfile.TemporaryDirectory() as tmp:
            bad = Path(tmp) / "bad.json"
            payload = load_sample()
            payload["decisions"]["duration_sec"] = {
                "value": 5,
                "source": "agent_proposed",
                "locked": True,
            }
            bad.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
            proc = subprocess.run(
                [
                    sys.executable,
                    str(SKILL_ROOT / "scripts" / "compile_intent_delivery.py"),
                    str(bad),
                    "--out",
                    str(Path(tmp) / "out"),
                ],
                cwd=str(SKILL_ROOT),
                capture_output=True,
                text=True,
                encoding="utf-8",
            )
            self.assertNotEqual(proc.returncode, 0)
            self.assertIn("locked", proc.stderr)


class IntentHandoffValidationTests(unittest.TestCase):
    """The handoff refuses to lie about the user's intent."""

    def _expect_error(self, mutate):
        payload = load_sample()
        mutate(payload)
        with self.assertRaises(IntentHandoffError):
            from scripts.intent_handoff import validate_intent_handoff

            validate_intent_handoff(payload)

    def test_unknown_format_is_rejected(self):
        self._expect_error(lambda p: p.update({"intent_format": "nope"}))

    def test_missing_lock_on_user_explicit_is_rejected(self):
        def mutate(payload):
            payload["decisions"]["duration_sec"]["locked"] = False

        self._expect_error(mutate)

    def test_locked_agent_proposal_is_rejected(self):
        def mutate(payload):
            payload["decisions"]["aspect_ratio"] = {
                "value": "9:16",
                "source": "agent_proposed",
                "locked": True,
            }

        self._expect_error(mutate)

    def test_prompt_constraint_without_semantics_is_rejected(self):
        def mutate(payload):
            payload["constraints"][0].pop("semantics")

        self._expect_error(mutate)

    def test_zero_duration_is_rejected(self):
        def mutate(payload):
            payload["decisions"]["duration_sec"]["value"] = 0

        self._expect_error(mutate)


# ---------------------------------------------------------------------------
# Added in call5 (INTENT-DELIVERY-01 续收口). The tests above are untouched.
# They close the audit's P1–P5:
#   P1 a negated positive requirement must not read as delivered
#   P2 a prohibition must not mask a real narration in the same clause
#   P3 candidate coverage is checked per authoritative graph node
#   P4 the aspect ratio / duration decisions must reach the delivered text
#   P5 the recovery index must ship inside the package and be checkable
# ---------------------------------------------------------------------------


class NegationScopeTests(unittest.TestCase):
    """A negated requirement is not a delivered requirement."""

    CAMERA = {"required_any": ["俯拍", "正上方", "自上而下"], "forbidden": ["平视"]}
    SOUND = {"required_any": ["雨声"], "forbidden": ["旁白", "解说", "人声台词"]}

    def test_negated_required_camera_is_not_delivered(self):
        report = evaluate_constraint("相机禁止俯拍，机位不移动。", self.CAMERA)
        self.assertFalse(report["ok"])
        self.assertFalse(report["required_satisfied"])
        self.assertTrue(report["required"]["missing"])

    def test_negated_requirement_fails_the_whole_delivery(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "out"
            result = compile_intent_delivery(load_sample(), out)
            markdown = (out / COPYABLE_MARKDOWN).read_text(encoding="utf-8")
            # Every affirmative mention of the requirement is negated — the
            # camera block *and* the shot description in the action block.
            markdown = markdown.replace("相机固定俯拍", "相机禁止俯拍")
            markdown = markdown.replace("固定俯拍", "禁止俯拍")
            report = verify_delivery(load_sample(), result["prompts"], result["graph"], markdown)
            self.assertEqual(report["status"], "FAIL")
            codes = {item["code"] for item in report["failures"]}
            self.assertIn("DELIVERY_TEXT_CONSTRAINT_VIOLATED", codes)

    def test_legal_synonym_is_still_delivered(self):
        report = evaluate_constraint("正上方俯视，固定机位。", self.CAMERA)
        self.assertTrue(report["ok"])

    def test_prohibition_does_not_mask_a_later_real_narration(self):
        report = evaluate_constraint(
            "只保留雨声；禁止音乐，旁白清晰朗读解说。", self.SOUND
        )
        self.assertFalse(report["ok"])
        self.assertTrue(report["forbidden"]["violations"])

    def test_prohibition_must_not_be_misread_as_a_violation(self):
        report = evaluate_constraint(
            "只保留 雨声；禁止人声、对白、旁白、口型说话与歌词。", self.SOUND
        )
        self.assertTrue(report["ok"], report)
        self.assertEqual(report["forbidden"]["violations"], [])

    def test_unrelated_prohibition_in_the_body_still_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "out"
            result = compile_intent_delivery(load_sample(), out)
            markdown = (out / COPYABLE_MARKDOWN).read_text(encoding="utf-8")
            markdown = markdown.replace(
                "只保留雨声；无人声、无对白、无旁白、无音乐。",
                "只保留雨声；禁止音乐，旁白清晰朗读解说。",
            )
            report = verify_delivery(load_sample(), result["prompts"], result["graph"], markdown)
            self.assertEqual(report["status"], "FAIL")
            codes = {item["code"] for item in report["failures"]}
            self.assertIn("DELIVERY_TEXT_CONSTRAINT_VIOLATED", codes)

    def test_required_form_containing_a_negation_marker_is_satisfied(self):
        # "不出现人物" is the required phrase itself — the marker is part of
        # the requirement, not a negation of it.
        report = evaluate_constraint(
            "画面内不出现人物、面孔、人体。", {"required_any": ["不出现人物", "禁止人物"]}
        )
        self.assertTrue(report["ok"], report)


class CandidateNodeCoverageTests(unittest.TestCase):
    """Coverage is checked per authoritative graph node, not per role."""

    @classmethod
    def setUpClass(cls):
        cls._tmp = tempfile.mkdtemp(prefix="intent_candidates_")
        cls.out = Path(cls._tmp) / "out"
        cls.result = compile_intent_delivery(load_sample(), cls.out)
        cls.packages = cls.result["prompts"]
        cls.graph = cls.result["graph"]

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls._tmp, ignore_errors=True)

    def _second_candidate_graph(self):
        graph = json.loads(json.dumps(self.graph))
        template = next(
            node for node in graph["nodes"] if node.get("role") == "video_candidate"
        )
        extra = json.loads(json.dumps(template))
        extra["id"] = extra["id"].replace("_A", "_B")
        graph["nodes"].append(extra)
        return graph, extra["id"]

    def test_missing_second_candidate_is_a_failure(self):
        graph, extra_id = self._second_candidate_graph()
        report = verify_delivery(load_sample(), self.packages, graph, None)
        self.assertEqual(report["status"], "FAIL")
        codes = {item["code"] for item in report["failures"]}
        self.assertIn("CANDIDATE_NODE_PACKAGE_MISSING", codes)
        self.assertIn(extra_id, {item.get("node_id") for item in report["failures"]})

    def test_duplicated_candidate_package_is_a_failure(self):
        packages = json.loads(json.dumps(self.packages))
        packages.append(
            json.loads(json.dumps(next(p for p in packages if p.get("role") == "video_candidate")))
        )
        report = verify_delivery(load_sample(), packages, self.graph, None)
        self.assertEqual(report["status"], "FAIL")
        codes = {item["code"] for item in report["failures"]}
        self.assertIn("CANDIDATE_NODE_PACKAGE_DUPLICATED", codes)

    def test_mismatched_candidate_role_is_a_failure(self):
        packages = json.loads(json.dumps(self.packages))
        for package in packages:
            if package.get("role") == "video_candidate":
                package["role"] = "candidate_image"
                break
        report = verify_delivery(load_sample(), packages, self.graph, None)
        self.assertEqual(report["status"], "FAIL")
        codes = {item["code"] for item in report["failures"]}
        self.assertTrue(
            codes & {"CANDIDATE_NODE_ROLE_MISMATCH", "PROMPT_PACKAGE_ROLE_MISMATCH"},
            codes,
        )

    def test_every_graph_candidate_node_is_delivered(self):
        report = verify_delivery(load_sample(), self.packages, self.graph, None)
        self.assertTrue(report["checks"]["candidate_coverage"], report["failures"])


class DecisionDeliveryTests(unittest.TestCase):
    """A decision that only lives in the contract is not a delivered decision."""

    @classmethod
    def setUpClass(cls):
        cls._tmp = tempfile.mkdtemp(prefix="intent_decisions_")
        cls.out = Path(cls._tmp) / "out"
        cls.result = compile_intent_delivery(load_sample(), cls.out)
        cls.markdown = (cls.out / COPYABLE_MARKDOWN).read_text(encoding="utf-8")

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls._tmp, ignore_errors=True)

    def test_aspect_ratio_reaches_the_copyable_body(self):
        self.assertIn("9:16", self.markdown)
        self.assertIn("【可复制设置】", self.markdown)

    def test_duration_reaches_the_copyable_body(self):
        self.assertIn("5 秒", self.markdown)

    def test_internal_control_fields_are_not_in_the_body(self):
        for marker in ("source_duration_sec=", "final_used_duration_sec=", "cut_start_sec="):
            self.assertNotIn(marker, self.markdown, marker)

    def test_contradicting_aspect_ratio_fails(self):
        report = verify_delivery(
            load_sample(),
            self.result["prompts"],
            self.result["graph"],
            self.markdown + "\n画幅16:9横屏。\n",
        )
        self.assertEqual(report["status"], "FAIL")
        codes = {item["code"] for item in report["failures"]}
        self.assertIn("DECISION_ASPECT_RATIO_CONTRADICTED", codes)

    def test_contradicting_duration_fails(self):
        report = verify_delivery(
            load_sample(),
            self.result["prompts"],
            self.result["graph"],
            self.markdown.replace("成片时长 5 秒", "时长120秒"),
        )
        self.assertEqual(report["status"], "FAIL")
        codes = {item["code"] for item in report["failures"]}
        self.assertIn("DECISION_DURATION_CONTRADICTED", codes)

    def test_decision_is_cross_checked_against_the_authoritative_input(self):
        report = verify_delivery(
            load_sample(), self.result["prompts"], self.result["graph"], self.markdown
        )
        self.assertTrue(report["checks"]["decision_delivery"], report["failures"])
        decisions = {
            item["decision"]: item for item in report["checks"]["decision_results"]
        }
        self.assertEqual(decisions["aspect_ratio"]["value"], "9:16")
        self.assertEqual(decisions["duration_sec"]["value"], 5)
        for record in decisions.values():
            self.assertTrue(record["delivered_in"], record)
            self.assertEqual(record["contradicting"], [], record)


class RecoveryIndexTests(unittest.TestCase):
    """The recovery index must ship inside the package and be checkable."""

    def test_index_is_inside_the_package(self):
        index = SKILL_ROOT / "references" / "stage1-recovery-index.json"
        self.assertTrue(index.is_file(), str(index))

    def test_index_does_not_point_into_a_task_directory(self):
        index = json.loads(
            (SKILL_ROOT / "references" / "stage1-recovery-index.json").read_text(
                encoding="utf-8"
            )
        )
        for book in index.get("books") or []:
            path = (book.get("external") or {}).get("path")
            if not path:
                continue
            self.assertNotIn(
                "intent_delivery_stage1_20261022",
                path,
                "恢复指针不得只指向本次任务目录：%s" % path,
            )

    def test_every_indexed_book_is_either_reachable_or_declared_unrecoverable(self):
        index = json.loads(
            (SKILL_ROOT / "references" / "stage1-recovery-index.json").read_text(
                encoding="utf-8"
            )
        )
        for book in index.get("books") or []:
            external = book.get("external") or {}
            if external.get("path"):
                self.assertTrue(Path(external["path"]).is_file(), external["path"])
            else:
                self.assertFalse(book.get("recoverable"), book.get("book"))

    def test_verifier_script_runs_and_passes(self):
        proc = subprocess.run(
            [sys.executable, str(SKILL_ROOT / "scripts" / "verify_recovery_index.py")],
            cwd=str(SKILL_ROOT),
            capture_output=True,
            text=True,
            encoding="utf-8",
        )
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        payload = json.loads(proc.stdout)
        self.assertEqual(payload["status"], "PASS")
        self.assertTrue(payload["index_in_package"])


if __name__ == "__main__":
    unittest.main()
