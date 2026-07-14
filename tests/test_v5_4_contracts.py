from __future__ import annotations

import hashlib
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from zipfile import ZIP_DEFLATED, ZipFile


SKILL = Path(__file__).resolve().parents[1]


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def valid_brief(page_count: int = 1) -> dict:
    return {
        "schema_version": "5.5",
        "requested_page_count": page_count,
        "page_mapping": [],
        "production_mode": "blueprint",
        "blueprint_engine": "direct",
        "confirmation_source": "user_explicit",
    }


class V54BootstrapTests(unittest.TestCase):
    def test_generator_template_contains_materialization_tokens(self):
        source = (SKILL / "assets" / "direct_blueprint_generator_template.py").read_text(encoding="utf-8")
        self.assertIn("__COMPANY_TEMPLATE_PATH__", source)
        self.assertIn("__COMPANY_TEMPLATE_SHA256__", source)
        self.assertNotIn("1ddc5ce1251c64a4b1ae8b8bfa0fc5ba62d44d19b1c2bd793796a5c310cafa19", source)

    def test_bootstrap_injects_live_template_hash(self):
        direct = load_module("direct_project_v54_hash", SKILL / "scripts" / "direct_project.py")
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory) / "project"
            project.mkdir()
            (project / "project_brief.json").write_text(json.dumps(valid_brief()), encoding="utf-8")
            template = Path(directory) / "master.pptx"
            template.write_bytes(b"current company master")
            generator = direct.bootstrap_direct_project(
                project,
                template_path=template,
                generator_template=SKILL / "assets" / "direct_blueprint_generator_template.py",
            )
            source = generator.read_text(encoding="utf-8")
            self.assertIn(template.resolve().as_posix(), source.replace("\\", "/"))
            self.assertIn(sha256_file(template), source)
            self.assertNotIn("__COMPANY_TEMPLATE_SHA256__", source)

    def test_bootstrap_rejects_legacy_brief_fields(self):
        direct = load_module("direct_project_v54_legacy", SKILL / "scripts" / "direct_project.py")
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory)
            legacy = {"schema_version": "5.5", "page_count": 1, "mode": "blueprint"}
            (project / "project_brief.json").write_text(json.dumps(legacy), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "requested_page_count|production_mode"):
                direct.bootstrap_direct_project(project)

    def test_bootstrap_creates_standard_directories_and_state(self):
        direct = load_module("direct_project_v54_dirs", SKILL / "scripts" / "direct_project.py")
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory) / "project"
            project.mkdir()
            (project / "project_brief.json").write_text(json.dumps(valid_brief()), encoding="utf-8")
            template = Path(directory) / "master.pptx"
            template.write_bytes(b"master")
            direct.bootstrap_direct_project(
                project,
                template_path=template,
                generator_template=SKILL / "assets" / "direct_blueprint_generator_template.py",
            )
            for relative in ("blueprints", ".build", ".build/rendered/current", "output"):
                self.assertTrue((project / relative).is_dir(), relative)
            state = json.loads((project / "direct_blueprint_state.json").read_text(encoding="utf-8"))
            self.assertEqual(state["page_count"], 1)

    def test_incremental_rollback_preserves_composition_evidence(self):
        direct = load_module("direct_project_v54_rollback", SKILL / "scripts" / "direct_project.py")
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory)
            state = {
                "schema_version": "5.5",
                "pages": [{
                    "slide_id": "S01",
                    "status": "assets_extracted",
                    "blueprint_path": "blueprints/S01.png",
                    "blueprint_sha256": "a" * 64,
                    "composition_sha256": "b" * 64,
                    "builder_name": "build_slide_S01",
                    "builder_sha256": "c" * 64,
                    "asset_count": 0,
                }],
            }
            (project / "direct_blueprint_state.json").write_text(json.dumps(state), encoding="utf-8")
            page = direct.invalidate_page_from(project, "S01", "builder_written")
            self.assertEqual(page["status"], "blueprint_saved")
            self.assertEqual(page["composition_sha256"], "b" * 64)


class V54DeliveryTests(unittest.TestCase):
    def _minimal_pptx(self, path: Path):
        payload = (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<p:presentation xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main">'
            '<p:sldIdLst><p:sldId id="256" r:id="rId1" '
            'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"/>'
            '</p:sldIdLst></p:presentation>'
        )
        with ZipFile(path, "w", ZIP_DEFLATED) as archive:
            archive.writestr("ppt/presentation.xml", payload)

    def test_delivery_rejects_non_desktop_output(self):
        pack = load_module("pack_delivery_v54_path", SKILL / "scripts" / "pack_delivery.py")
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            project = root / "project"
            project.mkdir()
            pptx = project / "report.pptx"
            generator = project / "generate_deck.py"
            self._minimal_pptx(pptx)
            generator.write_text("# generator\n", encoding="utf-8")
            (project / "project_brief.json").write_text(json.dumps(valid_brief()), encoding="utf-8")
            (project / "blueprints").mkdir()
            (project / "blueprints" / "S01.png").write_bytes(b"png")
            with self.assertRaisesRegex(ValueError, "desktop"):
                pack.package_direct_delivery(
                    project_dir=project,
                    pptx_path=pptx,
                    generator_path=generator,
                    output_zip=project / "delivery.zip",
                    desktop_dir=root / "Desktop",
                )

    def test_packaging_writes_verified_delivery_record(self):
        pack = load_module("pack_delivery_v54_record", SKILL / "scripts" / "pack_delivery.py")
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            desktop = root / "Desktop"
            desktop.mkdir()
            project = root / "project"
            project.mkdir()
            (project / ".build").mkdir()
            pptx = project / "report.pptx"
            generator = project / "generate_deck.py"
            self._minimal_pptx(pptx)
            generator.write_text("# generator\n", encoding="utf-8")
            (project / "project_brief.json").write_text(json.dumps(valid_brief()), encoding="utf-8")
            (project / "blueprints").mkdir()
            (project / "blueprints" / "S01.png").write_bytes(b"png")
            output = desktop / "delivery.zip"
            with patch.object(pack, "_run_skeleton_audit", return_value={"ok": True}), \
                 patch.object(pack, "_run_asset_audit", return_value={"ok": True}), \
                 patch.object(pack, "_validate_direct_project", return_value=[]):
                pack.package_direct_delivery(
                    project_dir=project,
                    pptx_path=pptx,
                    generator_path=generator,
                    output_zip=output,
                    desktop_dir=desktop,
                )
            record = json.loads((project / ".build" / "delivery_record.json").read_text(encoding="utf-8"))
            self.assertEqual(record["zip_path"], str(output.resolve()))
            self.assertEqual(record["zip_sha256"], sha256_file(output))
            self.assertEqual(record["pptx_page_count"], 1)
            self.assertEqual(record["outer_entries"], ["report.pptx", "blueprints.zip", "py.zip"])
            with ZipFile(output) as archive:
                self.assertEqual(archive.namelist(), record["outer_entries"])


if __name__ == "__main__":
    unittest.main()
