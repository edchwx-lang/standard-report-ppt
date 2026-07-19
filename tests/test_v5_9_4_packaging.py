from __future__ import annotations

import hashlib
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path
from zipfile import ZipFile


SKILL = Path(__file__).resolve().parents[1]


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class FakeContracts:
    def diagnose_visual_manifest(self, manifest):
        if manifest["pages"]["S01"].get("design_draft_sha256") == "a" * 64:
            return {"blockers": [], "warnings": []}
        return {
            "blockers": [{"message": "modern manifest rejected"}],
            "warnings": [],
        }

    def validate_visual_manifest(self, manifest):
        return ["legacy validator requires blueprint_sha256"]


class V594PackagingTests(unittest.TestCase):
    def setUp(self):
        self.pack = load_module(
            "v594_packaging",
            SKILL / "scripts" / "pack_delivery.py",
        )
        self.v594 = {
            "schema_version": "5.9",
            "pipeline_revision": "5.9.4",
            "production_mode": "blueprint",
        }

    def test_v594_uses_modern_visual_manifest_fields(self):
        manifest = {
            "schema_version": "5.9",
            "pages": {
                "S01": {
                    "design_draft_sha256": "a" * 64,
                    "formal_blueprint_sha256": "a" * 64,
                }
            },
        }
        self.assertEqual(
            [],
            self.pack.validate_packaging_visual_manifest(
                FakeContracts(),
                manifest,
                self.v594,
            ),
        )

    def test_v592_keeps_legacy_packaging_validation_behavior(self):
        manifest = {
            "schema_version": "5.9",
            "pages": {"S01": {"design_draft_sha256": "a" * 64}},
        }
        errors = self.pack.validate_packaging_visual_manifest(
            FakeContracts(),
            manifest,
            {**self.v594, "pipeline_revision": "5.9.2"},
        )
        self.assertEqual(
            ["legacy validator requires blueprint_sha256"],
            errors,
        )

    def test_v594_helper_python_files_do_not_enter_py_zip(self):
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory)
            generator = project / "generate_deck.py"
            generator.write_text("DECK_META = {}\n", encoding="utf-8")
            (project / "prepare_project.py").write_text(
                "print('prepare')\n",
                encoding="utf-8",
            )
            notes = project / "notes"
            notes.mkdir()
            (notes / "helper.py").write_text("HELPER = True\n", encoding="utf-8")

            self.assertEqual(
                [],
                self.pack.validate_project_python_policy(
                    project,
                    generator,
                    self.v594,
                ),
            )
            destination = project / "py.zip"
            self.pack._write_py_zip(generator, destination)
            with ZipFile(destination) as archive:
                self.assertEqual(["generate_deck.py"], archive.namelist())

    def test_v592_still_rejects_helper_python_files(self):
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory)
            generator = project / "generate_deck.py"
            generator.write_text("DECK_META = {}\n", encoding="utf-8")
            (project / "helper.py").write_text("HELPER = True\n", encoding="utf-8")
            errors = self.pack.validate_project_python_policy(
                project,
                generator,
                {**self.v594, "pipeline_revision": "5.9.2"},
            )
            self.assertTrue(errors)

    def test_v594_asset_audit_must_match_current_pptx(self):
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory)
            build = project / ".build"
            build.mkdir()
            pptx = project / "report.pptx"
            pptx.write_bytes(b"current-pptx")
            report = {
                "ok": True,
                "pptx_sha256": sha256(pptx),
                "declared_assets": 1,
                "inserted_assets": 1,
                "census_crop_assets": 1,
            }
            (build / "ppt_asset_audit.json").write_text(
                json.dumps(report),
                encoding="utf-8",
            )
            self.assertEqual(
                [],
                self.pack.validate_v594_asset_audit(
                    project,
                    pptx,
                    self.v594,
                ),
            )
            report["pptx_sha256"] = "0" * 64
            (build / "ppt_asset_audit.json").write_text(
                json.dumps(report),
                encoding="utf-8",
            )
            self.assertIn(
                "PPTX SHA-256 mismatch",
                " ".join(
                    self.pack.validate_v594_asset_audit(
                        project,
                        pptx,
                        self.v594,
                    )
                ),
            )

    def test_v594_zero_crop_audit_is_valid(self):
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory)
            build = project / ".build"
            build.mkdir()
            pptx = project / "report.pptx"
            pptx.write_bytes(b"zero-crop-pptx")
            (build / "ppt_asset_audit.json").write_text(
                json.dumps(
                    {
                        "ok": True,
                        "pptx_sha256": sha256(pptx),
                        "declared_assets": 0,
                        "inserted_assets": 0,
                        "census_crop_assets": 0,
                    }
                ),
                encoding="utf-8",
            )
            self.assertEqual(
                [],
                self.pack.validate_v594_asset_audit(
                    project,
                    pptx,
                    self.v594,
                ),
            )


if __name__ == "__main__":
    unittest.main()
