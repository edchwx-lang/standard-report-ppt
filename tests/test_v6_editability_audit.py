from __future__ import annotations

import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

from PIL import Image
from pptx import Presentation
from pptx.chart.data import CategoryChartData
from pptx.enum.chart import XL_CHART_TYPE
from pptx.enum.shapes import MSO_SHAPE
from pptx.util import Inches


ROOT = Path(__file__).resolve().parents[1]
RUNTIME = Path(r"C:\Users\edchw\.cache\codex-runtimes\codex-primary-runtime\dependencies\python")


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def reviewed(decisions=None):
    return {"pages": {"S01": {"text_decisions": decisions or [
        {"role": "chapter", "selected": "Chapter"}, {"role": "title", "selected": "Title"},
        {"role": "core_point", "selected": "Core"}, {"role": "source", "selected": "Source"},
        {"role": "page_number", "selected": "1"},
    ], "reconstruction_contract": {"module_bindings": []}, "visuals": []}}}


def add_skeleton(slide):
    definitions = (("SKEL_CHAPTER", .56, .1, 11.13, .2, "Chapter"), ("SKEL_TITLE", .56, .3, 11.13, .2, "Title"), ("SKEL_CORE", .56, .5, 11.13, .1, "Core"), ("SKEL_SOURCE", .56, 6.8, 11.13, .1, "Source"), ("SKEL_PAGE_NUMBER", .56, 6.95, 1, .1, "1"))
    for name, left, top, width, height, text in definitions:
        shape = slide.shapes.add_textbox(Inches(left), Inches(top), Inches(width), Inches(height))
        shape.name, shape.text = name, text


def add_picture(slide, asset, name, left=.56, top=.88, width=11.13, height=5.565):
    shape = slide.shapes.add_picture(str(asset), Inches(left), Inches(top), Inches(width), Inches(height))
    shape.name = name
    return shape


