import importlib
import unittest
from pathlib import Path
from unittest import mock

from scripts import libtv_canvas_build, wiring_plan


class PublicationPortabilityTests(unittest.TestCase):
    def test_adapters_use_shared_binary_resolution(self):
        expected = Path('different user') / 'tools' / 'libtv-custom'
        for module in (libtv_canvas_build, wiring_plan):
            with self.subTest(module=module.__name__):
                original = module.LIBTV
                try:
                    with mock.patch('scripts.apply_libtv_plan.resolve_libtv_binary', return_value=expected):
                        importlib.reload(module)
                    self.assertEqual(str(module.LIBTV), str(expected))
                finally:
                    module.LIBTV = original


if __name__ == '__main__':
    unittest.main()
