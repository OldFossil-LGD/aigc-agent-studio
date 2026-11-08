"""Media QC must propagate the real child gate status and expectations."""
import contextlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from scripts import media_qc

class MediaQCEntryTests(unittest.TestCase):

    def test_real_invalid_media_cannot_report_pass_or_argument_error(self):
        with tempfile.TemporaryDirectory() as temp:
            video = Path(temp) / 'not_video.txt'
            video.write_text('not a video', encoding='utf-8')
            rc, payload = media_qc.run_gate(str(video))
            self.assertNotEqual(rc, 2, payload)
            with contextlib.redirect_stdout(io.StringIO()) as out:
                code = media_qc.main(['--video', str(video)])
            self.assertNotEqual(code, 0, out.getvalue())
            self.assertNotEqual(json.loads(out.getvalue())['status'], 'PASS')

    def test_nonverified_and_tool_errors_keep_their_status(self):
        for rc, status in [(2, 'ERROR'), (3, 'NOT_VERIFIED'), (4, 'WARN')]:
            with self.subTest(rc=rc), patch.object(media_qc, 'run_gate', return_value=(rc, {'raw': 'child failure'})), contextlib.redirect_stdout(io.StringIO()) as out:
                code = media_qc.main(['--video', 'source.mp4', '--repair-plan'])
            self.assertEqual(code, rc)
            report = json.loads(out.getvalue())
            self.assertEqual(report['status'], status)
            self.assertFalse(report.get('repair_plan'))

    def test_unparsed_success_is_not_verified_success(self):
        with patch.object(media_qc, 'run_gate', return_value=(0, {'raw': 'not JSON'})), contextlib.redirect_stdout(io.StringIO()) as out:
            code = media_qc.main(['--video', 'source.mp4'])
        self.assertNotEqual(code, 0)
        self.assertNotEqual(json.loads(out.getvalue())['status'], 'PASS')

    def test_ir_expectations_reach_real_gate_arguments(self):
        from subprocess import CompletedProcess
        with tempfile.TemporaryDirectory() as temp:
            video = Path(temp) / 'source.mp4'
            video.write_bytes(b'synthetic test bytes')
            ir = Path(temp) / 'ir.json'
            ir.write_text(json.dumps({'project': {'delivery': {'duration_sec': 5, 'aspect_ratio': {'value': '9:16'}, 'fps': {'value': 24}}}, 'shots': []}), encoding='utf-8')
            with patch.object(media_qc.subprocess, 'run', return_value=CompletedProcess([], 0, json.dumps({'status': 'PASS', 'failures': []}), '')) as child, contextlib.redirect_stdout(io.StringIO()) as out:
                code = media_qc.main(['--video', str(video), '--ir', str(ir)])
            self.assertEqual(code, 0, out.getvalue())
            command = child.call_args.args[0]
            for flag, value in [('--video', str(video)), ('--expect-duration', '5'), ('--expect-ratio', '9:16'), ('--expect-fps', '24')]:
                self.assertEqual(command[command.index(flag) + 1], value)

    def test_segment_times_map_to_actual_shots_and_global_failures_stay_unmapped(self):
        shots = [{'shot_id': 's1', 'start': 0, 'end': 5}, {'shot_id': 's2', 'start': 5, 'end': 10}]
        issues = media_qc.normalize({'failures': [{'code': 'BLACK_FRAMES', 'segments': [{'black_start': 7, 'black_end': 8}]}, {'code': 'DURATION_MISMATCH', 'expected': 10, 'actual': 12}]}, shots)
        self.assertEqual([i['shot_id'] for i in issues], ['s2', None])
if __name__ == '__main__':
    unittest.main()
