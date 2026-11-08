"""Explicit style text survives metadata classification without unrelated craft."""
import unittest
from tests.test_quality_fixes_20261025 import make_intent, compile_intent

class StyleRegisterAuthorityTests(unittest.TestCase):
    def test_unlisted_crafts_do_not_acquire_register_defaults(self):
        for style in ('油画', '黏土定格'):
            for register in ('photoreal', 'stylized', 'illustration', 'graphic'):
                with self.subTest(style=style, register=register):
                    final, packages = compile_intent(make_intent(style, register))
                    self.assertIn(style, final)
                    for phrase in ('真实材质，自然光，避免塑料感和拼贴感',
                                   '插画式平涂色块与线条', '平面图形语言，形状与色块为主'):
                        self.assertNotIn(phrase, final)
                        for package in packages:
                            self.assertNotIn(phrase, package['blocks'].get('visual', ''))

    def test_negative_photoreal_text_does_not_trigger_photographic_default(self):
        final, _ = compile_intent(make_intent('非写实油画，保留画布笔触', 'photoreal'))
        self.assertIn('非写实油画，保留画布笔触', final)
        self.assertNotIn('真实材质，自然光，避免塑料感和拼贴感', final)

if __name__ == '__main__':
    unittest.main()
