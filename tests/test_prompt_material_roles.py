import json
import tempfile
import unittest
from pathlib import Path

from scripts.compile_intent_delivery import compile_intent_delivery

ROOT = Path(__file__).resolve().parents[1]


class PromptMaterialRolesTests(unittest.TestCase):
    def test_prompt_only_does_not_instruct_use_of_unmade_reference_images(self):
        intent = json.loads((ROOT / "samples" / "papercut_empty_shot_intent.json").read_text(encoding="utf-8"))
        with tempfile.TemporaryDirectory() as directory:
            result = compile_intent_delivery(intent, Path(directory))
            self.assertEqual(result["verification"]["status"], "PASS")
            videos = [p for p in result["prompts"] if p["role"] == "video_candidate"]
            self.assertTrue(videos)
            for package in videos:
                material = str(package["blocks"]["material_roles"])
                for unavailable in ("场景参考：", "身份参考：", "构图参考：", "{{Node"):
                    self.assertNotIn(unavailable, material)
            markdown = Path(result["copyable_markdown"]).read_text(encoding="utf-8")
            for unavailable in ("场景参考：", "身份参考：", "构图参考：", "{{Node"):
                self.assertNotIn(unavailable, markdown)


if __name__ == "__main__":
    unittest.main()
