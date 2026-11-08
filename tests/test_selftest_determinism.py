import contextlib
import io
import json
import os
import tempfile
import unittest
from pathlib import Path

import scripts.libtv_orchestrate as orch


class SelfTestDeterminismTests(unittest.TestCase):
    def _run_self_test(self, profile, force_skip=False, json_out=None):
        argv = ["--self-test", "--profile", profile, "--json"]
        if json_out is not None:
            argv += ["--json-out", str(json_out)]
        original_tmpdir = orch._tmpdir
        if force_skip:
            orch._tmpdir = lambda prefix="orch_": None
        buffer = io.StringIO()
        try:
            with contextlib.redirect_stdout(buffer):
                rc = orch.cmd_self_test(argv)
        finally:
            orch._tmpdir = original_tmpdir
        output = buffer.getvalue()
        payload = None
        for line in output.splitlines():
            line = line.strip()
            if line.startswith("{") and line.endswith("}"):
                try:
                    payload = json.loads(line)
                except json.JSONDecodeError:
                    pass
        return rc, payload, output

    def test_local_contract(self):
        rc, payload, _ = self._run_self_test("local")
        self.assertEqual(rc, 0)
        self.assertEqual(payload, {
            "profile": "local",
            "passed": 140 + (6 if orch._tool("ffmpeg") else 0)
                      - (1 if orch._tool("ffmpeg") and orch._tool("ffprobe") else 0),
            "failed": 0,
            "skipped": 0,
            "skipped_ids": [],
        })

    def test_sandbox_contract_and_skip_ids(self):
        rc, payload, _ = self._run_self_test("sandbox-readonly", force_skip=True)
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

    def test_deterministic_digest(self):
        with tempfile.TemporaryDirectory() as td:
            first = Path(td) / "first.json"
            second = Path(td) / "second.json"
            rc1, payload1, _ = self._run_self_test("local", json_out=first)
            rc2, payload2, _ = self._run_self_test("local", json_out=second)
            self.assertEqual(rc1, 0)
            self.assertEqual(rc2, 0)
            self.assertEqual(payload1, payload2)
            first_digest = (Path(str(first) + ".sha256")).read_text(encoding="utf-8").strip()
            second_digest = (Path(str(second) + ".sha256")).read_text(encoding="utf-8").strip()
            self.assertEqual(first_digest, second_digest)
            self.assertEqual(len(first_digest), 64)


if __name__ == "__main__":
    unittest.main()
