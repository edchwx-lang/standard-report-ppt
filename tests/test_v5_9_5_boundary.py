from __future__ import annotations

import hashlib
import importlib.util
import unittest
from pathlib import Path


SKILL = Path(__file__).resolve().parents[1]


def portable_text_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes().replace(b"\r\n", b"\n")).hexdigest()


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


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class V595BoundaryTests(unittest.TestCase):
    def test_pre_blueprint_files_remain_byte_identical_to_v594(self):
        actual = {
            relative: portable_text_sha256(SKILL / relative)
            for relative in FROZEN_SHA256
        }
        self.assertEqual(FROZEN_SHA256, actual)

    def test_pipeline_accepts_v595_without_changing_the_shared_schema(self):
        pipeline = load_module(
            "v595_boundary_pipeline",
            SKILL / "scripts" / "project_pipeline.py",
        )
        brief = {
            "schema_version": "5.9",
            "pipeline_revision": "5.9.5",
            "requested_page_count": 1,
            "production_mode": "blueprint",
            "blueprint_engine": "builtin_imagegen",
            "platform_target": "auto",
            "source_files": ["C:/fixture/source.docx"],
        }
        self.assertEqual([], pipeline.validate_brief(brief))

    def test_v595_contract_policy_exists(self):
        contracts = load_module(
            "v595_boundary_contracts",
            SKILL / "scripts" / "v591_contracts.py",
        )
        brief = {
            "schema_version": "5.9",
            "pipeline_revision": "5.9.5",
            "production_mode": "blueprint",
        }
        self.assertTrue(getattr(contracts, "is_v595", lambda _: False)(brief))
        self.assertEqual(
            "blocker",
            contracts.audit_policy(brief, "reconstruction_contract"),
        )
        self.assertEqual(
            "warning",
            contracts.audit_policy(brief, "blueprint_fidelity"),
        )

    def test_documentation_declares_first_build_release_contract(self):
        skill = (SKILL / "SKILL.md").read_text(encoding="utf-8")
        normalized = " ".join(skill.lower().split())
        self.assertIn("standard report ppt v5.9.5", normalized)
        self.assertIn('"pipeline_revision": "5.9.5"', normalized)
        self.assertIn("postbuild_release.json", normalized)
        self.assertIn("ordinary warnings never authorize a rebuild", normalized)


if __name__ == "__main__":
    unittest.main()
