from __future__ import annotations

import importlib.util
import json
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest import mock


SKILL = Path(__file__).resolve().parents[1]


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class V57VisualContractTests(unittest.TestCase):
    def test_skill_and_prompt_define_reference_style_as_positive_recipe(self):
        skill = (SKILL / "SKILL.md").read_text(encoding="utf-8")
        prompt = (SKILL / "prompts" / "imagegen_blueprint_prompt.md").read_text(encoding="utf-8")
        layout = (SKILL / "references" / "layout_and_chart_rules.md").read_text(encoding="utf-8")
        for text in (skill, prompt, layout):
            self.assertIn("analytical canvas", text)
            self.assertIn("6-12% of the body area", text)
            self.assertIn("reserved icon lane", text)
        self.assertIn("Standard Report PPT V5.7", skill)
        self.assertIn("schema_version\": \"5.7", skill)

    def test_visual_balance_rejects_oversized_supporting_raster(self):
        contracts = load_module("v57_contracts_visual", SKILL / "scripts" / "v56_contracts.py")
        page_specs = {
            "S01": {
                "elements": [
                    {"type": "hbar_chart", "box": [0.7, 3.0, 5.0, 2.5]},
                    {"type": "asset", "asset_id": "A01", "box": [6.0, 3.0, 5.8, 2.8]},
                ]
            }
        }
        manifest = {
            "schema_version": "5.7",
            "pages": {
                "S01": {
                    "visuals": [
                        {
                            "asset_id": "A01",
                            "kind": "pictogram",
                            "disposition": "crop",
                            "role": "supporting_accent",
                        }
                    ]
                }
            },
        }
        errors = contracts.validate_blueprint_visual_balance(page_specs, manifest)
        self.assertTrue(any("6-12%" in error for error in errors), errors)


class V57PipelineContractTests(unittest.TestCase):
    def test_fast_page_specs_uses_canonical_module_content(self):
        fast = load_module("v57_fast_specs", SKILL / "scripts" / "fast_page_specs.py")
        specs = fast.build_page_specs(
            [
                {
                    "slide_id": "S01",
                    "modules": [
                        {"module_id": "M01", "title": "高速互联", "content": "40-78层高频PCB"}
                    ],
                }
            ]
        )
        self.assertEqual("40-78层高频PCB", specs["S01"]["elements"][0]["body"])

    def test_pipeline_accepts_v57_and_records_v57_timing(self):
        pipeline = load_module("v57_pipeline", SKILL / "scripts" / "project_pipeline.py")
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "project_brief.json").write_text(
                json.dumps(
                    {
                        "schema_version": "5.7",
                        "requested_page_count": 3,
                        "production_mode": "fast",
                        "confirmation_source": "user_explicit",
                    }
                ),
                encoding="utf-8",
            )
            result = pipeline.init_project(root)
            timing = json.loads((root / ".build" / "pipeline_timing.json").read_text(encoding="utf-8"))
        self.assertEqual("5.7", result["schema_version"])
        self.assertEqual("5.7", timing["schema_version"])

    def test_v57_packaging_reuses_current_audits_instead_of_rerunning_them(self):
        pack = load_module("v57_pack", SKILL / "scripts" / "pack_delivery.py")
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            desktop = root / "Desktop"
            project = root / "project"
            desktop.mkdir()
            project.mkdir()
            (project / ".build").mkdir()
            (project / "blueprints").mkdir()
            (project / "blueprints" / "S01.png").write_bytes(b"png")
            (project / "project_brief.json").write_text(
                json.dumps(
                    {
                        "schema_version": "5.7",
                        "requested_page_count": 1,
                        "production_mode": "blueprint",
                        "blueprint_engine": "direct",
                    }
                ),
                encoding="utf-8",
            )
            generator = project / "generate_deck.py"
            generator.write_text("DECK_META={'schema_version':'5.7'}\ndef build_slide_S01():\n    pass\n", encoding="utf-8")
            pptx = project / "report.pptx"
            with zipfile.ZipFile(pptx, "w") as archive:
                archive.writestr(
                    "ppt/presentation.xml",
                    "<p:presentation xmlns:p='http://schemas.openxmlformats.org/presentationml/2006/main'><p:sldIdLst><p:sldId id='256'/></p:sldIdLst></p:presentation>",
                )
            output = desktop / "delivery.zip"
            with mock.patch.object(pack, "_run_skeleton_audit", side_effect=AssertionError("duplicate audit")), mock.patch.object(
                pack, "_run_asset_audit", side_effect=AssertionError("duplicate audit")
            ), mock.patch.object(pack, "_validate_v57_project", return_value=[]):
                pack.package_direct_delivery(
                    project_dir=project,
                    pptx_path=pptx,
                    generator_path=generator,
                    output_zip=output,
                    desktop_dir=desktop,
                )
            record = json.loads((project / ".build" / "delivery_record.json").read_text(encoding="utf-8"))
            output_exists = output.is_file()
        self.assertTrue(output_exists)
        self.assertIn("package_seconds", record)
        self.assertIn("delivery_verify_seconds", record)


if __name__ == "__main__":
    unittest.main()
