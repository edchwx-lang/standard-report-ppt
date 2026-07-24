from __future__ import annotations

import importlib.util
import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from zipfile import ZipFile

from PIL import Image


ROOT = Path(__file__).resolve().parents[1]


def load():
    spec = importlib.util.spec_from_file_location(
        "v6_delivery_tests", ROOT / "scripts" / "pack_delivery.py"
    )
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


PACK = load()


class V6DeliveryTests(unittest.TestCase):
    def make_project(self, project: Path, mode: str) -> tuple[Path, Path]:
        (project / ".build").mkdir()
        (project / ".build" / "design_drafts").mkdir()
        (project / "blueprints").mkdir()
        blueprint = project / "blueprints" / "S01.png"
        image = Image.new("RGB", (100, 100), "white")
        for x in range(50, 100):
            for y in range(100):
                image.putpixel((x, y), (0, 0, 255))
        image.save(blueprint)
        draft = project / ".build" / "design_drafts" / "S01.png"
        draft.write_bytes(blueprint.read_bytes())
        digest = hashlib.sha256(blueprint.read_bytes()).hexdigest()
        brief = {
            "schema_version": "6.0",
            "pipeline_revision": "6.0.0",
            "requested_page_count": 1,
            "production_mode": "blueprint",
            "construction_mode": mode,
            "blueprint_engine": "builtin_imagegen",
            "platform_target": "auto",
            "source_files": ["C:/source.docx"],
        }
        (project / "project_brief.json").write_text(json.dumps(brief), encoding="utf-8")
        (project / ".build" / "runtime_report.json").write_text(
            json.dumps({
                "schema_version": "6.0",
                "pipeline_revision": "6.0.0",
                "construction_mode": mode,
                "builder_backend": "windows_com_v584",
            }),
            encoding="utf-8",
        )
        audit_name = (
            "deconstruction_editability_audit.json"
            if mode == "deconstruct"
            else "bitmap_pptx_audit.json"
        )
        (project / ".build" / audit_name).write_text(
            json.dumps({"ok": True, "status": "pass"}), encoding="utf-8"
        )
        if mode == "deconstruct":
            (project / ".build" / "deconstruction_precheck.json").write_text(
                json.dumps({"ok": True, "status": "pass"}), encoding="utf-8"
            )
        (project / ".build" / "pipeline_result.json").write_text(
            json.dumps({
                "schema_version": "6.0",
                "pipeline_revision": "6.0.0",
                "construction_mode": mode,
                "builder_backend": "windows_com_v584",
                "ok": True,
            }),
            encoding="utf-8",
        )
        (project / ".build" / "formal_blueprint_manifest.json").write_text(
            json.dumps({
                "schema_version": "6.0",
                "pipeline_revision": "6.0.0",
                "construction_mode": mode,
                "pages": {
                    "S01": {
                        "formal_blueprint_path": "blueprints/S01.png",
                        "formal_blueprint_sha256": digest,
                        "design_draft_path": ".build/design_drafts/S01.png",
                        "design_draft_sha256": digest,
                    }
                },
            }),
            encoding="utf-8",
        )
        (project / ".build" / "visual_manifest.json").write_text(
            json.dumps(
                {
                    "schema_version": "6.0",
                    "pipeline_revision": "6.0.0",
                    "construction_mode": mode,
                    "pages": {
                        "S01": {
                            "design_draft_path": ".build/design_drafts/S01.png",
                            "design_draft_sha256": digest,
                            "formal_blueprint_path": "blueprints/S01.png",
                            "formal_blueprint_sha256": digest,
                            "visuals": [],
                        }
                    },
                }
            ),
            encoding="utf-8",
        )
        if mode == "bitmap":
            body = project / ".build" / "assets" / "S01" / "S01_BODY_BITMAP.png"
            body.parent.mkdir(parents=True)
            with Image.open(blueprint) as source:
                source.crop((0, 0, 50, 100)).save(body)
            (project / ".build" / "bitmap_contract.json").write_text(
                json.dumps({
                    "schema_version": "6.0",
                    "pipeline_revision": "6.0.0",
                    "construction_mode": "bitmap",
                    "pages": {
                        "S01": {
                            "asset_id": "S01_BODY_BITMAP",
                            "source_blueprint": "blueprints/S01.png",
                            "source_blueprint_sha256": digest,
                            "source_px": [0, 0, 50, 100],
                            "asset_path": ".build/assets/S01/S01_BODY_BITMAP.png",
                            "asset_sha256": hashlib.sha256(body.read_bytes()).hexdigest(),
                            "fit": "contain",
                            "target": "runtime_body_box",
                        }
                    },
                }),
                encoding="utf-8",
            )
            (project / ".build" / "bitmap_page_specs.json").write_text(
                json.dumps(
                    {
                        "S01": {
                            "elements": [
                                {
                                    "type": "body_asset",
                                    "element_id": "S01_BODY_BITMAP",
                                    "asset_id": "S01_BODY_BITMAP",
                                    "asset_path": ".build/assets/S01/S01_BODY_BITMAP.png",
                                    "fit": "contain",
                                    "target": "runtime_body_box",
                                }
                            ]
                        }
                    }
                ),
                encoding="utf-8",
            )
        else:
            (project / ".build" / "page_specs.json").write_text(
                json.dumps(
                    {
                        "S01": {
                            "elements": [
                                {
                                    "type": "text",
                                    "element_id": "BODY_TEXT",
                                    "box": [0, 0, 2, 1],
                                    "text": "body",
                                }
                            ]
                        }
                    }
                ),
                encoding="utf-8",
            )
        pptx = project / "report.pptx"
        generator = project / "generate_deck.py"
        pptx.write_bytes(b"pptx")
        generator.write_text("print('ok')\n", encoding="utf-8")
        (project / ".build" / audit_name).write_text(
            json.dumps({
                "ok": True,
                "status": "pass",
                "construction_mode": mode,
                "builder_backend": "windows_com_v584",
                "pptx_sha256": hashlib.sha256(pptx.read_bytes()).hexdigest(),
            }),
            encoding="utf-8",
        )
        return pptx, generator

    def test_outer_bundle_has_exactly_three_entries(self):
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory)
            pptx, generator = self.make_project(project, "deconstruct")
            output = project / "delivery.zip"
            PACK.package_v6_delivery(project, pptx, generator, output)
            with ZipFile(output) as archive:
                self.assertEqual(
                    sorted([pptx.name, "blueprints.zip", "py.zip"]),
                    sorted(archive.namelist()),
                )
                nested_py = project / "py.zip"
                nested_py.write_bytes(archive.read("py.zip"))
            with ZipFile(nested_py) as py_archive:
                self.assertEqual(["generate_deck.py"], py_archive.namelist())

    def test_bitmap_blueprints_zip_contains_body_and_contract(self):
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory)
            pptx, generator = self.make_project(project, "bitmap")
            output = project / "delivery.zip"
            PACK.package_v6_delivery(project, pptx, generator, output)
            with ZipFile(output) as outer:
                nested = project / "blueprints.zip"
                nested.write_bytes(outer.read("blueprints.zip"))
            with ZipFile(nested) as archive:
                names = archive.namelist()
                self.assertIn("blueprints/S01.png", names)
                self.assertIn("bitmap_contract.json", names)
                self.assertIn("body/S01_BODY_BITMAP.png", names)

    def test_explicit_output_wins(self):
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory)
            pptx, generator = self.make_project(project, "bitmap")
            explicit = project / "chosen.zip"
            self.assertEqual(
                explicit,
                PACK.package_v6_delivery(project, pptx, generator, explicit),
            )

    def test_delivery_rejects_tampered_design_draft(self):
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory)
            pptx, generator = self.make_project(project, "deconstruct")
            (project / ".build" / "design_drafts" / "S01.png").write_bytes(
                b"tampered"
            )
            with self.assertRaisesRegex(ValueError, "provenance"):
                PACK.package_v6_delivery(
                    project, pptx, generator, project / "delivery.zip"
                )

    def test_delivery_rejects_wrong_bitmap_crop_with_updated_hash(self):
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory)
            pptx, generator = self.make_project(project, "bitmap")
            asset = (
                project
                / ".build"
                / "assets"
                / "S01"
                / "S01_BODY_BITMAP.png"
            )
            Image.new("RGB", (50, 100), "red").save(asset)
            contract_path = project / ".build" / "bitmap_contract.json"
            contract = json.loads(contract_path.read_text(encoding="utf-8"))
            contract["pages"]["S01"]["asset_sha256"] = hashlib.sha256(
                asset.read_bytes()
            ).hexdigest()
            contract_path.write_text(json.dumps(contract), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "derivation"):
                PACK.package_v6_delivery(
                    project, pptx, generator, project / "delivery.zip"
                )


if __name__ == "__main__":
    unittest.main()
