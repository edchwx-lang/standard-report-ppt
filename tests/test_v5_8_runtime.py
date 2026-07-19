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


class V58WindowsRuntimeTests(unittest.TestCase):
    def test_windows_generator_template_remains_com_only(self):
        source = (
            SKILL / "assets" / "direct_blueprint_generator_template.py"
        ).read_text(encoding="utf-8")
        self.assertIn('DispatchEx("PowerPoint.Application")', source)
        self.assertNotIn("from pptx import Presentation", source)

    def test_preflight_initializes_com_before_powerpoint_dispatch(self):
        source = (SKILL / "scripts" / "project_pipeline.py").read_text(encoding="utf-8")
        initialize = source.index("pythoncom.CoInitialize()")
        dispatch = source.index('win32com.client.DispatchEx("PowerPoint.Application")')
        uninitialize = source.index("pythoncom.CoUninitialize()", dispatch)
        self.assertLess(initialize, dispatch)
        self.assertGreater(uninitialize, dispatch)

    def test_runtime_check_is_noop_when_pywin32_is_available(self):
        runtime = load_module("v58_runtime_available", SKILL / "scripts" / "ensure_windows_runtime.py")
        calls = []
        result = runtime.ensure_windows_runtime(
            importer=lambda: {"win32com": "ok", "pythoncom": "ok", "pywintypes": "ok"},
            installer=lambda command: calls.append(command),
            probe_com=False,
        )
        self.assertTrue(result["ok"])
        self.assertFalse(result["installed"])
        self.assertEqual([], calls)

    def test_runtime_uses_matching_offline_wheel_before_network(self):
        runtime = load_module("v58_runtime_offline", SKILL / "scripts" / "ensure_windows_runtime.py")
        attempts = {"count": 0}
        calls = []

        def importer():
            attempts["count"] += 1
            if attempts["count"] == 1:
                raise ModuleNotFoundError("win32com")
            return {"win32com": "ok", "pythoncom": "ok", "pywintypes": "ok"}

        with tempfile.TemporaryDirectory() as directory:
            wheel = Path(directory) / runtime.expected_wheel_name()
            wheel.write_bytes(b"wheel")
            result = runtime.ensure_windows_runtime(
                importer=importer,
                installer=lambda command: calls.append(command),
                wheel_dir=Path(directory),
                probe_com=False,
            )
        self.assertTrue(result["ok"])
        self.assertTrue(result["installed"])
        self.assertEqual(1, len(calls))
        self.assertIn(str(wheel), calls[0])


if __name__ == "__main__":
    unittest.main()
