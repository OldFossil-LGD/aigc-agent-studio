"""The optional video backend must never break import or hide the reason."""
import os
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ['consensus_cuts', 'film_contact_sheets', 'reverse_shotlist', 'subtitle_bands']
BLOCK = ("import sys\n"
         "for name in ('cv2', 'numpy', 'imageio_ffmpeg'): sys.modules[name] = None\n")


def run(code):
    return subprocess.run([sys.executable, '-c', BLOCK + code], capture_output=True,
                          text=True, encoding='utf-8', cwd=str(ROOT),
                          env=dict(os.environ, PYTHONPATH=str(ROOT),
                                   PYTHONIOENCODING='utf-8', PYTHONUTF8='1', PATH=''))


class OptionalBackendTests(unittest.TestCase):
    def test_modules_import_without_the_video_backend(self):
        for name in SCRIPTS:
            with self.subTest(script=name):
                result = run("import scripts.%s as m; print('ok')" % name)
                self.assertEqual(result.returncode, 0, result.stderr[-400:])
                self.assertIn('ok', result.stdout)

    def test_guard_explains_the_missing_backend(self):
        for name in SCRIPTS:
            with self.subTest(script=name):
                result = run("import scripts.%s as m\n"
                             "raise SystemExit(0 if not m._require_video_backend() else 1)" % name)
                self.assertEqual(result.returncode, 0, result.stderr[-400:])
                self.assertIn('pip install', result.stderr)
                self.assertIn('aigc-agent-studio[video]', result.stderr)
                self.assertNotIn('Traceback', result.stderr)


if __name__ == '__main__':
    unittest.main()
