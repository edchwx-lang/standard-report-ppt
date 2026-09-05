from __future__ import annotations

import hashlib
import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from PIL import Image, ImageDraw


ROOT = Path(__file__).resolve().parents[1]
TEMPLATE = ROOT / "assets" / "company_template.pptx"


def load(name: str):
    path = ROOT / "scripts" / f"{name}.py"
    spec = importlib.util.spec_from_file_location(f"{name}_integration_test", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def write_project(project: Path) -> None:
    (project / "blueprints").mkdir()
    (project / ".build").mkdir()
    image = Image.new("RGB", (1200, 675), "white")
    ImageDraw.Draw(image).rectangle((100, 180, 1100, 560), fill="#244A82")
    blueprint = project / "blueprints" / "S01.png"
    image.save(blueprint)
    digest = hashlib.sha256(blueprint.read_bytes()).hexdigest()
    (project / ".build" / "design_drafts").mkdir()
    (project / ".build" / "design_drafts" / "S01.png").write_bytes(blueprint.read_bytes())
    brief = {
        "schema_version": "6.0",
        "pipeline_revision": "6.0.0",
        "requested_page_count": 1,
        "production_mode": "blueprint",
        "construction_mode": "deconstruct",
        "blueprint_engine": "builtin_imagegen",
        "platform_target": "auto",
        "source_files": ["C:/fixture/source.docx"],
    }
    (project / "project_brief.json").write_text(json.dumps(brief), encoding="utf-8")
    (project / ".build" / "visual_manifest.json").write_text(
        json.dumps({"schema_version": "6.0", "pipeline_revision": "6.0.0", "construction_mode": "deconstruct", "pages": {"S01": {"design_draft_sha256": digest, "formal_blueprint_sha256": digest, "formal_blueprint_path": "blueprints/S01.png"}}}),
        encoding="utf-8",
    )
    (project / ".build" / "runtime_report.json").write_text(
        json.dumps({"builder_backend": "windows_com_v584"}), encoding="utf-8"
    )
    (project / ".build" / "slides.json").write_text(
        json.dumps([{"slide_id": "S01", "chapter": "一、章节", "title": "页标题", "core_points": ["核心判断"], "source": "资料来源：测试"}], ensure_ascii=False),
        encoding="utf-8",
    )
    (project / ".build" / "formal_blueprint_manifest.json").write_text(
        json.dumps({"schema_version": "6.0", "pipeline_revision": "6.0.0", "construction_mode": "deconstruct", "pages": {"S01": {"design_draft_path": ".build/design_drafts/S01.png", "design_draft_sha256": digest, "formal_blueprint_path": "blueprints/S01.png", "formal_blueprint_sha256": digest}}}),
        encoding="utf-8",
    )
    tiles = load("v63_visual_tiles").generate_review_tiles(project, template_path=TEMPLATE, legacy_template_roi=True)
    tile_page = tiles["pages"]["S01"]
    census = {
        "schema_version": "6.3",
        "deconstruction_runtime_revision": "6.3.1",
        "pages": {"S01": {"blueprint_sha256": digest, "body_roi_px": tile_page["body_roi_px"], "reviewed_tile_ids": [item["tile_id"] for item in tile_page["tiles"]], "candidates": [{"candidate_id": "C1", "kind": "panel", "bbox_px": [100, 180, 1100, 560], "review_tile_ids": ["FULL", "B01", "B02", "B03", "B04", "B05", "B06"], "expected_treatment": "editable", "confidence": "high"}]}}
    }
    load("v63_visual_census").validate_and_write_visual_census(project, census)
    scene = {
        "schema_version": "6.3",
        "deconstruction_runtime_revision": "6.3.1",
        "color_authority": "blueprint_body",
        "pages": {"S01": {"blueprint_sha256": digest, "body_roi_px": tile_page["body_roi_px"], "elements": [{"element_id": "E1", "type": "rect", "bbox_px": [100, 180, 1100, 560], "z_order": 1, "style": {"fill": "#244A82", "line": "none"}, "source_candidate_ids": ["C1"]}], "candidate_resolutions": {"C1": {"mode": "editable", "element_ids": ["E1"]}}}}
    }
    (project / ".build" / "v63_scene_graph.json").write_text(json.dumps(scene), encoding="utf-8")


class V63DeconstructionTests(unittest.TestCase):
    def test_prebuild_aggregates_post_lock_contracts_and_assets_once(self):
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory)
            write_project(project)
            report = load("v63_deconstruction").prepare_deconstruction(
                project, backend="windows_com_v584", template_path=TEMPLATE
            )
            precheck_exists = (project / ".build" / "v63_deconstruction_precheck.json").is_file()
            ledger_exists = (project / ".build" / "v63_asset_ledger.json").is_file()

        self.assertTrue(report["ok"], report["blockers"])
        self.assertEqual("6.3.1", report["cache_payload"]["deconstruction_runtime_revision"])
        self.assertTrue(precheck_exists)
        self.assertTrue(ledger_exists)

    def test_prebuild_reports_scene_omission_as_one_aggregated_blocker_set(self):
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory)
            write_project(project)
            path = project / ".build" / "v63_scene_graph.json"
            scene = json.loads(path.read_text(encoding="utf-8"))
            scene["pages"]["S01"]["candidate_resolutions"] = {}
            path.write_text(json.dumps(scene), encoding="utf-8")

            report = load("v63_deconstruction").prepare_deconstruction(
                project, backend="windows_com_v584", template_path=TEMPLATE
            )

        self.assertFalse(report["ok"])
        self.assertIn("V63_SCENE_CANDIDATE_UNRESOLVED", {item["code"] for item in report["blockers"]})

    def test_pipeline_prebuild_uses_scene_contract_without_legacy_alignment(self):
        pipeline = load("project_pipeline")
        original_loader = pipeline._load_module

        def loader(name, path):
            if Path(path).name == "v6_blueprint_gate.py":
                return SimpleNamespace(assert_blueprint_gate=lambda *args, **kwargs: {"ok": True})
            return original_loader(name, path)

        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory)
            write_project(project)
            with patch.object(pipeline, "_load_module", side_effect=loader):
                report = pipeline.prebuild_project(project)

        self.assertTrue(report["ok"], report["blockers"])
        self.assertEqual("6.3.1", report["deconstruction_runtime_revision"])

    def test_prepare_visual_review_also_materializes_v63_overlapping_tiles(self):
        pipeline = load("project_pipeline")
        original_loader = pipeline._load_module

        def loader(name, path):
            if Path(path).name == "v6_blueprint_gate.py":
                return SimpleNamespace(assert_imagegen_invocation_gate=lambda *args, **kwargs: {"ok": True})
            return original_loader(name, path)

        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory)
            write_project(project)
            (project / ".build" / "v63_visual_review_tiles.json").unlink()
            digest = hashlib.sha256((project / 'blueprints/S01.png').read_bytes()).hexdigest()
            (project / '.build/v63_source_body_rois.json').write_text(json.dumps({'pages': {'S01': {
                'blueprint_sha256': digest, 'source_body_roi_px': [60,150,1080,450]}}}), encoding='utf-8')
            with patch.object(pipeline, "_load_module", side_effect=loader):
                pipeline.prepare_visual_review(project)
            generated = (project / ".build" / "v63_visual_review_tiles.json").is_file()

        self.assertTrue(generated)

    @unittest.skipUnless(sys.platform == "win32", "requires Windows PowerPoint COM")
    def test_windows_compiler_emits_and_runs_v63_scene_generator(self):
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory)
            write_project(project)
            precheck = load("v63_deconstruction").prepare_deconstruction(
                project, backend="windows_com_v584", template_path=TEMPLATE
            )
            self.assertTrue(precheck["ok"], precheck["blockers"])
            generator = load("project_compiler").compile_project(project)
            source = generator.read_text(encoding="utf-8")
            output = project / "output" / "compiled.pptx"
            result = subprocess.run(
                [sys.executable, str(generator), "--output", str(output)],
                check=False,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=180,
            )
            output_exists = output.is_file()

        self.assertIn("6.3.1", source)
        self.assertIn("v63_windows_scene_renderer.py", source)
        self.assertEqual(0, result.returncode, result.stdout + result.stderr)
        self.assertTrue(output_exists)

    @unittest.skipUnless(sys.platform == "win32", "requires Windows PowerPoint COM")
    def test_full_windows_pipeline_uses_v63_acceptance_and_runtime_revision(self):
        pipeline = load("project_pipeline")
        original_loader = pipeline._load_module

        def loader(name, path):
            if Path(path).name == "v6_blueprint_gate.py":
                return SimpleNamespace(
                    assert_blueprint_gate=lambda *args, **kwargs: {"ok": True},
                    assert_imagegen_invocation_gate=lambda *args, **kwargs: {"ok": True},
                )
            return original_loader(name, path)

        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory)
            write_project(project)
            brief = json.loads((project / "project_brief.json").read_text(encoding="utf-8"))
            output = project / "output" / "pipeline-v63.pptx"
            with patch.object(pipeline, "_load_module", side_effect=loader):
                result = pipeline._run_v6_project(
                    project,
                    brief,
                    output,
                    catastrophic_repair=False,
                    user_revision=False,
                    auto_package=False,
                )
            acceptance = json.loads(
                (project / ".build" / "deconstruction_acceptance.json").read_text(
                    encoding="utf-8"
                )
            )
            cache = json.loads(
                (project / ".build" / "v6_cache_fingerprint.json").read_text(
                    encoding="utf-8"
                )
            )

        self.assertTrue(result["ok"])
        self.assertEqual("6.3.1", result["skill_version"])
        self.assertTrue(acceptance["accepted"], acceptance["blockers"])
        self.assertEqual("6.3.1", cache["deconstruction_runtime_revision"])


if __name__ == "__main__":
    unittest.main()
