import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import scripts.libtv_orchestrate as orch

ORCH = Path(__file__).resolve().parents[1] / "scripts" / "libtv_orchestrate.py"
PY = sys.executable


class DigestHashSeedTests(unittest.TestCase):
    def _run(self, hash_seed):
        with tempfile.TemporaryDirectory() as td:
            report = Path(td) / "report.json"
            env = dict(os.environ)
            env["PYTHONHASHSEED"] = str(hash_seed)
            env["PYTHONIOENCODING"] = "utf-8"
            proc = subprocess.run(
                [PY, str(ORCH), "--self-test", "--profile", "local", "--json", "--json-out", str(report)],
                capture_output=True,
                text=True,
                env=env,
            )
            self.assertEqual(proc.returncode, 0, proc.stderr)
            payload = json.loads(report.read_text(encoding="utf-8"))
            digest = Path(str(report) + ".sha256").read_text(encoding="utf-8").strip()
            return payload, digest

    def test_hash_seed_invariance(self):
        first_payload, first_digest = self._run(0)
        second_payload, second_digest = self._run(1)
        self.assertEqual(first_payload, second_payload)
        self.assertEqual(first_digest, second_digest)
        expected_passed = 140 + (6 if orch._tool("ffmpeg") else 0)
        expected_passed -= int(bool(orch._tool("ffmpeg") and orch._tool("ffprobe")))
        self.assertEqual(first_payload["passed"], expected_passed)
        self.assertEqual(first_payload["failed"], 0)
        self.assertEqual(first_payload["skipped"], 0)


if __name__ == "__main__":
    unittest.main()
