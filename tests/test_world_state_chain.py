"""World-state inheritance must reach real delivery, never certify media."""
import copy
import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from scripts.compile_intent_delivery import compile_intent_delivery
from scripts.compile_production import compile_production
from scripts.compile_graph_plan import convert
from scripts.intent_handoff import to_compiler_input
from scripts import compile_shot_graph as graph


def entry(kind, value, observable=True):
    return dict(kind=kind, value=value, observable=observable)


def intent():
    payload = dict(intent_format="intent-handoff/v1", goal="三镜状态继承，只交提示词",
                   task_type="prompt_only", version=7,
                   decisions={key: dict(value=value, source="user_explicit", locked=True)
                              for key, value in dict(duration_sec=6, aspect_ratio="9:16",
                                  visual_style=dict(text="剪纸", register="stylized")).items()},
                   world_state_initial={"杯": entry("prop", "完整"), "门": entry("world", "关闭")},
                   entities=[], shots=[])
    for number in range(1, 4):
        payload["shots"].append(dict(id="s%d" % number, version=number + 1, duration_sec=2,
            description="剪纸房间中的一镜，无人物", shot_kind="empty", asset_refs=[],
            world_state_refs=["杯", "门"] if number < 3 else ["门"],
            world_state_delta={"杯": entry("prop", "碎裂") if number == 1 else "unchanged",
                               "门": "unchanged"}))
    return payload


def build(payload):
    with tempfile.TemporaryDirectory() as tmp:
        return compile_production(to_compiler_input(payload), Path(tmp))


