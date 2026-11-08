import contextlib
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import canonical_prompt


class CanonicalFileTests(unittest.TestCase):
    def test_multishot_survives_public_file_entry_points(self):
        packages = [{"role": "video_candidate", "node_id": node, "blocks": {"action": action, "sound": sound}} for node, action, sound in [("S1", "FIRST_ACTION", "FIRST_SOUND"), ("S2", "SECOND_ACTION", "SECOND_SOUND")]]
        with tempfile.TemporaryDirectory() as temp:
            source = Path(temp) / "packages.jsonl"
            target = Path(temp) / "rendered.md"
            source.write_text("\n".join(json.dumps(row) for row in packages), encoding="utf-8")
            rendered = canonical_prompt.render_from_file(source, header="# Custom header")
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(canonical_prompt.main(["--packages", str(source), "--out", str(target)]), 0)
            for text in [rendered, target.read_text(encoding="utf-8")]:
                for value in ["FIRST_ACTION", "FIRST_SOUND", "SECOND_ACTION", "SECOND_SOUND", "## S1", "## S2"]:
                    self.assertIn(value, text)
                self.assertEqual(text.count("【9 · 时间线】"), 2)
            self.assertTrue(rendered.startswith("# Custom header"))

    def test_single_shot_fallback_remains_available(self):
        with tempfile.TemporaryDirectory() as temp:
            source = Path(temp) / "packages.jsonl"
            source.write_text(json.dumps({"role": "video_candidate", "blocks": {"sound": "RAIN"}}), encoding="utf-8")
            text = canonical_prompt.render_from_file(source, shot={"description": "FALLBACK_ACTION"})
            self.assertIn("FALLBACK_ACTION", text)
            self.assertEqual(text.count("【9 · 时间线】"), 1)


if __name__ == "__main__":
    unittest.main()
