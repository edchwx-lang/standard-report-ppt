from __future__ import annotations

import importlib.util
import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from PIL import Image


ROOT = Path(__file__).resolve().parents[1]


def load():
    spec = importlib.util.spec_from_file_location(
        "v6_windows_compile_tests", ROOT / "scripts" / "project_compiler.py"
    )
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


COMPILER = load()


def project_files(project: Path, mode: str, elements: list[dict]) -> None:
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
    (project / ".build").mkdir()
    (project / ".build" / "design_drafts").mkdir()
    (project / "blueprints").mkdir()
    Image.new("RGB", (1600, 900), "white").save(project / "blueprints" / "S01.png")
    (project / ".build" / "design_drafts" / "S01.png").write_bytes(
        (project / "blueprints" / "S01.png").read_bytes()
    )
    digest = hashlib.sha256((project / "blueprints" / "S01.png").read_bytes()).hexdigest()
    (project / "project_brief.json").write_text(json.dumps(brief), encoding="utf-8")
    slides = [{
        "slide_id": "S01",
        "chapter": "章节",
        "title": "标题",
        "core_points": ["判断"],
        "source": "来源",
    }]
    (project / ".build" / "slides.json").write_text(json.dumps(slides), encoding="utf-8")
    if mode == "bitmap":
        elements = [
            {
                **element,
                **(
                    {"outline": "none"}
                    if element.get("type") == "body_asset"
                    else {}
                ),
            }
            for element in elements
        ]
    name = "page_specs.json" if mode == "deconstruct" else "bitmap_page_specs.json"
    (project / ".build" / name).write_text(
        json.dumps({"S01": {"elements": elements}}), encoding="utf-8"
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


def materialize_bitmap_contract(
    project: Path,
    *,
    source_px: list[int] | None = None,
    actual_px: list[int] | None = None,
    asset_path: str = ".build/assets/S01/S01_BODY_BITMAP.png",
) -> Path:
    source_px = source_px or [0, 0, 1200, 500]
    actual_px = actual_px or source_px
    asset = project / asset_path
    asset.parent.mkdir(parents=True, exist_ok=True)
    with Image.open(project / "blueprints" / "S01.png") as image:
        image.crop(tuple(actual_px)).save(asset)
    digest = hashlib.sha256(
        (project / "blueprints" / "S01.png").read_bytes()
    ).hexdigest()
    (project / ".build" / "bitmap_contract.json").write_text(
        json.dumps(
            {
                "schema_version": "6.0",
                "pipeline_revision": "6.0.0",
                "construction_mode": "bitmap",
                "pages": {
                    "S01": {
                        "asset_id": "S01_BODY_BITMAP",
                        "source_blueprint": "blueprints/S01.png",
                        "source_blueprint_sha256": digest,
                        "source_px": source_px,
                        "asset_path": asset_path,
                        "asset_sha256": hashlib.sha256(asset.read_bytes()).hexdigest(),
                        "fit": "contain",
                        "target": "runtime_body_box",
                        "outline": "none",
                    }
                },
            }
        ),
        encoding="utf-8",
    )
    return asset


class V6WindowsCompileTests(unittest.TestCase):
    def test_deconstruct_keeps_existing_page_spec_and_adds_stable_names(self):
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory)
            project_files(
                project,
                "deconstruct",
                [{"element_id": "BODY_TEXT", "type": "text", "box": [0, 0, 2, 1], "text": "正文"}],
            )
            generator = COMPILER.compile_project(project)
            source = generator.read_text(encoding="utf-8")
            self.assertIn('"construction_mode": "deconstruct"', source)
            self.assertIn("'element_id': 'BODY_TEXT'", source)
            self.assertIn('Name = f"EL_{element_id}_{number}"', source)
            spec = importlib.util.spec_from_file_location("compiled_v6_windows", generator)
            compiled = importlib.util.module_from_spec(spec)
            assert spec.loader is not None
            spec.loader.exec_module(compiled)
            self.assertEqual(["S01"], compiled.validate_embedded_contract(project_dir=project))

    def test_deconstruct_asset_keeps_legacy_spec_without_asset_path(self):
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory)
            project_files(
                project,
                "deconstruct",
                [{
                    "element_id": "MAP",
                    "type": "asset",
                    "asset_id": "MAP",
                    "box": [0, 0, 2, 1],
                }],
            )
            visual = json.loads(
                (project / ".build" / "visual_manifest.json").read_text(
                    encoding="utf-8"
                )
            )
            visual["pages"]["S01"]["visuals"] = [{
                "asset_id": "MAP",
                "kind": "map",
                "treatment": "crop",
                "source_px": [0, 0, 100, 100],
                "target_box_in": [0, 0, 2, 1],
            }]
            (project / ".build" / "visual_manifest.json").write_text(
                json.dumps(visual), encoding="utf-8"
            )
            asset = project / ".build" / "assets" / "S01" / "MAP.png"
            asset.parent.mkdir(parents=True)
            with Image.open(project / "blueprints" / "S01.png") as source:
                source.crop((0, 0, 100, 100)).save(asset)
            generator = COMPILER.compile_project(project)
            self.assertTrue(generator.is_file())

    def test_bitmap_uses_body_asset_and_contains_without_manual_box(self):
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory)
            asset = project / ".build" / "assets" / "S01" / "S01_BODY_BITMAP.png"
            project_files(
                project,
                "bitmap",
                [{
                    "element_id": "S01_BODY_BITMAP",
                    "asset_id": "S01_BODY_BITMAP",
                    "asset_path": ".build/assets/S01/S01_BODY_BITMAP.png",
                    "type": "body_asset",
                    "fit": "contain",
                    "target": "runtime_body_box",
                }],
            )
            materialize_bitmap_contract(project)
            generator = COMPILER.compile_project(project)
            source = generator.read_text(encoding="utf-8")
            self.assertIn("kind == \"body_asset\"", source)
            self.assertIn('"construction_mode": "bitmap"', source)

            spec = importlib.util.spec_from_file_location(
                "compiled_v6_windows_bitmap", generator
            )
            compiled = importlib.util.module_from_spec(spec)
            assert spec.loader is not None
            spec.loader.exec_module(compiled)
            self.assertEqual(
                "■ 判断",
                compiled.normalize_v6_core_point("■ ■ 判断"),
            )

            shape = SimpleNamespace(Line=SimpleNamespace(Visible=-1))
            shapes = SimpleNamespace(AddPicture=lambda *args: shape)
            slide = SimpleNamespace(Shapes=shapes)
            compiled.clear_shape_effects = lambda _shape: None
            compiled.add_body_asset(
                slide,
                project,
                {
                    "element_id": "S01_BODY_BITMAP",
                    "asset_id": "S01_BODY_BITMAP",
                    "asset_path": ".build/assets/S01/S01_BODY_BITMAP.png",
                    "type": "body_asset",
                    "fit": "contain",
                    "target": "runtime_body_box",
                    "outline": "none",
                },
                {"left": .56, "top": 1.2, "width": 11.13, "height": 5.0},
                "S01",
            )
            self.assertEqual(0, shape.Line.Visible)

    def test_missing_bitmap_asset_is_blocking(self):
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory)
            project_files(
                project,
                "bitmap",
                [{
                    "element_id": "S01_BODY_BITMAP",
                    "asset_id": "S01_BODY_BITMAP",
                    "asset_path": ".build/assets/S01/S01_BODY_BITMAP.png",
                    "type": "body_asset",
                    "fit": "contain",
                    "target": "runtime_body_box",
                }],
            )
            with self.assertRaises(FileNotFoundError):
                COMPILER.compile_project(project)

    def test_draft_tamper_is_blocked(self):
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory)
            project_files(
                project,
                "deconstruct",
                [{"element_id": "BODY_TEXT", "type": "text", "box": [0, 0, 2, 1], "text": "body"}],
            )
            (project / ".build" / "design_drafts" / "S01.png").write_bytes(b"tampered")
            with self.assertRaisesRegex(ValueError, "provenance chain"):
                COMPILER.compile_project(project)

    def test_bitmap_rejects_alternate_in_project_png(self):
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory)
            alternate = ".build/assets/S01/alternate.png"
            project_files(
                project,
                "bitmap",
                [{
                    "element_id": "S01_BODY_BITMAP",
                    "asset_id": "S01_BODY_BITMAP",
                    "asset_path": alternate,
                    "type": "body_asset",
                    "fit": "contain",
                    "target": "runtime_body_box",
                }],
            )
            materialize_bitmap_contract(project, asset_path=alternate)
            with self.assertRaisesRegex(ValueError, "binding"):
                COMPILER.compile_project(project)

    def test_deconstruct_rejects_parent_traversal_asset_id(self):
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory)
            project_files(
                project,
                "deconstruct",
                [{
                    "element_id": "BAD_ASSET",
                    "type": "asset",
                    "asset_id": "../evil",
                    "asset_path": ".build/assets/S01/../evil.png",
                    "box": [0, 0, 2, 1],
                }],
            )
            visual = json.loads(
                (project / ".build" / "visual_manifest.json").read_text(
                    encoding="utf-8"
                )
            )
            visual["pages"]["S01"]["visuals"] = [{
                "asset_id": "../evil",
                "kind": "photo",
                "treatment": "crop",
                "source_px": [0, 0, 100, 100],
                "target_box_in": [0, 0, 2, 1],
            }]
            (project / ".build" / "visual_manifest.json").write_text(
                json.dumps(visual), encoding="utf-8"
            )
            with self.assertRaisesRegex(ValueError, "unsafe"):
                COMPILER.compile_project(project)

    def test_bitmap_rejects_wrong_crop_even_with_synchronized_hash(self):
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory)
            project_files(
                project,
                "bitmap",
                [{
                    "element_id": "S01_BODY_BITMAP",
                    "asset_id": "S01_BODY_BITMAP",
                    "asset_path": ".build/assets/S01/S01_BODY_BITMAP.png",
                    "type": "body_asset",
                    "fit": "contain",
                    "target": "runtime_body_box",
                }],
            )
            materialize_bitmap_contract(
                project,
                source_px=[0, 0, 400, 400],
                actual_px=[400, 0, 800, 400],
            )
            asset = (
                project
                / ".build"
                / "assets"
                / "S01"
                / "S01_BODY_BITMAP.png"
            )
            Image.new("RGB", (400, 400), "red").save(asset)
            contract = json.loads(
                (project / ".build" / "bitmap_contract.json").read_text(
                    encoding="utf-8"
                )
            )
            contract["pages"]["S01"]["asset_sha256"] = hashlib.sha256(
                asset.read_bytes()
            ).hexdigest()
            (project / ".build" / "bitmap_contract.json").write_text(
                json.dumps(contract), encoding="utf-8"
            )
            with self.assertRaisesRegex(ValueError, "pixels differ"):
                COMPILER.compile_project(project)


if __name__ == "__main__":
    unittest.main()
