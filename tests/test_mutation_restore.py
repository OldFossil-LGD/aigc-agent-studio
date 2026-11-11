"""A failed restore must not be reported as a caught mutation.

check() used to return "caught" from inside the try block; the finally block
could only append a warning, so a polluted file still returned 0.
"""
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))

import mutation_check as mc


class RestoreFailureTests(unittest.TestCase):
    def test_restore_failure_overrides_caught(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / 'sample.py'
            target.write_text('MUTATE_ME\n', encoding='utf-8')
            # 基线绿 → 变异后红（应判 caught=0）→ 但还原哈希不一致，必须盖成 3
            # 变了之后测试必须以非 0 退出，否则不算"抓住"
            outputs = [(0, 'OK'), (1, 'FAILED (failures=1)')]
            with patch.object(mc, '_run', side_effect=lambda *a, **k: outputs.pop(0)), \
                 patch.object(mc, '_file_sha', side_effect=['before', 'after']):
                rc, out = mc.check(str(target), 'MUTATE_ME', 'CHANGED', 'whatever', 'OK', tmp)
        self.assertEqual(rc, 3, '\n'.join(out))
        self.assertTrue(any('还原失败' in line for line in out), out)

    def test_caught_mutation_still_returns_zero_when_restore_is_clean(self):  # noqa: D401
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / 'sample.py'
            target.write_text('MUTATE_ME\n', encoding='utf-8')
            outputs = [(0, 'OK'), (1, 'FAILED (failures=1)')]
            with patch.object(mc, '_run', side_effect=lambda *a, **k: outputs.pop(0)):
                rc, _ = mc.check(str(target), 'MUTATE_ME', 'CHANGED', 'whatever', 'OK', tmp)
        self.assertEqual(rc, 0)

    def test_zero_exit_with_missing_marker_is_not_a_catch(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / 'sample.py'
            target.write_text('MUTATE_ME\n', encoding='utf-8')
            # 字样消失但进程仍 0：不能算抓住
            outputs = [(0, 'OK'), (0, 'something else')]
            with patch.object(mc, '_run', side_effect=lambda *a, **k: outputs.pop(0)):
                rc, _ = mc.check(str(target), 'MUTATE_ME', 'CHANGED', 'whatever', 'OK', tmp)
        self.assertEqual(rc, 1)

    def test_load_failure_is_not_a_catch(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / 'sample.py'
            target.write_text('MUTATE_ME\n', encoding='utf-8')
            # 导入/语法错误也会让 "OK" 消失，但那不是门禁在查
            outputs = [(0, 'OK'), (1, 'ImportError: cannot import name x')]
            with patch.object(mc, '_run', side_effect=lambda *a, **k: outputs.pop(0)):
                rc, _ = mc.check(str(target), 'MUTATE_ME', 'CHANGED', 'whatever', 'OK', tmp)
        self.assertEqual(rc, 3)


if __name__ == '__main__':
    unittest.main()
