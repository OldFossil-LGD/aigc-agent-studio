import unittest
from pathlib import Path

from scripts.knowledge_catalog import build_catalog

ROOT = Path(__file__).resolve().parents[1]


class CatalogDomainRegressionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.entries = build_catalog(ROOT)["entries"]

    def test_music_reference_is_discoverable_in_sound_domain(self):
        self.assertIn("sound", self.entries["references/music-craft.md"]["domains"])

    def test_script_directory_does_not_make_every_implementation_narrative(self):
        for source in ("scripts/_common.py", "scripts/lib_health.py"):
            with self.subTest(source=source):
                self.assertNotIn("story_direction", self.entries[source]["domains"])
                self.assertIn("implementation_publication", self.entries[source]["domains"])

    def test_actual_script_source_remains_in_narrative_domain(self):
        self.assertIn("story_direction", self.entries["scripts/script_lint.py"]["domains"])


if __name__ == "__main__":
    unittest.main()
