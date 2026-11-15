"""Runtime failures must stay bounded and cannot become successful evidence."""
import contextlib
import io
import json
import os
import shlex
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))

import consensus_cuts
import mutation_check
import proc


def shell_command(code):
    args = [sys.executable, '-c', code]
    return subprocess.list2cmdline(args) if os.name == 'nt' else shlex.join(args)


class ProcessBoundaryTests(unittest.TestCase):
    def test_shell_child_timeout_returns_before_the_child_finishes(self):
        with tempfile.TemporaryDirectory() as directory:
            marker = Path(directory) / 'child-finished'
            code = ('import time; from pathlib import Path; time.sleep(4); '
                    'Path(%r).write_text("survived")' % str(marker))
            started = time.monotonic()
            result = proc.run(shell_command(code), shell=True, capture_output=True,
                              text=True, timeout=0.5)
            elapsed = time.monotonic() - started
            self.assertEqual(result.returncode, proc.TIMEOUT_RC)
            self.assertLess(elapsed, 3, 'a shell descendant held the output pipe open')
            time.sleep(max(0, 4.5 - (time.monotonic() - started)))
            self.assertFalse(marker.exists(), 'the timed-out shell child kept running')

    def test_input_capture_and_text_options_survive_the_wrapper(self):
        result = proc.run(shell_command('import sys; print(sys.stdin.read().upper()); '
                                        'print("detail", file=sys.stderr)'),
                          shell=True, input='sample', capture_output=True,
                          encoding='utf-8', check=True, timeout=10)
        self.assertEqual(result.stdout, 'SAMPLE\n')
        self.assertEqual(result.stderr, 'detail\n')

    def test_byte_input_and_merged_output_survive_the_wrapper(self):
        result = proc.run([sys.executable, '-c', 'import sys; '
                           'sys.stdout.buffer.write(sys.stdin.buffer.read())'],
                          input=b'bytes', stdout=subprocess.PIPE,
                          stderr=subprocess.STDOUT, timeout=10)
        self.assertEqual(result.stdout, b'bytes')
        self.assertIsNone(result.stderr)

    def test_checked_failure_keeps_the_exit_code_and_captured_output(self):
        with self.assertRaises(subprocess.CalledProcessError) as raised:
            proc.run(shell_command('import sys; print("failed"); sys.exit(7)'),
                     shell=True, capture_output=True, text=True, check=True, timeout=10)
        self.assertEqual(raised.exception.returncode, 7)
        self.assertEqual(raised.exception.stdout, 'failed\n')

    def test_timeout_still_returns_failed_result_when_check_is_enabled(self):
        result = proc.run([sys.executable, '-c', 'import time; time.sleep(4)'],
                          capture_output=True, check=True, timeout=0.2)
        self.assertEqual(result.returncode, proc.TIMEOUT_RC)
        self.assertIn(b'timed out', result.stderr)

    def test_conflicting_input_options_are_rejected(self):
        with self.assertRaises(ValueError):
            proc.run([sys.executable, '-c', 'pass'], input=b'x', stdin=subprocess.PIPE)
        with self.assertRaises(ValueError):
            proc.run([sys.executable, '-c', 'pass'], capture_output=True,
                     stdout=subprocess.PIPE)


class MutationTimeoutTests(unittest.TestCase):
    def test_timeout_is_unverified_and_restores_original_bytes(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / 'target.py'
            original = b'GOOD = 1\r\n'
            target.write_bytes(original)
            with patch.object(mutation_check, '_run',
                              side_effect=[(0, 'OK'), (proc.TIMEOUT_RC, '')]):
                code, messages = mutation_check.check(
                    str(target), 'GOOD', 'BAD', 'unused', 'OK', directory)
            self.assertEqual(code, 3, '\n'.join(messages))
            self.assertEqual(target.read_bytes(), original)
            self.assertFalse(any(line.startswith('[证据]') for line in messages))


class ConsensusFailureTests(unittest.TestCase):
    def test_failed_detection_never_writes_a_consensus_report(self):
        for returncode in (1, proc.TIMEOUT_RC):
            with self.subTest(returncode=returncode), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                shots = root / 'shots.json'
                shots.write_text(json.dumps([{'start': 0}]), encoding='utf-8')
                out = root / 'report'
                finished = subprocess.CompletedProcess(
                    ['ffmpeg'], returncode, b'pts_time:1.5\n', b'timed out')
                backend = SimpleNamespace(get_ffmpeg_exe=lambda: 'ffmpeg')
                argv = ['consensus_cuts.py', 'source.mp4', '--shots', str(shots),
                        '--out', str(out)]
                with patch.object(consensus_cuts, '_require_video_backend', return_value=True), \
                        patch.object(consensus_cuts, 'imageio_ffmpeg', backend), \
                        patch.object(consensus_cuts.proc, 'run', return_value=finished), \
                        patch.object(sys, 'argv', argv), \
                        contextlib.redirect_stderr(io.StringIO()) as errors, \
                        contextlib.redirect_stdout(io.StringIO()):
                    code = consensus_cuts.main()
                self.assertNotEqual(code, 0)
                self.assertFalse((out / 'consensus.json').exists())
                self.assertTrue(errors.getvalue())


if __name__ == '__main__':
    unittest.main()
