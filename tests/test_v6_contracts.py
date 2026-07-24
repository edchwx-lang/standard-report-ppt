from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def brief(mode: str = "deconstruct") -> dict:
    return {
        "schema_version": "6.0",
        "pipeline_revision": "6.0.0",
        "production_mode": "blueprint",
        "construction_mode": mode,
        "blueprint_engine": "builtin_imagegen",
        "platform_target": "auto",
        "source_files": ["C:/fixtures/source.docx"],
        "visual_brief": {"primary_expression": "comparison"},
    }


class V6ContractsTests(unittest.TestCase):
    def setUp(self):
        self.contracts = load_module(
            "v6_contracts", ROOT / "scripts" / "v6_contracts.py"
        )

    def test_valid_v6_brief_is_recognized(self):
        payload = brief()
        self.assertTrue(self.contracts.is_v6(payload))
        self.assertEqual([], self.contracts.validate_v6_brief(payload))
        self.assertEqual("deconstruct", self.contracts.construction_mode(payload))

    def test_v6_requires_an_explicit_supported_construction_mode(self):
        missing = brief()
        missing.pop("construction_mode")
        fast = brief("fast")
        invalid = brief("other")
        for payload in (missing, fast, invalid):
            with self.subTest(payload=payload):
                errors = self.contracts.validate_v6_brief(payload)
                self.assertIn(
                    self.contracts.ERROR_CONSTRUCTION_MODE_REQUIRED,
                    errors,
                )
                self.assertIsNone(self.contracts.construction_mode(payload))

    def test_v6_fixed_contract_fields_are_validated(self):
        payload = brief()
        payload.update(
            {
                "schema_version": "5.9",
                "pipeline_revision": "6",
                "production_mode": "fast",
                "blueprint_engine": "direct",
                "platform_target": "windows",
            }
        )
        errors = self.contracts.validate_v6_brief(payload)
        self.assertEqual(
            {
                self.contracts.ERROR_SCHEMA_VERSION,
                self.contracts.ERROR_PIPELINE_REVISION,
                self.contracts.ERROR_PRODUCTION_MODE,
                self.contracts.ERROR_BLUEPRINT_ENGINE,
                self.contracts.ERROR_PLATFORM_TARGET,
            },
            set(errors),
        )

    def test_upstream_cache_ignores_mode_and_platform_but_post_lock_does_not(self):
        deconstruct = brief("deconstruct")
        bitmap = brief("bitmap")
        bitmap["platform_target"] = "mac"
        bitmap["backend"] = "mac_python_pptx_v1"
        self.assertEqual(
            self.contracts.upstream_cache_payload(deconstruct),
            self.contracts.upstream_cache_payload(bitmap),
        )
        self.assertNotIn(
            "construction_mode", self.contracts.upstream_cache_payload(bitmap)
        )
        self.assertNotIn(
            "platform_target", self.contracts.upstream_cache_payload(bitmap)
        )
        self.assertNotEqual(
            self.contracts.post_lock_cache_payload(
                deconstruct, "windows_com_v584"
            ),
            self.contracts.post_lock_cache_payload(
                bitmap, "mac_python_pptx_v1"
            ),
        )

    def test_runtime_page_spec_path_is_mode_specific(self):
        self.assertEqual(
            ".build/page_specs.json",
            self.contracts.runtime_page_specs_path(brief("deconstruct")),
        )
        self.assertEqual(
            ".build/bitmap_page_specs.json",
            self.contracts.runtime_page_specs_path(brief("bitmap")),
        )
        with self.assertRaises(ValueError):
            self.contracts.runtime_page_specs_path(brief("fast"))


if __name__ == "__main__":
    unittest.main()
