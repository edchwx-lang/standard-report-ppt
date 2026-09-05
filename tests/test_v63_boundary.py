from __future__ import annotations

import importlib.util
import json
import unittest
from pathlib import Path

from tests.boundary_hash import frozen_sha256


ROOT = Path(__file__).resolve().parents[1]


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class V63BoundaryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.manifest = json.loads(
            (ROOT / "tests" / "fixtures" / "v63_boundary_manifest.json").read_text(
                encoding="utf-8"
            )
        )

    def test_v622_pre_blueprint_and_bitmap_assets_remain_frozen(self):
        expected = {
            **self.manifest["pre_blueprint"],
            **self.manifest["bitmap_only"],
        }
        actual = {relative: frozen_sha256(ROOT / relative) for relative in expected}
        self.assertEqual(expected, actual)

    def test_v63_cache_requires_locked_blueprints_and_deconstruction(self):
        contracts = load_module(
            "v63_boundary_contracts", ROOT / "scripts" / "v6_contracts.py"
        )
        base = {
            "schema_version": "6.0",
            "pipeline_revision": "6.0.0",
            "requested_page_count": 1,
            "production_mode": "blueprint",
            "blueprint_engine": "builtin_imagegen",
            "platform_target": "auto",
            "source_files": ["C:/fixture/source.docx"],
        }
        deconstruct = dict(base, construction_mode="deconstruct")
        bitmap = dict(base, construction_mode="bitmap")
        hashes = {"S01": "a" * 64}

        upstream_before = contracts.upstream_cache_payload(deconstruct)
        payload = contracts.v63_post_lock_cache_payload(
            deconstruct, "windows_com_v584", hashes
        )

        self.assertEqual("6.3.1", payload["deconstruction_runtime_revision"])
        self.assertEqual(hashes, payload["formal_blueprint_hashes"])
        self.assertEqual(upstream_before, contracts.upstream_cache_payload(deconstruct))
        self.assertNotIn(
            "deconstruction_runtime_revision",
            contracts.post_lock_cache_payload(bitmap, "windows_com_v584"),
        )
        with self.assertRaisesRegex(ValueError, "V63_BLUEPRINT_LOCK_REQUIRED"):
            contracts.v63_post_lock_cache_payload(
                deconstruct, "windows_com_v584", {}
            )
        with self.assertRaisesRegex(ValueError, "V63_DECONSTRUCTION_ONLY"):
            contracts.v63_post_lock_cache_payload(
                bitmap, "windows_com_v584", hashes
            )


if __name__ == "__main__":
    unittest.main()
