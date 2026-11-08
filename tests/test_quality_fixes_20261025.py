import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PYTHON = Path(sys.executable)
COMPILE = ROOT / "scripts" / "compile_intent_delivery.py"


def make_intent(style_text, register, *, style_detail=None, style_notes=None,
                technique=None, extra_text=None):
    shot = {
        "id": "shot_01",
        "duration_sec": 5,
        "shot_kind": "empty",
        "description": "空镜，固定机位，无人物。",
    }
    if style_detail is not None:
        shot["style_detail"] = style_detail
    if style_notes is not None:
        shot["style_notes"] = style_notes
    value = {"text": style_text, "register": register}
    if technique is not None:
        value["technique"] = technique
    intent = {
        "intent_format": "intent-handoff/v1",
        "goal": "回归测试：风格文本与工艺消费。",
        "task_type": "prompt_only",
        "decisions": {
            "duration_sec": {"value": 5, "source": "user_explicit", "locked": True},
            "aspect_ratio": {"value": "16:9", "source": "user_explicit", "locked": True},
            "visual_style": {"value": value, "source": "user_explicit", "locked": True},
        },
        "shots": [shot],
        "constraints": [],
        "sound": {
            "mode": "ambience_only",
            "allowed": ["环境声"],
            "forbidden": ["人声", "对白", "旁白", "音乐"],
            "source": "user_explicit",
            "locked": True,
        },
    }
    return intent


def compile_intent(intent):
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        intent_path = tmp_path / "intent.json"
        out_path = tmp_path / "out"
        intent_path.write_text(json.dumps(intent, ensure_ascii=False), encoding="utf-8")
        proc = subprocess.run(
            [str(PYTHON), "-X", "utf8", "-B", str(COMPILE),
             str(intent_path), "--out", str(out_path), "--draft"],
            cwd=str(ROOT),
            capture_output=True,
            text=True,
            encoding="utf-8",
        )
        if proc.returncode != 0:
            raise AssertionError(
                "compile failed: %s\nstdout=%s\nstderr=%s"
                % (proc.returncode, proc.stdout, proc.stderr)
            )
        final = (out_path / "13_Draft_Prompt.md").read_text(encoding="utf-8")
        packages = [
            json.loads(line)
            for line in (out_path / "04_prompt_packages.jsonl").read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        return final, packages


class QualityFix20261025Tests(unittest.TestCase):
    def test_watercolor_does_not_get_register_specific_craft(self):
        forbidden = (
            "插画式平涂色块与线条",
            "平面图形语言，形状与色块为主",
            "真实材质，自然光，避免塑料感和拼贴感",
        )
        for register in ("photoreal", "stylized", "illustration", "graphic"):
            intent = make_intent("水彩", register)
            final, _ = compile_intent(intent)
            self.assertIn("水彩", final)
            for text in forbidden:
                self.assertNotIn(text, final, "register=%s still adds %r" % (register, text))

    def test_explicit_flat_color_text_is_preserved(self):
        intent = make_intent("平涂插画", "illustration")
        final, _ = compile_intent(intent)
        self.assertIn("平涂", final)

    def test_explicit_craft_passes_through(self):
        detail = "手绘平涂色块与纸纹肌理，边缘清楚。"
        notes = "左侧单光源保留因果，不增加第二光源。"
        intent = make_intent(
            "水彩", "illustration",
            style_detail=detail, style_notes=notes, technique="湿边晕染",
        )
        final, packages = compile_intent(intent)
        self.assertIn(detail, final)
        self.assertIn(notes, final)
        self.assertIn("湿边晕染", final)
        visual = " ".join(p["blocks"].get("visual", "") for p in packages)
        self.assertIn(detail, visual)

    def test_normal_photoreal_style_still_gets_photoreal_default(self):
        intent = make_intent("写实", "photoreal")
        final, _ = compile_intent(intent)
        self.assertIn("真实材质，自然光，避免塑料感和拼贴感。", final)


if __name__ == "__main__":
    unittest.main()