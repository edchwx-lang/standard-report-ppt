from __future__ import annotations

import hashlib
import importlib.util
import unittest
from pathlib import Path


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
V6_UPSTREAM_SKILL_SECTION_SHA256 = (
    "b61f12710aeff96a51bbcda1eb5e65ced90b9f72c973b39d69f968081c369507"
)
SKILL_SECTION_START = "## Standard Report PPT V5.9.2 lightweight alignment patch"
SKILL_SECTION_END = "without replacing or repainting the formal blueprint."


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class V594BoundaryTests(unittest.TestCase):
    def test_pre_blueprint_files_are_byte_identical_to_v592(self):
        actual = {
            relative: sha256_bytes((SKILL / relative).read_bytes())
            for relative in FROZEN_SHA256
        }
        self.assertEqual(FROZEN_SHA256, actual)

    def test_skill_requirements_through_blueprint_lock_match_v6_gate_boundary(self):
        text = (SKILL / "SKILL.md").read_text(encoding="utf-8")
        start = text.index(SKILL_SECTION_START)
        end = text.index(SKILL_SECTION_END, start) + len(SKILL_SECTION_END)
        self.assertEqual(
            V6_UPSTREAM_SKILL_SECTION_SHA256,
            sha256_bytes(text[start:end].encode("utf-8")),
        )

    def test_imagegen_prompt_keeps_visual_freedom(self):
        prompt = (
            SKILL / "prompts" / "imagegen_blueprint_prompt.md"
        ).read_text(encoding="utf-8")
        normalized = " ".join(prompt.lower().split())
        self.assertIn(
            "icons, people, devices, products, maps, illustrations",
            normalized,
        )
        self.assertNotIn("expected_treatment", normalized)
        self.assertNotIn("no independent icon", normalized)
        self.assertNotIn("no stock photo", normalized)

    def test_v594_uses_existing_modern_local_backend_contract(self):
        pipeline = load_module(
            "v594_boundary_pipeline",
            SKILL / "scripts" / "project_pipeline.py",
        )
        contracts = load_module(
            "v594_boundary_contracts",
            SKILL / "scripts" / "v591_contracts.py",
        )
        brief = {
            "schema_version": "5.9",
            "pipeline_revision": "5.9.4",
            "requested_page_count": 1,
            "production_mode": "blueprint",
            "blueprint_engine": "builtin_imagegen",
            "platform_target": "auto",
            "source_files": ["C:/fixture/source.docx"],
        }
        self.assertEqual([], pipeline.validate_brief(brief))
        self.assertTrue(contracts.is_v594(brief))
        self.assertTrue(contracts.uses_modern_blueprint_contract(brief))
        self.assertEqual(
            "blocker",
            contracts.audit_policy(brief, "reconstruction_contract"),
        )


if __name__ == "__main__":
    unittest.main()
