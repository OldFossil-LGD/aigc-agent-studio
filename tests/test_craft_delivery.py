import copy
import json
import re
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.verify_delivery_semantics import verify_delivery


class CraftDeliveryTests(unittest.TestCase):
    def test_metadata_keys_not_in_creative_craft_set(self):
        from scripts.intent_handoff import CREATIVE_CRAFT_KEYS
        for bad in ("craft_applied", "craft_ids", "source", "locked", "semantics"):
            self.assertNotIn(bad, CREATIVE_CRAFT_KEYS)

    def test_craft_consumption_missing_fails(self):
        intent = {
            "intent_format": "intent-handoff/v1",
            "goal": "t",
            "task_type": "prompt_only",
            "decisions": {
                "duration_sec": {"value": 5, "source": "user_explicit", "locked": True},
                "aspect_ratio": {"value": "16:9", "source": "user_explicit", "locked": True},
                "visual_style": {"value": {"text": "写实", "register": "photoreal"}, "source": "user_explicit", "locked": True},
            },
            "shots": [{"id": "shot_01", "duration_sec": 5, "description": "x", "action_feedback": "反馈文本XYZ"}],
            "constraints": [],
        }
        pkg = {
            "prompt_format": "prompt-package/v1",
            "node_id": "shot_01__video_candidate_A",
            "role": "video_candidate",
            "shot_id": "shot_01",
            "blocks": {"action": "完成镜头 shot_01 的变化；", "visual": "写实", "sound": "环境声", "negative": "禁止", "duration": "5秒", "material_roles": "m", "continuity": "c"},
            "missing_blocks": [],
            "constraint_evidence": [],
        }
        res = verify_delivery(intent, [pkg], None, "## shot_01\n无工艺。")
        self.assertEqual(res["status"], "FAIL")
        self.assertTrue(any(f["code"] == "CRAFT_CONSUMPTION_MISSING" for f in res["failures"]))

    def test_craft_consumption_present_passes(self):
        intent = {
            "intent_format": "intent-handoff/v1",
            "goal": "t",
            "task_type": "prompt_only",
            "decisions": {
                "duration_sec": {"value": 5, "source": "user_explicit", "locked": True},
                "aspect_ratio": {"value": "16:9", "source": "user_explicit", "locked": True},
                "visual_style": {"value": {"text": "写实", "register": "photoreal"}, "source": "user_explicit", "locked": True},
            },
            "shots": [{"id": "shot_01", "duration_sec": 5, "description": "x", "action_feedback": "反馈文本XYZ"}],
            "constraints": [],
        }
        pkg = {
            "prompt_format": "prompt-package/v1",
            "node_id": "shot_01__video_candidate_A",
            "role": "video_candidate",
            "shot_id": "shot_01",
            "blocks": {"action": "完成镜头 shot_01 的变化；反馈文本XYZ", "visual": "写实", "sound": "环境声", "negative": "禁止", "duration": "5秒", "material_roles": "m", "continuity": "c"},
            "missing_blocks": [],
            "constraint_evidence": [],
        }
        res = verify_delivery(intent, [pkg], None, "## shot_01\n画幅 16:9；时长 5 秒。\n反馈文本XYZ")
        self.assertNotEqual(res["status"], "FAIL")


    def test_duration_scope_cross_shot_fails(self):
        intent = {
            "intent_format": "intent-handoff/v1",
            "goal": "scope test",
            "task_type": "prompt_only",
            "decisions": {
                "duration_sec": {"value": 12, "source": "user_explicit", "locked": True},
                "aspect_ratio": {"value": "9:16", "source": "user_explicit", "locked": True},
                "visual_style": {"value": {"text": "写实", "register": "photoreal"}, "source": "user_explicit", "locked": True},
            },
            "shots": [
                {"id": "shot_02", "duration_sec": 6, "description": "y", "sound_craft": "切到第二镜后滴答余响延续2秒，再只留窗外雨声。"},
            ],
            "constraints": [],
        }
        pkg1 = {
            "prompt_format": "prompt-package/v1",
            "node_id": "shot_01__video_candidate_A",
            "role": "video_candidate",
            "shot_id": "shot_01",
            "blocks": {"visual": "固定", "sound": "滴答声", "duration": "成片时长 6 秒。", "delivery_settings": "画幅 9:16；时长 6 秒。全片时长 12 秒。 当前镜头时长2秒。"},
            "missing_blocks": [],
            "constraint_evidence": [],
        }
        pkg2 = {
            "prompt_format": "prompt-package/v1",
            "node_id": "shot_02__video_candidate_A",
            "role": "video_candidate",
            "shot_id": "shot_02",
            "blocks": {"visual": "固定", "sound": "切到第二镜后滴答余响延续2秒，再只留窗外雨声。", "duration": "成片时长 6 秒。", "delivery_settings": "画幅 9:16；时长 6 秒。全片时长 12 秒。"},
            "missing_blocks": [],
            "constraint_evidence": [],
        }
        md = "## shot_01__video_candidate_A\n时长 6 秒。 当前镜头时长2秒。\n## shot_02__video_candidate_A\n时长 6 秒。全片时长 12 秒。 切到第二镜后滴答余响延续2秒，再只留窗外雨声。"
        res = verify_delivery(intent, [pkg1, pkg2], None, md)
        self.assertEqual(res["status"], "FAIL")
        self.assertTrue(any(f["code"] == "DECISION_DURATION_CONTRADICTED" for f in res["failures"]))

    def test_duration_same_shot_sound_borrowed_as_control_fails(self):
        intent = {
            "intent_format": "intent-handoff/v1",
            "goal": "scope test",
            "task_type": "prompt_only",
            "decisions": {
                "duration_sec": {"value": 17, "source": "user_explicit", "locked": True},
                "aspect_ratio": {"value": "16:9", "source": "user_explicit", "locked": True},
                "visual_style": {"value": {"text": "写实", "register": "photoreal"}, "source": "user_explicit", "locked": True},
            },
            "shots": [
                {"id": "shot_02", "duration_sec": 7, "description": "y", "sound_craft": "机械回响（前1.5秒）"},
            ],
            "constraints": [],
        }
        pkg = {
            "prompt_format": "prompt-package/v1",
            "node_id": "shot_02__video_candidate_A",
            "role": "video_candidate",
            "shot_id": "shot_02",
            "blocks": {
                "visual": "固定",
                "sound": "切到第二镜后滴答余响延续2秒，再只留窗外雨声。",
                "duration": "成片时长 7 秒（生成 7 秒，裁切 0–7 秒）。",
                "delivery_settings": "画幅 16:9；时长 7 秒。全片时长 17 秒。 当前镜头时长1.5秒。",
            },
            "missing_blocks": [],
            "constraint_evidence": [],
        }
        md = "## shot_02__video_candidate_A\n画幅 16:9；时长 7 秒。全片时长 17 秒。 当前镜头时长1.5秒。\n成片时长 7 秒（生成 7 秒，裁切 0–7 秒）。"
        res = verify_delivery(intent, [pkg], None, md)
        self.assertEqual(res["status"], "FAIL")
        self.assertTrue(any(f["code"] == "DECISION_DURATION_CONTRADICTED" for f in res["failures"]))

    def test_duration_performance_pause_passes(self):
        intent = {
            "intent_format": "intent-handoff/v1",
            "goal": "pause test",
            "task_type": "prompt_only",
            "decisions": {
                "duration_sec": {"value": 12, "source": "user_explicit", "locked": True},
                "aspect_ratio": {"value": "16:9", "source": "user_explicit", "locked": True},
                "visual_style": {"value": {"text": "写实", "register": "photoreal"}, "source": "user_explicit", "locked": True},
            },
            "shots": [
                {"id": "shot_01", "duration_sec": 6, "description": "x", "performance": "安慰动作前停顿0.6秒，停顿包含在本镜6秒内。"},
            ],
            "constraints": [],
        }
        pkg = {
            "prompt_format": "prompt-package/v1",
            "node_id": "shot_01__video_candidate_A",
            "role": "video_candidate",
            "shot_id": "shot_01",
            "blocks": {
                "visual": "固定",
                "action": "安慰动作前停顿0.6秒，停顿包含在本镜6秒内。",
                "duration": "成片时长 6 秒（生成 6 秒，裁切 0–6 秒）。",
                "delivery_settings": "画幅 16:9；时长 6 秒。全片时长 12 秒。",
            },
            "missing_blocks": [],
            "constraint_evidence": [],
        }
        md = "## shot_01__video_candidate_A\n画幅 16:9；时长 6 秒。全片时长 12 秒。\n成片时长 6 秒（生成 6 秒，裁切 0–6 秒）。\n安慰动作前停顿0.6秒，停顿包含在本镜6秒内。"
        res = verify_delivery(intent, [pkg], None, md)
        self.assertNotEqual(res["status"], "FAIL")

    def test_generation_differs_from_final_control_passes(self):
        intent = {
            "intent_format": "intent-handoff/v1",
            "goal": "gen test",
            "task_type": "prompt_only",
            "decisions": {
                "duration_sec": {"value": 12, "source": "user_explicit", "locked": True},
                "aspect_ratio": {"value": "16:9", "source": "user_explicit", "locked": True},
                "visual_style": {"value": {"text": "写实", "register": "photoreal"}, "source": "user_explicit", "locked": True},
            },
            "shots": [
                {"id": "shot_01", "duration_sec": 6, "generation_duration_sec": 8, "description": "x", "cut_range": {"start_sec": 0, "end_sec": 6}},
            ],
            "constraints": [],
        }
        pkg = {
            "prompt_format": "prompt-package/v1",
            "node_id": "shot_01__video_candidate_A",
            "role": "video_candidate",
            "shot_id": "shot_01",
            "blocks": {
                "visual": "固定",
                "duration": "成片时长 6 秒（生成 8 秒，裁切 0–6 秒）。",
                "delivery_settings": "画幅 16:9；时长 6 秒。全片时长 12 秒。",
            },
            "missing_blocks": [],
            "constraint_evidence": [],
        }
        md = "## shot_01__video_candidate_A\n画幅 16:9；时长 6 秒。全片时长 12 秒。\n成片时长 6 秒（生成 8 秒，裁切 0–6 秒）。"
        res = verify_delivery(intent, [pkg], None, md)
        self.assertNotEqual(res["status"], "FAIL")

    def test_generation_wrong_slot_fails(self):
        intent = {
            "intent_format": "intent-handoff/v1",
            "goal": "gen wrong test",
            "task_type": "prompt_only",
            "decisions": {
                "duration_sec": {"value": 12, "source": "user_explicit", "locked": True},
                "aspect_ratio": {"value": "16:9", "source": "user_explicit", "locked": True},
                "visual_style": {"value": {"text": "写实", "register": "photoreal"}, "source": "user_explicit", "locked": True},
            },
            "shots": [
                {"id": "shot_01", "duration_sec": 6, "generation_duration_sec": 8, "description": "x", "cut_range": {"start_sec": 0, "end_sec": 6}},
            ],
            "constraints": [],
        }
        pkg = {
            "prompt_format": "prompt-package/v1",
            "node_id": "shot_01__video_candidate_A",
            "role": "video_candidate",
            "shot_id": "shot_01",
            "blocks": {
                "visual": "固定",
                "duration": "成片时长 6 秒（生成 6 秒，裁切 0–6 秒）。",
                "delivery_settings": "画幅 16:9；时长 6 秒。全片时长 12 秒。",
            },
            "missing_blocks": [],
            "constraint_evidence": [],
        }
        md = "## shot_01__video_candidate_A\n画幅 16:9；时长 6 秒。全片时长 12 秒。\n成片时长 6 秒（生成 6 秒，裁切 0–6 秒）。"
        res = verify_delivery(intent, [pkg], None, md)
        self.assertEqual(res["status"], "FAIL")
        self.assertTrue(any(f["code"] == "DECISION_DURATION_CONTRADICTED" for f in res["failures"]))

    def test_duration_scope_same_shot_sound_timing_passes(self):
        intent = {
            "intent_format": "intent-handoff/v1",
            "goal": "scope test",
            "task_type": "prompt_only",
            "decisions": {
                "duration_sec": {"value": 12, "source": "user_explicit", "locked": True},
                "aspect_ratio": {"value": "9:16", "source": "user_explicit", "locked": True},
                "visual_style": {"value": {"text": "写实", "register": "photoreal"}, "source": "user_explicit", "locked": True},
            },
            "shots": [
                {"id": "shot_02", "duration_sec": 6, "description": "y", "sound_craft": "切到第二镜后滴答余响延续2秒，再只留窗外雨声。"},
            ],
            "constraints": [],
        }
        pkg2 = {
            "prompt_format": "prompt-package/v1",
            "node_id": "shot_02__video_candidate_A",
            "role": "video_candidate",
            "shot_id": "shot_02",
            "blocks": {"visual": "固定", "sound": "切到第二镜后滴答余响延续2秒，再只留窗外雨声。", "duration": "成片时长 6 秒。", "delivery_settings": "画幅 9:16；时长 6 秒。全片时长 12 秒。"},
            "missing_blocks": [],
            "constraint_evidence": [],
        }
        md = "## shot_02__video_candidate_A\n时长 6 秒。全片时长 12 秒。 切到第二镜后滴答余响延续2秒，再只留窗外雨声。"
        res = verify_delivery(intent, [pkg2], None, md)
        self.assertNotEqual(res["status"], "FAIL")

    def test_control_matrix_positive_and_field_permutation(self):
        """Real production fixture: final4/gen8/cut1-5 positive passes and every
        field permutation to another legal value fails."""
        audit = Path(__file__).parent / "fixtures" / "control_matrix"
        intent = json.loads((audit / "control_matrix_intent.json").read_text(encoding="utf-8"))
        packages = [
            json.loads(line)
            for line in (audit / "control_matrix_positive" / "04_prompt_packages.jsonl").read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        graph = json.loads((audit / "control_matrix_positive" / "03_shot_graph_plan.json").read_text(encoding="utf-8"))
        md = (audit / "control_matrix_positive" / "13_Final_Prompt.md").read_text(encoding="utf-8")

        positive = verify_delivery(intent, packages, graph, md)
        self.assertEqual(positive["status"], "PASS")
        self.assertEqual(positive["failures"], [])

        video = next(p for p in packages if p.get("role") == "video_candidate" and p.get("shot_id") == "fresh_01")
        changes = [
            ("final", "duration", r"(成片时长\s*)4(\s*秒)", 4),
            ("gen", "duration", r"(生成\s*)8(\s*秒)", 8),
            ("cut_start", "duration", r"(裁切\s*)1([–\-]5\s*秒)", 1),
            ("cut_end", "duration", r"(裁切\s*1[–\-])5(\s*秒)", 5),
            ("settings", "delivery_settings", r"(时长\s*)4(\s*秒)", 4),
        ]
        for field, block, pattern, truth in changes:
            for value in (4, 8, 1, 5, 17, 7, 0.6, 1.5):
                if abs(value - truth) < 1e-6:
                    continue
                packs = copy.deepcopy(packages)
                mdc = md
                p = next(p for p in packs if p.get("node_id") == video["node_id"])
                text, count = re.subn(pattern, lambda m: m.group(1) + str(value) + m.group(2), p["blocks"][block], count=1)
                self.assertEqual(count, 1, "probe must apply: %s=%s" % (field, value))
                p["blocks"][block] = text
                mdc, _ = re.subn(pattern, lambda m: m.group(1) + str(value) + m.group(2), mdc, count=1)
                res = verify_delivery(intent, packs, graph, mdc)
                self.assertEqual(
                    res["status"],
                    "FAIL",
                    "%s=%s must be rejected" % (field, value),
                )
                self.assertTrue(
                    any(f["code"] == "DECISION_DURATION_CONTRADICTED" for f in res["failures"]),
                    "%s=%s must be rejected as duration contradiction" % (field, value),
                )

    def test_control_field_permutation_with_different_numbers(self):
        """Self-contained fixture with different final/gen/cut values and a
        sound-sequence timing; verifies field-permutation property again."""
        intent = {
            "intent_format": "intent-handoff/v1",
            "goal": "variant test",
            "task_type": "prompt_only",
            "decisions": {
                "duration_sec": {"value": 15, "source": "user_explicit", "locked": True},
                "aspect_ratio": {"value": "16:9", "source": "user_explicit", "locked": True},
            },
            "shots": [
                {
                    "id": "v_01",
                    "duration_sec": 3,
                    "generation_duration_sec": 6,
                    "cut_range": {"start_sec": 2, "end_sec": 4},
                    "sound_craft": "门铃余响延续0.8秒，随后只有房间底噪。",
                }
            ],
            "constraints": [],
        }
        pkg = {
            "prompt_format": "prompt-package/v1",
            "node_id": "v_01__video_candidate_A",
            "role": "video_candidate",
            "shot_id": "v_01",
            "blocks": {
                "sound": "门铃余响延续0.8秒，随后只有房间底噪。",
                "duration": "成片时长 3 秒（生成 6 秒，裁切 2–4 秒）。",
                "delivery_settings": "画幅 16:9；时长 3 秒。全片时长 15 秒。",
            },
            "missing_blocks": [],
            "constraint_evidence": [],
        }
        md = (
            "## v_01__video_candidate_A\n"
            "画幅 16:9；时长 3 秒。全片时长 15 秒。\n"
            "成片时长 3 秒（生成 6 秒，裁切 2–4 秒）。\n"
            "门铃余响延续0.8秒，随后只有房间底噪。"
        )
        positive = verify_delivery(intent, [pkg], None, md)
        self.assertEqual(positive["status"], "PASS")

        probes = [
            # (block, pattern, wrong_value)
            ("duration", r"(成片时长\s*)3(\s*秒)", 5),
            ("duration", r"(生成\s*)6(\s*秒)", 3),
            ("duration", r"(裁切\s*)2([–\-]4\s*秒)", 1),
            ("duration", r"(裁切\s*2[–\-])4(\s*秒)", 6),
            ("delivery_settings", r"(时长\s*)3(\s*秒)", 15),
        ]
        for block, pattern, value in probes:
            bad_pkg = copy.deepcopy(pkg)
            bad_pkg["blocks"][block] = re.sub(pattern, lambda m: m.group(1) + str(value) + m.group(2), bad_pkg["blocks"][block], count=1)
            bad_md = re.sub(pattern, lambda m: m.group(1) + str(value) + m.group(2), md, count=1)
            res = verify_delivery(intent, [bad_pkg], None, bad_md)
            self.assertEqual(res["status"], "FAIL", "%s=%s must be rejected" % (block, value))
            self.assertTrue(any(f["code"] == "DECISION_DURATION_CONTRADICTED" for f in res["failures"]))

    def test_graph_intent_duration_conflict_fails(self):
        """A derived graph must not override a locked intent duration."""
        intent = {
            "intent_format": "intent-handoff/v1",
            "goal": "conflict test",
            "task_type": "prompt_only",
            "decisions": {
                "duration_sec": {"value": 10, "source": "user_explicit", "locked": True},
                "aspect_ratio": {"value": "16:9", "source": "user_explicit", "locked": True},
            },
            "shots": [
                {"id": "shot_01", "duration_sec": 4, "generation_duration_sec": 8, "cut_range": {"start_sec": 1, "end_sec": 5}},
            ],
            "constraints": [],
        }
        graph = {
            "nodes": [
                {
                    "id": "shot_01__video_candidate_A",
                    "role": "video_candidate",
                    "shot_id": "shot_01",
                    "shot_timing": {"duration_sec": 5, "generation_duration_sec": 8, "cut_range": {"start_sec": 1, "end_sec": 5}},
                }
            ]
        }
        pkg = {
            "prompt_format": "prompt-package/v1",
            "node_id": "shot_01__video_candidate_A",
            "role": "video_candidate",
            "shot_id": "shot_01",
            "blocks": {
                "duration": "成片时长 4 秒（生成 8 秒，裁切 1–5 秒）。",
                "delivery_settings": "画幅 16:9；时长 4 秒。全片时长 10 秒。",
            },
            "missing_blocks": [],
            "constraint_evidence": [],
        }
        md = (
            "## shot_01__video_candidate_A\n"
            "画幅 16:9；时长 4 秒。全片时长 10 秒。\n"
            "成片时长 4 秒（生成 8 秒，裁切 1–5 秒）。"
        )
        res = verify_delivery(intent, [pkg], graph, md)
        self.assertEqual(res["status"], "FAIL")
        self.assertTrue(
            any(f["code"] == "CONTROL_GRAPH_FINAL_CONFLICT" for f in res["failures"]),
            "graph overriding intent final must be reported",
        )


    def test_whole_film_total_duration_declarations(self):
        """Totals retain their scope even when equal to a single shot duration."""
        from scripts.compile_intent_delivery import build_copyable_markdown
        fixture = Path(__file__).parent / "fixtures" / "control_matrix"
        intent = json.loads((fixture / "control_matrix_intent.json").read_text(encoding="utf-8"))
        positive = fixture / "control_matrix_positive"
        packages = [json.loads(line) for line in (positive / "04_prompt_packages.jsonl").read_text(encoding="utf-8").splitlines() if line.strip()]
        graph = json.loads((positive / "03_shot_graph_plan.json").read_text(encoding="utf-8"))
        original_md = (positive / "13_Final_Prompt.md").read_text(encoding="utf-8")
        video = next(p for p in packages if p.get("role") == "video_candidate")
        total = intent["decisions"]["duration_sec"]["value"]
        shot = next(s for s in intent["shots"] if s["id"] == video["shot_id"])["duration_sec"]
        self.assertNotEqual(total, shot, "fixture must distinguish whole film from shot")
        for label in ("全片总时长", "总时长", "整片总时长", "完整影片总时长", "全片时长"):
            for value, expected in ((total, "PASS"), (shot, "FAIL")):
                for target in ("package", "markdown", "both"):
                    with self.subTest(label=label, value=value, target=target):
                        changed = copy.deepcopy(packages)
                        row = next(p for p in changed if p["node_id"] == video["node_id"])
                        row["blocks"]["delivery_settings"] += " %s %s 秒。" % (label, value)
                        changed_md = build_copyable_markdown(changed)
                        result = verify_delivery(intent, changed if target != "markdown" else packages, graph, changed_md if target != "package" else original_md)
                        self.assertEqual(result["status"], expected, result["failures"])
                        if expected == "FAIL":
                            self.assertTrue(any(f["code"] == "DECISION_DURATION_CONTRADICTED" for f in result["failures"]))


if __name__ == "__main__":
    unittest.main()
