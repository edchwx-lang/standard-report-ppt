from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path

from PIL import ImageFont


SKILL = Path(__file__).resolve().parents[1]


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class V59MacMetricsTests(unittest.TestCase):
    def setUp(self):
        self.metrics = load_module("v59_mac_metrics", SKILL / "scripts" / "mac_text_metrics.py")
        candidates = [
            Path("C:/Windows/Fonts/arial.ttf"),
            Path("/System/Library/Fonts/Supplemental/Arial.ttf"),
            Path("/Library/Fonts/Arial.ttf"),
        ]
        self.font_path = next(path for path in candidates if path.is_file())
        ImageFont.truetype(str(self.font_path), 20)

    def test_mixed_text_wraps_deterministically(self):
        kwargs = dict(font_path=self.font_path, font_size_pt=12, max_width_pt=120)
        first = self.metrics.wrap_text("蓝图 Blueprint 2026 必须先于平台后端", **kwargs)
        self.assertEqual(first, self.metrics.wrap_text("蓝图 Blueprint 2026 必须先于平台后端", **kwargs))
        self.assertGreater(len(first), 1)

    def test_allocated_height_includes_safety_margin(self):
        result = self.metrics.measure_text_box(
            "第一行\n第二行", font_path=self.font_path, resolved_font_name="DejaVu Sans",
            font_size_pt=12, max_width_pt=160, safety_margin_ratio=1.10,
        )
        self.assertEqual("pillow_font_metrics", result.measurement_backend)
        self.assertGreater(result.allocated_height_pt, result.predicted_height_pt)

    def test_font_policy_uses_declared_order(self):
        resolved = self.metrics.resolve_font(
            ["Microsoft YaHei", "PingFang SC", "Noto Sans CJK SC"],
            catalog={"PingFang SC": (self.font_path, 0)},
        )
        self.assertEqual("PingFang SC", resolved.name)
        self.assertTrue(resolved.fallback_used)
