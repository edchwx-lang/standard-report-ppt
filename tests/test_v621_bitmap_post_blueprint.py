from __future__ import annotations

import importlib.util
import os
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def load(name: str, relative: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / relative)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


PIPELINE = load("v621_pipeline_tests", "scripts/project_pipeline.py")
AUDIT = load("v621_audit_tests", "scripts/v6_editability_audit.py")


class V621BitmapPostBlueprintTests(unittest.TestCase):
    @unittest.skipUnless(os.name == "nt", "requires Windows path semantics")
    def test_windows_bitmap_render_environment_discovers_bundled_runtime(self):
        with tempfile.TemporaryDirectory() as directory:
            dependencies = Path(directory) / "dependencies"
            python = dependencies / "python" / "python.exe"
            node = dependencies / "node" / "bin" / "node.exe"
            modules = dependencies / "node" / "node_modules"
            override = dependencies / "bin" / "override"
            for path in (python, node):
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(b"")
            modules.mkdir(parents=True)
            override.mkdir(parents=True)

            env = PIPELINE._bitmap_render_environment(
                {"PATH": "existing"}, executable=python
            )

            self.assertEqual(str(node.resolve()), env["RUNTIME_NODE"])
            self.assertEqual(str(modules.resolve()), env["RUNTIME_NODE_MODULES"])
            self.assertEqual(str(override.resolve()), env["RUNTIME_BIN_DIR"])
            self.assertEqual(str(modules.resolve()), env["NODE_PATH"])
            self.assertEqual(str(override.resolve()), env["PATH"].split(os.pathsep)[0])

    def test_bitmap_repair_snapshot_ignores_pipeline_owned_acceptance_state(self):
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory)
            (project / ".build").mkdir()
            (project / "project_brief.json").write_text("{}", encoding="utf-8")
            (project / "generate_deck.py").write_text("pass\n", encoding="utf-8")
            (project / ".build" / "bitmap_acceptance.json").write_text(
                "{}", encoding="utf-8"
            )
            snapshot = PIPELINE._v6_repair_contract_snapshot(project, "bitmap")
            self.assertNotIn(".build/bitmap_acceptance.json", snapshot)

    def test_bitmap_theme_signatures_are_order_insensitive(self):
        expected = {
            "slide_size": [13.333, 7.5],
            "masters": 1,
            "theme_signatures": [
                {"colors": ["a"], "fonts": ["x"]},
                {"colors": ["b"], "fonts": ["y"]},
            ],
        }
        actual = {
            "slide_size": [13.333, 7.5],
            "masters": 1,
            "theme_signatures": list(reversed(expected["theme_signatures"])),
        }
        self.assertTrue(AUDIT._bitmap_design_signatures_match(actual, expected))


if __name__ == "__main__":
    unittest.main()
