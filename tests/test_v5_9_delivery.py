from __future__ import annotations

import importlib.util
import json
import tempfile
import unittest
from pathlib import Path


SKILL = Path(__file__).resolve().parents[1]


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class V59DeliveryTests(unittest.TestCase):
    def test_unrendered_mac_project_cannot_create_formal_zip(self):
        pack = load_module("v59_pack", SKILL / "scripts" / "pack_delivery.py")
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / ".build").mkdir()
            (root / "project_brief.json").write_text(
                json.dumps({
                    "schema_version": "5.9",
                    "pipeline_revision": "5.9.0",
                    "requested_page_count": 1,
                    "production_mode": "fast",
                }),
                encoding="utf-8",
            )
            (root / ".build" / "runtime_report.json").write_text(
                json.dumps({"builder_backend": "mac_python_pptx_v1"}),
                encoding="utf-8",
            )
            (root / ".build" / "mac_quality_report.json").write_text(
                json.dumps({
                    "status": "structurally_valid_unrendered",
                    "visual_verification": False,
                }),
                encoding="utf-8",
            )
            (root / "output").mkdir()
            pptx = root / "output" / "report.pptx"
            pptx.write_bytes(b"fixture")
            with self.assertRaisesRegex(ValueError, "visual verification"):
                pack.validate_v59_delivery_status(root)
            loose = pack.write_v59_loose_delivery(root, pptx)
            self.assertEqual("structurally_valid_unrendered", loose["status"])
            self.assertTrue((root / "output" / "quality_report.json").is_file())

    def test_verified_status_is_allowed(self):
        pack = load_module(
            "v59_pack_verified", SKILL / "scripts" / "pack_delivery.py"
        )
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / ".build").mkdir()
            (root / ".build" / "runtime_report.json").write_text(
                json.dumps({"builder_backend": "mac_python_pptx_v1"}),
                encoding="utf-8",
            )
            (root / ".build" / "mac_quality_report.json").write_text(
                json.dumps({
                    "status": "pass_with_warnings",
                    "visual_verification": True,
                }),
                encoding="utf-8",
            )
            result = pack.validate_v59_delivery_status(root)
            self.assertTrue(result["visual_verification"])

    def test_mac_delivery_merges_shared_warnings(self):
        pack = load_module(
            "v592_pack_shared_warnings",
            SKILL / "scripts" / "pack_delivery.py",
        )
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            build = root / ".build"
            build.mkdir()
            (build / "runtime_report.json").write_text(
                json.dumps({"builder_backend": "mac_python_pptx_v1"}),
                encoding="utf-8",
            )
            (build / "mac_quality_report.json").write_text(
                json.dumps(
                    {
                        "status": "pass",
                        "visual_verification": True,
                        "warnings": [],
                        "errors": [],
                    }
                ),
                encoding="utf-8",
            )
            (build / "quality_report.json").write_text(
                json.dumps(
                    {
                        "status": "pass_with_warnings",
                        "warnings": [
                            {
                                "code": "SEMANTIC_VISUAL_OMITTED",
                                "message": "semantic visual omitted",
                            }
                        ],
                        "blockers": [],
                        "warning_count": 1,
                        "blocker_count": 0,
                    }
                ),
                encoding="utf-8",
            )

            result = pack.validate_v59_delivery_status(root)

            self.assertEqual("pass_with_warnings", result["status"])
            self.assertEqual(1, result["warning_count"])

    def test_mac_delivery_rejects_shared_blocker(self):
        pack = load_module(
            "v592_pack_shared_blocker",
            SKILL / "scripts" / "pack_delivery.py",
        )
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            build = root / ".build"
            build.mkdir()
            (build / "runtime_report.json").write_text(
                json.dumps({"builder_backend": "mac_python_pptx_v1"}),
                encoding="utf-8",
            )
            (build / "mac_quality_report.json").write_text(
                json.dumps(
                    {
                        "status": "pass",
                        "visual_verification": True,
                        "warnings": [],
                        "errors": [],
                    }
                ),
                encoding="utf-8",
            )
            (build / "quality_report.json").write_text(
                json.dumps(
                    {
                        "status": "blocked",
                        "warnings": [],
                        "blockers": [
                            {
                                "code": "RECONSTRUCTION_MODULE_UNBOUND",
                                "message": "module is unbound",
                            }
                        ],
                        "warning_count": 0,
                        "blocker_count": 1,
                    }
                ),
                encoding="utf-8",
            )

            with self.assertRaisesRegex(ValueError, "shared quality"):
                pack.validate_v59_delivery_status(root)

    def test_v591_contract_hashes_reject_post_compile_manifest_edit(self):
        pack = load_module(
            "v591_pack_hashes",
            SKILL / "scripts" / "pack_delivery.py",
        )
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            build = root / ".build"
            build.mkdir()
            for name in (
                "authoring_bundle.json",
                "blueprint_alignment.json",
                "slides.json",
                "page_specs.json",
                "visual_manifest.json",
            ):
                (build / name).write_text(
                    json.dumps({"name": name}),
                    encoding="utf-8",
                )
            contracts = load_module(
                "v591_hash_contracts",
                SKILL / "scripts" / "v591_contracts.py",
            )
            expected = contracts.contract_hashes(root)
            (build / "visual_manifest.json").write_text(
                json.dumps({"name": "visual_manifest.json", "changed": True}),
                encoding="utf-8",
            )
            errors = pack.validate_contract_hashes(root, expected)
        self.assertTrue(
            any("visual_manifest hash mismatch" in error for error in errors),
            errors,
        )


if __name__ == "__main__":
    unittest.main()
