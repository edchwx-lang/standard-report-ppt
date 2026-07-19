from __future__ import annotations

import importlib.util
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


class V59MacRuntimeTests(unittest.TestCase):
    def test_existing_dependencies_do_not_install_anything(self):
        runtime = load_module("v59_mac_runtime", SKILL / "scripts" / "ensure_macos_runtime.py")
        result = runtime.ensure_macos_runtime(importer=lambda: {
            "pptx": "1", "PIL": "1", "lxml": "1", "xlsxwriter": "1", "fontTools": "1",
        })
        self.assertTrue(result["ok"])
        self.assertEqual("existing", result["fonttools_source"])

    def test_missing_required_dependency_blocks_without_pip(self):
        runtime = load_module("v59_mac_runtime_missing", SKILL / "scripts" / "ensure_macos_runtime.py")
        with self.assertRaisesRegex(RuntimeError, "missing macOS runtime dependencies"):
            runtime.ensure_macos_runtime(importer=lambda: {
                "pptx": "1", "PIL": "1", "lxml": "1", "xlsxwriter": None, "fontTools": "1",
            })

    def test_report_is_written_inside_project(self):
        runtime = load_module("v59_mac_runtime_report", SKILL / "scripts" / "ensure_macos_runtime.py")
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            runtime.ensure_macos_runtime(project_dir=root, importer=lambda: {
                "pptx": "1", "PIL": "1", "lxml": "1", "xlsxwriter": "1", "fontTools": "1",
            })
            self.assertTrue((root / ".build" / "macos_runtime_report.json").is_file())
