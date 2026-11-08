import importlib.util
import os
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest import mock
from scripts import apply_libtv_plan as adapter

class ReleasePortabilityTests(unittest.TestCase):
    def test_explicit_cli_override_precedes_path(self):
        with tempfile.TemporaryDirectory() as td:
            expected = Path(td) / 'My Tools' / 'libtv-custom'
            with mock.patch.dict(os.environ, {'LIBTV_BIN': str(expected)}, clear=True), mock.patch('shutil.which', return_value=str(Path(td) / 'other')):
                self.assertEqual(adapter.resolve_libtv_binary(), expected)

    def test_path_cli_is_used_without_override(self):
        with tempfile.TemporaryDirectory() as td:
            expected = Path(td) / 'bin' / 'libtv'
            with mock.patch.dict(os.environ, {}, clear=True), mock.patch('shutil.which', return_value=str(expected)):
                self.assertEqual(adapter.resolve_libtv_binary(), expected)

    def test_home_install_is_user_relative(self):
        with tempfile.TemporaryDirectory() as td:
            home = Path(td) / 'different user'
            expected = home / '.libtv' / ('libtv.exe' if os.name == 'nt' else 'libtv')
            expected.parent.mkdir(parents=True)
            expected.write_bytes(b'not executed')
            with mock.patch.dict(os.environ, {}, clear=True), mock.patch('shutil.which', return_value=None), mock.patch('pathlib.Path.home', return_value=home):
                self.assertEqual(adapter.resolve_libtv_binary(), expected)

    def test_no_cli_still_allows_offline_plan_building(self):
        with tempfile.TemporaryDirectory() as td:
            with mock.patch.dict(os.environ, {}, clear=True), mock.patch('shutil.which', return_value=None), mock.patch('pathlib.Path.home', return_value=Path(td)):
                resolved = adapter.resolve_libtv_binary()
                self.assertEqual(resolved, Path('libtv'))
                with mock.patch.object(adapter, 'LIBTV', resolved):
                    phases = adapter.build_phases({'commands': []}, 'offline-example')
                    self.assertEqual(phases['nodes'], [])

    def test_digest_test_targets_this_checkout(self):
        path = Path(__file__).with_name('test_digest_hashseed.py')
        spec = importlib.util.spec_from_file_location('relocated_digest_test', path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        expected = Path(__file__).resolve().parents[1] / 'scripts' / 'libtv_orchestrate.py'
        self.assertEqual(module.ORCH, expected)

if __name__ == '__main__':
    unittest.main()