class WorldStateTests(unittest.TestCase):
    def test_intent_contract_graph_keep_initial_deltas_refs_and_revisions(self):
        raw = intent()
        saved = copy.deepcopy(raw)
        data = to_compiler_input(raw)
        self.assertEqual(data.get("world_state_initial"), raw["world_state_initial"])
        self.assertEqual(data["shots"][0].get("world_state_delta"), raw["shots"][0]["world_state_delta"])
        result = build(raw)
        self.assertEqual(result["contract"].get("world_state_initial"), raw["world_state_initial"])
        shots = result["graph"]["shots"]
        self.assertEqual(shots[0]["world_state_start"]["杯"]["value"], "完整")
        self.assertEqual(shots[0]["world_state_end"]["杯"]["value"], "碎裂")
        self.assertEqual(shots[1]["world_state_start"], shots[0]["world_state_end"])
        self.assertEqual(shots[2]["world_state_start"]["杯"]["value"], "碎裂")
        source = shots[1]["world_state_sources_start"]["杯"]
        self.assertEqual((source["record_id"], source["version"]), ("s1", 2))
        self.assertRegex(source["sha256"], r"^[0-9a-f]{64}$")
        self.assertEqual(shots[2]["world_state_refs"], ["门"])
        self.assertEqual(raw, saved)

    def test_unchanged_must_be_explicit_and_unknown_refs_do_not_silently_expand(self):
        for mutation in ("delta_gap", "missing_refs", "unknown_ref", "duplicate_ref"):
            with self.subTest(mutation=mutation):
                data = intent()
                if mutation == "delta_gap": del data["shots"][1]["world_state_delta"]["杯"]
                if mutation == "missing_refs": data["shots"][1].pop("world_state_refs")
                if mutation == "unknown_ref": data["shots"][1]["world_state_refs"] = ["missing"]
                if mutation == "duplicate_ref": data["shots"][1]["world_state_refs"] = ["门", "门"]
                with self.assertRaises(ValueError): build(data)

    def test_unknown_unobservable_or_nonfinite_state_is_rejected(self):
        for value in (entry("thought", "悲伤"), entry("world", "关闭", False),
                      entry("approval", "已批准", True), entry("prop", None), entry("physical", float("nan"))):
            with self.subTest(value=value):
                data = intent(); data["world_state_initial"]["杯"] = value
                with self.assertRaises(ValueError): build(data)

    def test_real_packages_and_final_text_consume_inherited_state_by_frame_scope(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            compile_intent_delivery(intent(), out)
            self.assertEqual(json.loads((out / "14_delivery_verification.json").read_text(encoding="utf-8"))["status"], "PASS")
            packages = {p["node_id"]: p for p in map(json.loads, (out / "04_prompt_packages.jsonl").read_text(encoding="utf-8").splitlines())}
            body = lambda nid: "\n".join(str(v) for v in packages[nid]["blocks"].values())
            self.assertIn("杯：完整", body("s1__candidate_image_A"))
            self.assertNotIn("杯：碎裂", body("s1__candidate_image_A"))
            self.assertIn("杯：完整", body("s1__video_candidate_A"))
            self.assertIn("杯：碎裂", body("s1__video_candidate_A"))
            self.assertIn("杯：碎裂", body("s2__candidate_image_A"))
            self.assertIn("杯：碎裂", body("s2__video_candidate_A"))
            self.assertNotIn("杯：", body("s3__video_candidate_A"))
            self.assertIn("门：关闭", body("s3__video_candidate_A"))
            final = (out / "13_Draft_Prompt.md").read_text(encoding="utf-8")
            second = final.split("## s2__video_candidate_A", 1)[1].split("\n## ", 1)[0]
            self.assertIn("杯：碎裂", second)
            self.assertFalse((out / "05_platform_execution_plan.json").exists())
            self.assertFalse((out / "08_libtv_command_plan.json").exists())
            self.assertNotIn("source_revision", second)

    def test_state_change_follows_actual_refs_and_static_frames(self):
        before = build(intent())["graph"]
        raw = intent(); raw["shots"][0]["world_state_delta"]["杯"]["value"] = "缺口"
        after = build(raw)["graph"]
        result = graph.plan_rework(before, after)
        self.assertIn("s1__video_candidate_A", result["affected_record_ids"])
        self.assertIn("s2__video_candidate_A", result["affected_record_ids"])
        self.assertNotIn("s1__candidate_image_A", result["affected_record_ids"])
        self.assertNotIn("s3__video_candidate_A", result["affected_record_ids"])
        self.assertFalse(result["generation_authorized"])

    def test_approval_metadata_never_becomes_creative_instruction_or_permission(self):
        raw = intent(); raw["world_state_initial"]["批准"] = entry("approval", "允许付费点火", False)
        for shot in raw["shots"]:
            shot["world_state_delta"]["批准"] = "unchanged"
            shot["world_state_refs"].append("批准")
        result = build(raw)
        self.assertTrue(result["graph"]["shots"][0]["world_state_end"]["批准"])
        for package in result["prompts"]:
            self.assertNotIn("允许付费点火", json.dumps(package["blocks"], ensure_ascii=False))
        self.assertFalse(result["contract"]["delivery"]["ignition_allowed"])

    def test_canonical_graph_preserves_plan_and_node_versions_and_source(self):
        raw = build(intent())["graph"]
        plan = convert(raw, "offline-world-state", "generic")
        self.assertEqual(plan["version"], 7)
        self.assertEqual(plan["source_revision"], raw["source_revision"])
        self.assertEqual(next(n for n in plan["nodes"] if n["node_id"] == "s1__video_candidate_A")["version"], 2)
        self.assertEqual(next(n for n in plan["nodes"] if n["node_id"] == "s2__video_candidate_A")["version"], 3)

    def test_world_state_requirements_reach_the_context_plan(self):
        from scripts.knowledge_routes import plan_context
        raw = intent()
        for shot in raw["shots"]: shot.pop("asset_refs")
        plan = plan_context(Path(__file__).resolve().parents[1], "prompt_only", intent=raw)
        self.assertEqual(plan["status"], "PLAN_ONLY", plan.get("unresolved"))
        rows = {row["requirement_id"] for row in plan["coverage"]}
        self.assertIn("world_state_initial", rows)
        self.assertIn("s1:world_state_delta", rows)
        self.assertIn("s3:world_state_refs", rows)
        self.assertIn("references/offline-continuity-entry.md", {row["path"] for row in plan["files"]})

    def test_dialogue_state_uses_sound_blocks_and_not_static_visual_frames(self):
        raw = intent(); raw["world_state_initial"]["人声"] = entry("dialogue", "无对白")
        for shot in raw["shots"]:
            shot["shot_kind"] = "standard"
            shot["world_state_delta"]["人声"] = "unchanged"
            shot["world_state_refs"].append("人声")
        result = build(raw)
        packages = {p["node_id"]: p for p in result["prompts"]}
        self.assertIn("人声：无对白", packages["s1__video_candidate_A"]["blocks"]["sound"])
        self.assertIn("人声：无对白", packages["s1__audio"]["blocks"]["sound_layers"])
        self.assertNotIn("人声：无对白", json.dumps(packages["s1__candidate_image_A"]["blocks"], ensure_ascii=False))

    def test_empty_shot_cannot_consume_observable_identity_but_keeps_unseen_world(self):
        raw = intent(); raw["world_state_initial"]["人物"] = entry("identity", "红衣女子")
        for shot in raw["shots"]: shot["world_state_delta"]["人物"] = "unchanged"
        build(raw)  # Unreferenced global identity must not appear or be prohibited.
        raw["shots"][0]["world_state_refs"].append("人物")
        with self.assertRaises(ValueError): build(raw)

    def test_prompt_dialogue_state_is_in_sound_and_not_compiled_visual_constraints(self):
        raw = intent(); raw["world_state_initial"]["人声"] = entry("dialogue", "无对白")
        for shot in raw["shots"]:
            shot["world_state_delta"]["人声"] = "unchanged"
            shot["world_state_refs"].append("人声")
        packages = {p["node_id"]: p for p in build(raw)["prompts"]}
        blocks = packages["s1__prompt"]["blocks"]
        self.assertIn("人声：无对白", blocks.get("sound", ""))
        self.assertNotIn("人声：无对白", blocks["compiled_constraints"])

    def test_deleting_or_moving_state_cannot_be_hidden_by_metadata_other_blocks_or_nodes(self):
        from scripts.verify_delivery_semantics import verify_delivery
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp); raw = intent(); compile_intent_delivery(raw, out)
            source_packages = list(map(json.loads, (out / "04_prompt_packages.jsonl").read_text(encoding="utf-8").splitlines()))
            source_graph = json.loads((out / "03_shot_graph_plan.json").read_text(encoding="utf-8"))
            source_markdown = (out / "13_Draft_Prompt.md").read_text(encoding="utf-8")
            self.assertEqual(verify_delivery(raw, source_packages, source_graph, source_markdown)["status"], "PASS")
            for mutation in ("canonical_delete", "final_delete", "wrong_block", "negated", "duplicate_heading"):
                with self.subTest(mutation=mutation):
                    packages = copy.deepcopy(source_packages); markdown = source_markdown
                    target = next(p for p in packages if p["node_id"] == "s2__video_candidate_A")
                    target["consumed"] = target["verified"] = True
                    if mutation in ("canonical_delete", "wrong_block", "negated"):
                        original = target["blocks"]["continuity"]
                        if mutation == "negated":
                            target["blocks"]["continuity"] = original.replace("开场可观察状态", "禁止开场可观察状态").replace("结束可观察状态", "禁止结束可观察状态")
                        else:
                            target["blocks"]["continuity"] = original.replace("杯：碎裂", "")
                        if mutation == "wrong_block": target["blocks"]["negative"] += "\n" + original
                    if mutation in ("final_delete", "duplicate_heading"):
                        start = markdown.index("## s2__video_candidate_A")
                        end = markdown.find("\n## ", start + 1)
                        if end < 0: end = len(markdown)
                        segment = markdown[start:end]
                        if mutation == "final_delete": markdown = markdown[:start] + segment.replace("杯：碎裂", "") + markdown[end:]
                        else: markdown += "\n" + segment
                    result = verify_delivery(raw, packages, source_graph, markdown)
                    self.assertEqual(result["status"], "FAIL", result)
                    self.assertTrue(any(f["code"].startswith("WORLD_STATE_") for f in result["failures"]))

    def test_world_state_cannot_be_skipped_by_removing_all_candidate_declarations(self):
        from scripts.verify_delivery_semantics import verify_delivery
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp); raw = intent(); compile_intent_delivery(raw, out)
            packages = list(map(json.loads, (out / "04_prompt_packages.jsonl").read_text(encoding="utf-8").splitlines()))
            g = json.loads((out / "03_shot_graph_plan.json").read_text(encoding="utf-8"))
            markdown = (out / "13_Draft_Prompt.md").read_text(encoding="utf-8")
            self.assertEqual(verify_delivery(raw, packages, g, markdown)["status"], "PASS")
            roles = {"candidate_image", "video_candidate"}
            packages = [p for p in packages if p["role"] not in roles]
            g["nodes"] = [n for n in g["nodes"] if n["role"] not in roles]
            result = verify_delivery(raw, packages, g, markdown)
            self.assertEqual(result["status"], "FAIL", result)
            self.assertTrue(any(f["code"].startswith("WORLD_STATE_") for f in result["failures"]))

    def test_multiline_state_value_cannot_lose_its_second_line(self):
        from scripts.verify_delivery_semantics import verify_delivery
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp); raw = intent(); raw["world_state_initial"]["杯"]["value"] = "完整\n白釉"
            compile_intent_delivery(raw, out)
            packages = list(map(json.loads, (out / "04_prompt_packages.jsonl").read_text(encoding="utf-8").splitlines()))
            g = json.loads((out / "03_shot_graph_plan.json").read_text(encoding="utf-8"))
            markdown = (out / "13_Draft_Prompt.md").read_text(encoding="utf-8")
            self.assertEqual(verify_delivery(raw, packages, g, markdown)["status"], "PASS")
            target = next(p for p in packages if p["node_id"] == "s1__candidate_image_A")
            target["blocks"]["composition"] = target["blocks"]["composition"].replace("白釉", "")
            result = verify_delivery(raw, packages, g, markdown)
            self.assertEqual(result["status"], "FAIL", result)
            self.assertTrue(any(f["code"].startswith("WORLD_STATE_") for f in result["failures"]))

    def test_stateful_delivery_without_final_text_is_not_verified(self):
        from scripts.verify_delivery_semantics import verify_delivery
        result = build(intent())
        check = verify_delivery(intent(), result["prompts"], result["graph"], None)
        self.assertEqual(check["status"], "FAIL", check)
        self.assertIn("WORLD_STATE_FINAL_MISSING", {f["code"] for f in check["failures"]})

    def test_invalid_graph_version_is_rejected_instead_of_reset_to_one(self):
        for bad in (True, 0, -1, "2"):
            with self.subTest(bad=bad):
                with self.assertRaises(ValueError): convert({"nodes": [], "version": bad}, "fixture", "generic")


if __name__ == "__main__": unittest.main()
