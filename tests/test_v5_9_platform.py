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


class V59PlatformTests(unittest.TestCase):
    def test_selects_backend_from_operating_system(self):
        platform = load_module("v59_platform", SKILL / "scripts" / "v59_platform.py")
        self.assertEqual("windows_com_v584", platform.select_backend("Windows", "AMD64").backend)
        self.assertEqual("mac_python_pptx_v1", platform.select_backend("Darwin", "arm64").backend)
        self.assertEqual("mac_python_pptx_v1", platform.select_backend("Darwin", "x86_64").backend)
        linux = platform.select_backend("Linux", "x86_64")
        self.assertFalse(linux.supported)
        with self.assertRaisesRegex(RuntimeError, "Linux is unsupported"):
            platform.require_supported_backend(linux)

    def test_runtime_report_records_derived_backend(self):
        platform = load_module("v59_platform_report", SKILL / "scripts" / "v59_platform.py")
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            report = platform.write_runtime_report(root, platform.select_backend("Darwin", "arm64"))
            stored = json.loads((root / ".build" / "runtime_report.json").read_text(encoding="utf-8"))
        self.assertEqual("mac_python_pptx_v1", report["builder_backend"])
        self.assertEqual(report, stored)

    def test_v59_brief_requires_auto_platform_and_builtin_imagegen(self):
        pipeline = load_module("v59_pipeline_brief", SKILL / "scripts" / "project_pipeline.py")
        valid = {
            "schema_version": "5.9",
            "pipeline_revision": "5.9.0",
            "requested_page_count": 1,
            "production_mode": "blueprint",
            "blueprint_engine": "builtin_imagegen",
            "platform_target": "auto",
            "source_files": ["/tmp/source.docx"],
        }
        self.assertEqual([], pipeline.validate_brief(valid))
        errors = pipeline.validate_brief(dict(valid, platform_target="mac", blueprint_engine="direct"))
        self.assertTrue(any("platform_target" in error for error in errors), errors)
        self.assertTrue(any("builtin_imagegen" in error for error in errors), errors)

    def test_compiler_dispatch_uses_backend_specific_compiler(self):
        pipeline = load_module(
            "v59_pipeline_dispatch", SKILL / "scripts" / "project_pipeline.py"
        )
        source = Path(pipeline.__file__).read_text(encoding="utf-8")
        self.assertIn('"windows_com_v584"', source)
        self.assertIn('"mac_python_pptx_v1"', source)
        self.assertIn("project_compiler_mac.py", source)

    def test_windows_template_treats_v59_as_modern_com_family(self):
        source = (
            SKILL / "assets" / "direct_blueprint_generator_template.py"
        ).read_text(encoding="utf-8")
        self.assertIn('in {"5.8", "5.9"}', source)
        self.assertIn('DispatchEx("PowerPoint.Application")', source)
        self.assertNotIn("from pptx import Presentation", source)

    def test_windows_compiler_accepts_v59_without_importing_python_pptx(self):
        compiler = load_module(
            "v59_windows_compiler", SKILL / "scripts" / "project_compiler.py"
        )
        cache = load_module(
            "v59_windows_source_cache", SKILL / "scripts" / "v58_source_cache.py"
        )
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory)
            build = project / ".build"
            build.mkdir()
            source_file = project / "source.txt"
            source_file.write_text("source", encoding="utf-8")
            brief = {
                "schema_version": "5.9",
                "pipeline_revision": "5.9.0",
                "requested_page_count": 1,
                "production_mode": "fast",
                "platform_target": "auto",
                "source_files": [str(source_file)],
            }
            slides = [{
                "slide_id": "S01",
                "chapter": "第一章",
                "title": "Windows V5.9",
                "core_points": ["保留 V5.8.4 COM 构建器"],
                "source": "资料来源：测试",
                "visual_route": {
                    "data_kind": "qualitative",
                    "qualitative_form": "parallel",
                },
                "evidence_inventory": [],
            }]
            specs = {"S01": {"elements": [{
                "type": "text",
                "text": "正文",
                "box": [0.2, 0.2, 2.0, 0.5],
            }]}}
            (project / "project_brief.json").write_text(
                json.dumps(brief, ensure_ascii=False), encoding="utf-8"
            )
            (build / "slides.json").write_text(
                json.dumps(slides, ensure_ascii=False), encoding="utf-8"
            )
            (build / "page_specs.json").write_text(
                json.dumps(specs, ensure_ascii=False), encoding="utf-8"
            )
            cache.write_source_digest(
                project,
                [source_file],
                {"text": "source"},
                schema_version="5.9",
            )
            generated = compiler.compile_project(project)
            generated_source = generated.read_text(encoding="utf-8")
        self.assertIn('"schema_version": "5.9"', generated_source)
        self.assertIn('DispatchEx("PowerPoint.Application")', generated_source)
        self.assertNotIn("from pptx import Presentation", generated_source)

    def test_documentation_declares_blueprint_before_platform_split(self):
        skill = (SKILL / "SKILL.md").read_text(encoding="utf-8")
        backend = (
            SKILL / "references" / "cross_platform_backend_contract.md"
        ).read_text(encoding="utf-8")
        imagegen = (
            SKILL / "prompts" / "imagegen_blueprint_prompt.md"
        ).read_text(encoding="utf-8")
        for text in (skill, backend):
            self.assertIn("windows_com_v584", text)
            self.assertIn("mac_python_pptx_v1", text)
            self.assertIn("structurally_valid_unrendered", text)
        self.assertIn("real first slide", imagegen.lower())
        self.assertIn("must not reach either builder", backend.lower())


if __name__ == "__main__":
    unittest.main()
