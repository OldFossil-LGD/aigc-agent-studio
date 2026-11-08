import json
import subprocess
import sys
import unittest
from pathlib import Path

import scripts.libtv_orchestrate as orch

SCRIPT_DIR = Path(__file__).resolve().parents[1] / "scripts"
ORCH = SCRIPT_DIR / "libtv_orchestrate.py"
GATE = SCRIPT_DIR / "libtv_model_rules_gate.py"
PY = sys.executable


class AuditStateSnapshotTests(unittest.TestCase):
    def _run_self_test(self, profile, force_skip=False):
        original = orch._tmpdir
        if force_skip:
            orch._tmpdir = lambda prefix="orch_": None
        buffer = __import__("io").StringIO()
        try:
            with __import__("contextlib").redirect_stdout(buffer):
                rc = orch.cmd_self_test(["--self-test", "--profile", profile, "--json"])
        finally:
            orch._tmpdir = original
        payload = None
        for line in buffer.getvalue().splitlines():
            line = line.strip()
            if line.startswith("{") and line.endswith("}"):
                try:
                    payload = json.loads(line)
                except json.JSONDecodeError:
                    pass
        return rc, payload

    def test_local_snapshot(self):
        rc, payload = self._run_self_test("local")
        self.assertEqual(rc, 0)
        self.assertEqual(payload, {
            "profile": "local",
            "passed": 140 + (6 if orch._tool("ffmpeg") else 0)
                      - (1 if orch._tool("ffmpeg") and orch._tool("ffprobe") else 0),
            "failed": 0,
            "skipped": 0,
            "skipped_ids": [],
        })

    def test_sandbox_snapshot(self):
        rc, payload = self._run_self_test("sandbox-readonly", force_skip=True)
        self.assertEqual(rc, 0)
        self.assertEqual(payload, {
            "profile": "sandbox-readonly",
            "passed": 104 if orch._tool("ffmpeg") else 105,
            "failed": 0,
            "skipped": 4 if orch._tool("ffmpeg") else 3,
            "skipped_ids": [
                "preflight_probe",
                *(["ffmpeg_frame_checks"] if orch._tool("ffmpeg") else []),
                "verify_evidence_pack",
                "pipeline_compile_resume_e2e",
            ],
        })

    def test_gate_snapshot(self):
        proc = subprocess.run(
            [PY, str(GATE), "--self-test"],
            capture_output=True,
            text=True,
            encoding="utf-8",
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        start = proc.stdout.find("{")
        payload = json.loads(proc.stdout[start:])
        self.assertEqual(payload["passed"], 74)
        self.assertEqual(payload["failed"], 0)


if __name__ == "__main__":
    unittest.main()
