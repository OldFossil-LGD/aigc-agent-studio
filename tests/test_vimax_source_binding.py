import hashlib
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import filmdsl_bridge
import vimax_backend_compile

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = Path(filmdsl_bridge.FIXTURES) / "base"


class VimaxSourceBindingTests(unittest.TestCase):
    def test_public_cli_preserves_original_bytes_and_source_hash(self):
        for workflow, flag in [("script2video", "--script"), ("novel2video", "--novel")]:
            for data in [b"Source screenplay\n\n", b"Source screenplay\r\n\r\n", "中文源文".encode("utf-8")]:
                with self.subTest(workflow=workflow, data=data), tempfile.TemporaryDirectory() as temp:
                    folder = Path(temp)
                    source = folder / "source.txt"
                    output = folder / "job"
                    source.write_bytes(data)
                    result = subprocess.run([sys.executable, str(ROOT / "scripts/vimax_backend_compile.py"), "--artifacts", str(FIXTURE), "--out", str(output), "--workflow", workflow, flag, str(source)], capture_output=True, text=True, encoding="utf-8", env=dict(os.environ, PYTHONIOENCODING="utf-8", PYTHONUTF8="1"))
                    self.assertIn(result.returncode, [0, 4], result.stdout + result.stderr)
                    job = json.loads((output / "vimax_job.json").read_text(encoding="utf-8"))
                    relative = "script.txt" if workflow == "script2video" else "novel/novel.txt"
                    staged = (output / "vimax_session" / workflow / relative).read_bytes()
                    self.assertEqual(staged, data)
                    self.assertEqual(job["source"]["sha256"], hashlib.sha256(staged).hexdigest())
                    self.assertFalse(job["render"]["run"])
                    self.assertFalse(job["studio"]["generation_authorized"])

    def test_invalid_source_hash_is_rejected_before_writes(self):
        art = filmdsl_bridge.load_artifacts(str(FIXTURE))
        source = {"kind": "script", "text": "source", "sha256": "wrong", "explicit": True}
        with tempfile.TemporaryDirectory() as temp:
            output = Path(temp) / "job"
            job, issues = vimax_backend_compile.compile_job(art, "script2video", source, str(output))
            self.assertIsNone(job)
            self.assertIn("SOURCE_HASH_MISMATCH", [row["code"] for row in issues])
            self.assertFalse(output.exists())


if __name__ == "__main__":
    unittest.main()
