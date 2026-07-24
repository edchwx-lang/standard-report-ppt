from __future__ import annotations

import hashlib
import importlib.util
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


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def skeleton(slide):
    for name, top in (("SKEL_CHAPTER", .1), ("SKEL_TITLE", .3), ("SKEL_CORE", .5), ("SKEL_SOURCE", 6.8), ("SKEL_PAGE_NUMBER", 6.9)):
        shape = slide.shapes.add_textbox(Inches(.1), Inches(top), Inches(1), Inches(.1))
        shape.name = name


def add_asset(slide, image: Path, name: str, left=1, top=1, width=5, height=3):
    shape = slide.shapes.add_picture(str(image), Inches(left), Inches(top), Inches(width), Inches(height))
    shape.name = name


class V6EditabilityAuditTests(unittest.TestCase):
    def setUp(self):
        self.subject = load_module(
            "v6_editability_audit", ROOT / "scripts" / "v6_editability_audit.py"
        )

    def make_presentation(self, directory: Path):
        presentation = Presentation()
        presentation.slide_width = Inches(12)
        presentation.slide_height = Inches(7.5)
        slide = presentation.slides.add_slide(presentation.slide_layouts[6])
        skeleton(slide)
        return presentation, slide, directory / "deck.pptx"

    def test_composite_half_slide_body_picture_fails_postbuild(self):
        with tempfile.TemporaryDirectory() as directory:
            directory = Path(directory)
            image = directory / "body.png"
            Image.new("RGB", (500, 300), "navy").save(image)
            ppt, slide, deck = self.make_presentation(directory)
            add_asset(slide, image, "EL_COMPOSITE", 3, 2, 6, 3.5)
            ppt.save(deck)
            specs = {"S01": {"elements": [{"element_id": "COMPOSITE", "type": "asset"}], "reconstruction_contract": {"module_bindings": [{"module_id": "body", "element_ids": ["COMPOSITE"]}], "text_decisions": [{"selected": "Editable conclusion"}]}}}
            report = self.subject.audit_deconstruction_pptx(deck, specs, {"pages": {"S01": {}}})
            self.assertFalse(report["ok"])
            self.assertIn("DECONSTRUCTION_EDITABILITY_FAILED", [item["code"] for item in report["blockers"]])

    def test_editable_text_table_chart_and_element_names_pass(self):
        with tempfile.TemporaryDirectory() as directory:
            directory = Path(directory)
            ppt, slide, deck = self.make_presentation(directory)
            text = slide.shapes.add_textbox(Inches(1), Inches(1), Inches(3), Inches(.5))
            text.name = "EL_TEXT"
            text.text = "Editable conclusion"
            table = slide.shapes.add_table(2, 2, Inches(1), Inches(2), Inches(3), Inches(1))
            table.name = "EL_TABLE"
            data = CategoryChartData(); data.categories = ["A", "B"]; data.add_series("S", (1, 2))
            chart = slide.shapes.add_chart(XL_CHART_TYPE.COLUMN_CLUSTERED, Inches(5), Inches(2), Inches(3), Inches(2), data)
            chart.name = "EL_CHART"
            flow = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, Inches(1), Inches(4), Inches(1), Inches(.5)); flow.name = "EL_FLOW_NODE"
            connector = slide.shapes.add_connector(1, Inches(2), Inches(4.25), Inches(3), Inches(4.25)); connector.name = "EL_FLOW_CONNECTOR"
            ppt.save(deck)
            specs = {"S01": {"elements": [{"element_id": "TEXT", "type": "text"}, {"element_id": "TABLE", "type": "matrix"}, {"element_id": "CHART", "type": "column_chart"}, {"element_id": "FLOW_NODE", "type": "flow"}, {"element_id": "FLOW_CONNECTOR", "type": "flow"}], "reconstruction_contract": {"text_decisions": [{"selected": "Editable conclusion"}]}}}
            report = self.subject.audit_deconstruction_pptx(deck, specs, {"pages": {"S01": {}}})
            self.assertTrue(report["ok"])

    def test_native_basic_shape_prevents_large_body_asset_false_positive(self):
        with tempfile.TemporaryDirectory() as directory:
            directory = Path(directory)
            image = directory / "body.png"
            Image.new("RGB", (500, 300), "navy").save(image)
            ppt, slide, deck = self.make_presentation(directory)
            add_asset(slide, image, "EL_MAP", 0, .6, 12, 6.2)
            rect = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, Inches(1), Inches(1), Inches(1), Inches(.5))
            rect.name = "EL_RECT"
            ppt.save(deck)
            specs = {"S01": {"elements": [{"element_id": "MAP", "type": "asset"}, {"element_id": "RECT", "type": "rect"}], "reconstruction_contract": {"text_decisions": []}}}
            report = self.subject.audit_deconstruction_pptx(deck, specs, {"pages": {"S01": {}}})
            self.assertTrue(report["ok"])

    def test_bitmap_contract_requires_one_correct_contained_picture_and_skeleton(self):
        with tempfile.TemporaryDirectory() as directory:
            directory = Path(directory)
            image = directory / "body.png"
            Image.new("RGB", (400, 200), "navy").save(image)
            ppt, slide, deck = self.make_presentation(directory)
            add_asset(slide, image, "EL_S01_BODY_BITMAP", 1, 1, 4, 2)
            ppt.save(deck)
            contract = {"pages": {"S01": {"asset_id": "S01_BODY_BITMAP", "asset_path": str(image), "asset_sha256": hashlib.sha256(image.read_bytes()).hexdigest(), "fit": "contain", "target": "runtime_body_box", "runtime_body_box": [1, 1, 4, 2]}}}
            self.assertTrue(self.subject.audit_bitmap_pptx(deck, contract)["ok"])
            contract["pages"]["S01"]["asset_sha256"] = "0" * 64
            self.assertFalse(self.subject.audit_bitmap_pptx(deck, contract)["ok"])

    def test_bitmap_contract_rejects_duplicates_and_stretching(self):
        with tempfile.TemporaryDirectory() as directory:
            directory = Path(directory)
            image = directory / "body.png"
            Image.new("RGB", (400, 200), "navy").save(image)
            ppt, slide, deck = self.make_presentation(directory)
            add_asset(slide, image, "EL_S01_BODY_BITMAP", 1, 1, 4, 3)
            ppt.save(deck)
            contract = {"pages": {"S01": {"asset_id": "S01_BODY_BITMAP", "asset_path": str(image), "asset_sha256": hashlib.sha256(image.read_bytes()).hexdigest(), "fit": "contain", "target": "runtime_body_box", "runtime_body_box": [1, 1, 4, 3]}}}
            report = self.subject.audit_bitmap_pptx(deck, contract)
            self.assertFalse(report["ok"])
            self.assertIn("BITMAP_CONTRACT_INVALID", [item["code"] for item in report["blockers"]])
            add_asset(slide, image, "EL_S01_BODY_BITMAP", 1, 1, 4, 2)
            ppt.save(deck)
            report = self.subject.audit_bitmap_pptx(deck, contract)
            self.assertFalse(report["ok"])
            self.assertIn("BITMAP_CONTRACT_INVALID", [item["code"] for item in report["blockers"]])


if __name__ == "__main__":
    unittest.main()
