from __future__ import annotations

import hashlib
import unittest
from pathlib import Path

from tests.boundary_hash import frozen_sha256


SKILL = Path(__file__).resolve().parents[1]
FROZEN_SHA256 = {
    "prompts/page_outline_prompt.md":
        "34c6b589461849d749fccc5009d54b73e4f3e24359e0e44450902b79d59c8709",
    "prompts/imagegen_blueprint_prompt.md":
        "333b68c57240704baa5695900ee8bff4cc4c3ffe69310c0e04ccde0b4fc88526",
    "references/company_visual_system.md":
        "e97fa87a58255f008d666b6f9e50fdebc661752edc2110a81f9d5a7e0c37cfec",
    "references/layout_and_chart_rules.md":
        "99585552ab2b94e74debdad110030203e1224bb63d420a3792e2ebec32222b44",
    "scripts/v58_source_cache.py":
        "0f8a84230be8f01def40c373995157890cea8c7e0c2ad37dbfa79cb80e6395bf",
    "scripts/v583_source_ingest.py":
        "a15de512e51187024ce21548251caddaafe3678205192167af35b81d2ce600fa",
    "scripts/v583_authoring.py":
        "e0b3c556f8debf2d9a4111c58a0b7fdfc0813af7ff1f6137bfd911013586065d",
    "scripts/v58_visual_policy.py":
        "a58f9361f747d4a3c7262dda483e4abdf7ef61c1dbaf36908b0638f98117bab4",
    "scripts/v59_blueprint_gate.py":
        "f8a737f0051e0e011600439edb0c9577922cf9885c90ed6b55eeb9e966a58293",
    "scripts/compose_blueprint.py":
        "5b313f2ed90b2c08aae212f4ecbcadc2468d04a21afa4ee786acf73b7ef03d65",
}


class V596BoundaryTests(unittest.TestCase):
    def test_pre_blueprint_files_remain_byte_identical_to_v595(self):
        actual = {
            relative: frozen_sha256(SKILL / relative)
            for relative in FROZEN_SHA256
        }
        self.assertEqual(FROZEN_SHA256, actual)

    def test_documentation_declares_post_blueprint_only_upgrade(self):
        skill = (SKILL / "SKILL.md").read_text(encoding="utf-8")
        normalized = " ".join(skill.lower().split())
        self.assertIn("standard report ppt v5.9.6", normalized)
        self.assertIn('"pipeline_revision": "5.9.6"', normalized)
        self.assertIn("visual_review_tiles.json", normalized)
        self.assertIn("formal blueprint locking remain unchanged", normalized)


if __name__ == "__main__":
    unittest.main()
