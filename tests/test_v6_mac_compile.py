from __future__ import annotations

import hashlib
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

from PIL import Image
from pptx import Presentation
from pptx.enum.shapes import MSO_SHAPE_TYPE


ROOT = Path(__file__).resolve().parents[1]
V1_COMPILER_SHA256 = "b7960b4abf7d37d82e1ed1db9f72a8c532ad6d24e9f91ae13f4d4b7a3c479453"
V1_TEMPLATE_SHA256 = "7e2605fced46c30ee78b5ce72d5ebb0ed8c391f10675e60dd1171dbc1b3982ec"


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def portable_font_path() -> Path:
    candidates = (
        Path("C:/Windows/Fonts/arial.ttf"),
        Path("/System/Library/Fonts/Supplemental/Arial.ttf"),
        Path("/Library/Fonts/Arial.ttf"),
    )
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    raise unittest.SkipTest("Arial-compatible test font is unavailable")


def inches(value) -> float:
    return float(value) / 914400.0


class V6MacCompileTests(unittest.TestCase):
    def _project(self, mode: str) -> Path:
        temporary = tempfile.TemporaryDirectory(prefix=f"v6_mac_{mode}_")
        self.addCleanup(temporary.cleanup)
        project = Path(temporary.name)
        build = project / ".build"
        build.mkdir()
        (project / "blueprints").mkdir()
        Image.new("RGB", (1600, 900), "#ddeeff").save(
            project / "blueprints" / "S01.png"
        )
        source = project / "source.txt"
        source.write_text("source", encoding="utf-8")
        brief = {
            "schema_version": "6.0",
            "pipeline_revision": "6.0.0",
            "requested_page_count": 1,
            "production_mode": "blueprint",
            "construction_mode": mode,
            "blueprint_engine": "builtin_imagegen",
            "platform_target": "auto",
            "source_files": [str(source)],
        }
        slides = [
            {
                "slide_id": "S01",
                "chapter": "Chapter",
                "title": "Mac V2",
                "core_points": ["Editable reconstruction"],
                "source": "Source: test",
            }
        ]
        (project / "project_brief.json").write_text(
            json.dumps(brief), encoding="utf-8"
        )
        (build / "slides.json").write_text(
            json.dumps(slides), encoding="utf-8"
        )
        (build / "visual_manifest.json").write_text(
            json.dumps(
                {
                    "schema_version": "6.0",
                    "pages": {
                        "S01": {
                            "design_draft_path": "blueprints/S01.png",
                            "design_draft_sha256": sha256_file(
                                project / "blueprints" / "S01.png"
                            ),
                            "visuals": [],
                        }
                    },
                }
            ),
            encoding="utf-8",
        )
        for name, payload in (
            ("authoring_bundle.json", {"schema_version": "6.0"}),
            ("blueprint_alignment.json", {"schema_version": "6.0", "pages": {}}),
        ):
            (build / name).write_text(json.dumps(payload), encoding="utf-8")
        return project

    def _compile_and_build(self, project: Path):
        compiler = load_module(
            f"v6_mac_compiler_{id(project)}",
            ROOT / "scripts" / "project_compiler_mac_v2.py",
        )
        generator = compiler.compile_project(project)
        runtime = load_module(f"v6_mac_runtime_{id(project)}", generator)
        output = runtime.build_deck(
            project / "output" / "report.pptx",
            font_catalog={"Microsoft YaHei": (portable_font_path(), 0)},
        )
        return generator, output

    def test_v1_files_remain_byte_identical(self):
        self.assertEqual(
            V1_COMPILER_SHA256,
            sha256_file(ROOT / "scripts" / "project_compiler_mac.py"),
        )
        self.assertEqual(
            V1_TEMPLATE_SHA256,
            sha256_file(ROOT / "assets" / "python_pptx_generator_template.py"),
        )

    def test_deconstruct_builds_native_editable_elements_with_stable_names(self):
        project = self._project("deconstruct")
        asset_dir = project / ".build" / "assets" / "S01"
        asset_dir.mkdir(parents=True)
        Image.new("RGB", (400, 100), "blue").save(asset_dir / "A01.png")
        elements = [
            {
                "type": "text",
                "element_id": "E_TEXT",
                "module_id": "claim",
                "text": "Editable body",
                "box": [0.1, 0.1, 2.0, 0.5],
            },
            {
                "type": "matrix",
                "element_id": "E_TABLE",
                "module_id": "table",
                "headers": ["A", "B"],
                "rows": [["x", "y"]],
                "box": [0.1, 0.8, 2.4, 1.0],
            },
            {
                "type": "column_chart",
                "element_id": "E_CHART",
                "module_id": "chart",
                "data": [
                    {"label": "2025", "value": 10},
                    {"label": "2026", "value": 12},
                ],
                "box": [2.8, 0.1, 2.5, 1.7],
            },
            {
                "type": "combo_chart",
                "element_id": "E_COMBO",
                "module_id": "combo",
                "data": [
                    {"label": "2025", "column": 10, "line": 20},
                    {"label": "2026", "column": 12, "line": 18},
                ],
                "box": [5.5, 0.1, 2.8, 1.7],
            },
            {
                "type": "flow",
                "element_id": "E_FLOW",
                "module_id": "flow",
                "steps": ["First", "Second", "Third"],
                "box": [0.1, 2.1, 5.5, 0.8],
            },
            {
                "type": "asset",
                "element_id": "E_MAP",
                "module_id": "map",
                "asset_id": "A01",
                "box": [9.0, 2.0, 2.0, 2.0],
                "coord_space": "absolute",
                "fit": "contain",
            },
        ]
        (project / ".build" / "page_specs.json").write_text(
            json.dumps({"S01": {"elements": elements}}), encoding="utf-8"
        )
        manifest = json.loads(
            (project / ".build" / "visual_manifest.json").read_text(
                encoding="utf-8"
            )
        )
        manifest["pages"]["S01"]["visuals"] = [
            {
                "treatment": "crop",
                "asset_id": "A01",
                "kind": "map",
                "source_px": [0, 0, 400, 100],
                "target_box_in": [9.0, 2.0, 2.0, 2.0],
                "target_coord_space": "absolute",
            }
        ]
        (project / ".build" / "visual_manifest.json").write_text(
            json.dumps(manifest), encoding="utf-8"
        )
        spec_module = load_module(
            f"v6_mac_spec_{id(project)}", ROOT / "scripts" / "v6_mac_spec.py"
        )
        spec_module.materialize_mac_page_specs(project)
        generator, output = self._compile_and_build(project)

        prs = Presentation(output)
        slide = prs.slides[0]
        names = [shape.name for shape in slide.shapes]
        self.assertTrue(any(name.startswith("EL_E_TEXT_") for name in names))
        self.assertTrue(
            any(
                shape.name.startswith("EL_E_TABLE_") and shape.has_table
                for shape in slide.shapes
            )
        )
        self.assertTrue(
            any(
                shape.name.startswith("EL_E_CHART_") and shape.has_chart
                for shape in slide.shapes
            )
        )
        combo = [
            shape
            for shape in slide.shapes
            if shape.name.startswith("EL_E_COMBO_") and shape.has_chart
        ]
        self.assertEqual(2, len(combo))
        flow = [
            shape for shape in slide.shapes if shape.name.startswith("EL_E_FLOW_")
        ]
        self.assertGreaterEqual(len(flow), 5)
        self.assertEqual(MSO_SHAPE_TYPE.LINE, flow[0].shape_type)
        self.assertTrue(
            any(shape.shape_type != MSO_SHAPE_TYPE.LINE for shape in flow[1:])
        )
        picture = next(
            shape
            for shape in slide.shapes
            if shape.name.startswith("EL_E_MAP_")
        )
        self.assertAlmostEqual(2.0, inches(picture.width), places=2)
        self.assertAlmostEqual(0.5, inches(picture.height), places=2)
        self.assertAlmostEqual(2.75, inches(picture.top), places=2)
        self.assertEqual(0, picture.crop_left)
        self.assertEqual(0, picture.crop_right)
        generated_module = load_module(
            f"v6_generated_assert_{id(project)}", generator
        )
        self.assertTrue(
            all(
                element["type"] != "body_asset"
                for element in generated_module.PAGE_SPECS["S01"]["elements"]
            )
        )
        compile_report = json.loads(
            (project / ".build" / "compile_report.json").read_text(
                encoding="utf-8"
            )
        )
        self.assertEqual("6.0", compile_report["schema_version"])
        self.assertEqual("deconstruct", compile_report["construction_mode"])
        self.assertEqual("mac_python_pptx_v2", compile_report["builder_backend"])

    def test_bitmap_build_uses_exact_runtime_body_contain_and_editable_skeleton(self):
        project = self._project("bitmap")
        asset_id = "S01_BODY_BITMAP"
        asset_dir = project / ".build" / "assets" / "S01"
        asset_dir.mkdir(parents=True)
        asset = asset_dir / f"{asset_id}.png"
        Image.new("RGB", (1000, 400), "#225588").save(asset)
        page_specs = {
            "S01": {
                "elements": [
                    {
                        "type": "body_asset",
                        "element_id": asset_id,
                        "asset_id": asset_id,
                        "fit": "contain",
                        "target": "runtime_body_box",
                    }
                ]
            }
        }
        contract = {
            "schema_version": "6.0",
            "pipeline_revision": "6.0.0",
            "construction_mode": "bitmap",
            "pages": {
                "S01": {
                    "asset_id": asset_id,
                    "asset_path": f".build/assets/S01/{asset_id}.png",
                    "asset_sha256": sha256_file(asset),
                    "source_blueprint": "blueprints/S01.png",
                    "source_blueprint_sha256": sha256_file(
                        project / "blueprints" / "S01.png"
                    ),
                    "fit": "contain",
                    "target": "runtime_body_box",
                }
            },
        }
        (project / ".build" / "bitmap_page_specs.json").write_text(
            json.dumps(page_specs), encoding="utf-8"
        )
        (project / ".build" / "bitmap_contract.json").write_text(
            json.dumps(contract), encoding="utf-8"
        )
        _, output = self._compile_and_build(project)

        prs = Presentation(output)
        slide = prs.slides[0]
        body = next(
            shape
            for shape in slide.shapes
            if shape.name.startswith(f"EL_{asset_id}_")
        )
        core = next(shape for shape in slide.shapes if shape.name == "SKEL_CORE")
        source = next(shape for shape in slide.shapes if shape.name == "SKEL_SOURCE")
        body_left = inches(core.left)
        body_top = inches(core.top + core.height) + 0.12
        body_right = body_left + inches(core.width)
        body_bottom = inches(source.top) - 0.195
        box_width = body_right - body_left
        box_height = body_bottom - body_top
        expected_width = min(box_width, box_height * 2.5)
        expected_height = expected_width / 2.5
        self.assertAlmostEqual(expected_width, inches(body.width), places=2)
        self.assertAlmostEqual(expected_height, inches(body.height), places=2)
        self.assertAlmostEqual(
            body_left + (box_width - expected_width) / 2,
            inches(body.left),
            places=2,
        )
        self.assertAlmostEqual(
            body_top + (box_height - expected_height) / 2,
            inches(body.top),
            places=2,
        )
        self.assertEqual(0, body.crop_left)
        self.assertEqual(0, body.crop_bottom)
        self.assertTrue(all(
            any(shape.name == skeleton and shape.has_text_frame for shape in slide.shapes)
            for skeleton in (
                "SKEL_CHAPTER",
                "SKEL_TITLE",
                "SKEL_CORE",
                "SKEL_SOURCE",
                "SKEL_PAGE_NUMBER",
            )
        ))
        pictures = [
            shape for shape in slide.shapes
            if shape.shape_type == MSO_SHAPE_TYPE.PICTURE
        ]
        self.assertEqual(1, len(pictures))
        asset_report = json.loads(
            (project / ".build" / "mac_asset_report.json").read_text(
                encoding="utf-8"
            )
        )
        self.assertEqual("6.0", asset_report["schema_version"])
        self.assertEqual("bitmap", asset_report["construction_mode"])
        self.assertEqual(sha256_file(asset), asset_report["assets"][0]["source_sha256"])

    def test_compiler_rejects_non_v6_projects(self):
        project = self._project("deconstruct")
        brief = json.loads((project / "project_brief.json").read_text(encoding="utf-8"))
        brief["schema_version"] = "5.9"
        (project / "project_brief.json").write_text(
            json.dumps(brief), encoding="utf-8"
        )
        compiler = load_module(
            "v6_mac_compiler_invalid",
            ROOT / "scripts" / "project_compiler_mac_v2.py",
        )
        with self.assertRaisesRegex(ValueError, "6.0.0"):
            compiler.compile_project(project)


if __name__ == "__main__":
    unittest.main()
