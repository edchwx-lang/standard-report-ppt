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


class V59SharedContractsTests(unittest.TestCase):
    def test_v59_authoring_materializes_modern_artifacts(self):
        authoring = load_module("v59_authoring", SKILL / "scripts" / "v583_authoring.py")
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            build = root / ".build"
            build.mkdir()
            bundle = {
                "schema_version": "5.9",
                "slides": [{
                    "slide_id": "S01", "chapter": "第一章", "title": "跨平台结论",
                    "core_points": ["蓝图先于平台后端"], "source": "资料来源：测试",
                    "visual_route": {"data_kind": "qualitative", "qualitative_form": "parallel"},
                    "evidence_inventory": [],
                }],
                "page_specs": {"S01": {"elements": []}},
                "visual_manifest": {"schema_version": "5.9", "pages": {"S01": {}}},
            }
            (build / "authoring_bundle.json").write_text(json.dumps(bundle, ensure_ascii=False), encoding="utf-8")
            result = authoring.materialize_project(root)
            manifest = json.loads((build / "visual_manifest.json").read_text(encoding="utf-8"))
            benchmark = json.loads((build / "blueprint_text_benchmark.json").read_text(encoding="utf-8"))
        self.assertEqual("5.9", result["schema_version"])
        self.assertEqual("5.9", manifest["schema_version"])
        self.assertEqual("5.9", benchmark["schema_version"])

    def test_v59_prebuild_accepts_platform_neutral_specs(self):
        prebuild = load_module("v59_prebuild", SKILL / "scripts" / "v58_prebuild.py")
        brief = {"schema_version": "5.9", "requested_page_count": 1, "production_mode": "fast"}
        slides = [{
            "slide_id": "S01", "chapter": "第一章", "title": "平台无关页面",
            "core_points": ["同一规格供双后端消费"], "source": "资料来源：测试",
            "visual_route": {"data_kind": "qualitative", "qualitative_form": "parallel"},
            "evidence_inventory": [],
        }]
        specs = {"S01": {"elements": [{"type": "text", "text": "正文", "box": [0, 0, 2, 1]}]}}
        self.assertEqual([], prebuild.validate_project_specs(brief, slides, specs))