class V6EditabilityAuditTests(unittest.TestCase):
    def setUp(self):
        self.subject = load_module("v6_editability_audit", ROOT / "scripts" / "v6_editability_audit.py")
        self.bitmap = load_module("v6_bitmap", ROOT / "scripts" / "v6_bitmap.py")

    def deck(self, directory):
        ppt = Presentation(); ppt.slide_width = Inches(12.25); ppt.slide_height = Inches(7.5)
        slide = ppt.slides.add_slide(ppt.slide_layouts[6]); add_skeleton(slide)
        return ppt, slide, Path(directory) / "deck.pptx"

    def bitmap_contract(self, directory):
        project = Path(directory) / "project"; (project / "blueprints").mkdir(parents=True)
        Image.new("RGB", (400, 200), "navy").save(project / "blueprints" / "S01.png")
        review = self.bitmap.prepare_bitmap_review(project)
        alignment = {"schema_version": "6.0", "pipeline_revision": "6.0.0", "construction_mode": "bitmap", "pages": {"S01": {"reviewed_full_page": True, "blueprint_sha256": review["pages"]["S01"]["blueprint_sha256"], "source_px": [10, 20, 390, 190], "excluded_skeleton_regions": list(self.bitmap.EXCLUDED_SKELETON_REGIONS)}}}
        (project / ".build" / "bitmap_alignment.json").write_text(json.dumps(alignment), encoding="utf-8")
        contract = self.bitmap.materialize_bitmap_assets(project)
        return project, contract, project / contract["pages"]["S01"]["asset_path"]

    def test_postbuild_uses_alignment_text_and_prefix_element_names(self):
        with tempfile.TemporaryDirectory() as directory:
            ppt, slide, deck = self.deck(directory)
            text = slide.shapes.add_textbox(Inches(1), Inches(1), Inches(3), Inches(.3)); text.name = "EL_TEXT_1"; text.text = "Body copy"
            table = slide.shapes.add_table(2, 2, Inches(1), Inches(2), Inches(3), Inches(1)); table.name = "EL_TABLE_1"
            data = CategoryChartData(); data.categories = ["A"]; data.add_series("S", (1,))
            chart = slide.shapes.add_chart(XL_CHART_TYPE.COLUMN_CLUSTERED, Inches(5), Inches(2), Inches(2), Inches(1), data); chart.name = "EL_CHART_1"
            node = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, Inches(1), Inches(4), Inches(1), Inches(.3)); node.name = "EL_FLOW_1"
            line = slide.shapes.add_connector(1, Inches(2), Inches(4.1), Inches(3), Inches(4.1)); line.name = "EL_FLOW_2"
            ppt.save(deck)
            specs = {"S01": {"elements": [{"element_id": "TEXT", "type": "text"}, {"element_id": "TABLE", "type": "matrix"}, {"element_id": "CHART", "type": "column_chart"}, {"element_id": "FLOW", "type": "flow"}]}}
            alignment = reviewed(); alignment["pages"]["S01"]["text_decisions"].append({"role": "body", "selected": "Body copy"})
            self.assertTrue(self.subject.audit_deconstruction_pptx(deck, specs, alignment)["ok"])
            slide.shapes._spTree.remove(line._element); ppt.save(deck)
            self.assertFalse(self.subject.audit_deconstruction_pptx(deck, specs, alignment)["ok"])
            ppt, slide, deck = self.deck(directory)
            text_only = slide.shapes.add_textbox(Inches(1), Inches(4), Inches(2), Inches(.3)); text_only.name = "EL_FLOW_1"; text_only.text = "not a flow node"
            ppt.save(deck)
            self.assertFalse(self.subject.audit_deconstruction_pptx(deck, {"S01": {"elements": [{"element_id": "FLOW", "type": "flow"}]}}, reviewed())["ok"])

    def test_large_body_picture_fails_for_editability_not_missing_text(self):
        with tempfile.TemporaryDirectory() as directory:
            asset = Path(directory) / "map.png"; Image.new("RGB", (400, 200), "navy").save(asset)
            ppt, slide, deck = self.deck(directory); add_picture(slide, asset, "EL_MAP_1"); ppt.save(deck)
            specs = {"S01": {"elements": [{"element_id": "MAP", "asset_id": "MAP_ASSET", "type": "asset"}]}}
            report = self.subject.audit_deconstruction_pptx(deck, specs, reviewed())
            self.assertFalse(report["ok"])
            self.assertTrue(any("large body picture" in item["message"] for item in report["blockers"]))
            self.assertTrue(self.subject.audit_deconstruction_pptx(deck, specs, reviewed(), ["MAP_ASSET"])["ok"])

    def test_bitmap_audit_consumes_task1_contract_and_rejects_bad_contain(self):
        with tempfile.TemporaryDirectory() as directory:
            project, contract, asset = self.bitmap_contract(directory)
            for case, geometry, crop in (("good", (.56, 1.1725, 11.13, 4.98), 0), ("small", (.56, 1.1725, 10, 4.48), 0), ("off_center", (.70, 1.1725, 11.13, 4.98), 0), ("stretch", (.56, 1.1725, 11.13, 4.7), 0), ("crop", (.56, 1.1725, 11.13, 4.98), 10000)):
                with self.subTest(case=case):
                    ppt, slide, deck = self.deck(directory)
                    picture = add_picture(slide, asset, "EL_S01_BODY_BITMAP_1", *geometry)
                    picture.crop_left = crop
                    ppt.save(deck)
                    report = self.subject.audit_bitmap_pptx(deck, contract)
                    self.assertEqual(case == "good", report["ok"])
            ppt, slide, deck = self.deck(directory); add_picture(slide, asset, "EL_S01_BODY_BITMAP_1"); add_picture(slide, asset, "EL_OTHER_1", 1, 1, 2, 1); ppt.save(deck)
            self.assertFalse(self.subject.audit_bitmap_pptx(deck, contract)["ok"])


if __name__ == "__main__":
    unittest.main()
