from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class V62BitmapPlatformContractTests(unittest.TestCase):
    def test_mac_bitmap_skeleton_uses_one_left_anchor_without_changing_deconstruct(self):
        source = (ROOT / "assets" / "python_pptx_generator_template_v2.py").read_text(
            encoding="utf-8"
        )
        self.assertIn('bitmap_skeleton = DECK_META["construction_mode"] == "bitmap"', source)
        self.assertIn("title_left = 0.56 if bitmap_skeleton else 0.60", source)
        self.assertIn("core_left = 0.56 if bitmap_skeleton else 0.64", source)

    def test_windows_and_mac_build_from_the_company_template(self):
        windows = (ROOT / "assets" / "direct_blueprint_generator_template.py").read_text(
            encoding="utf-8"
        )
        mac = (ROOT / "assets" / "python_pptx_generator_template_v2.py").read_text(
            encoding="utf-8"
        )
        self.assertIn("Presentations.Open", windows)
        self.assertIn("Presentation(template)", mac)
        self.assertIn("first_layout = presentation.slides[0].slide_layout", mac)

    def test_bitmap_postbuild_audit_checks_master_alignment_and_image_effects(self):
        source = (ROOT / "scripts" / "v6_editability_audit.py").read_text(
            encoding="utf-8"
        )
        self.assertIn("_bitmap_template_errors", source)
        self.assertIn("upper skeleton layers must share one left anchor", source)
        self.assertIn("body picture must not contain shadow, reflection, glow, or soft-edge effects", source)


if __name__ == "__main__":
    unittest.main()
