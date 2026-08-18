from __future__ import annotations

import importlib.util
import json
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class V62BitmapAcceptanceTests(unittest.TestCase):
    def setUp(self):
        self.release = load_module(
            "v62_bitmap_acceptance",
            ROOT / "scripts" / "v62_bitmap_acceptance.py",
        )

    def test_first_structurally_valid_pptx_is_hash_locked(self):
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory)
            pptx = project / "output" / "deck.pptx"
            pptx.parent.mkdir()
            pptx.write_bytes(b"valid deck")
            payload = self.release.write_acceptance(
                project,
                pptx,
                bitmap_audit={"ok": True, "blockers": []},
                build_attempt=1,
            )
            self.assertTrue(payload["build_locked"])
            self.assertEqual("accept", payload["decision"])
            self.assertEqual("manual_only", payload["minor_crop_adjustment"])
            self.assertIsNotNone(self.release.locked_acceptance(project, pptx))

    def test_minor_crop_feedback_never_authorizes_an_automatic_rebuild(self):
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory)
            pptx = project / "deck.pptx"
            pptx.write_bytes(b"valid deck")
            self.release.write_acceptance(
                project,
                pptx,
                bitmap_audit={"ok": True, "blockers": []},
                build_attempt=1,
            )
            self.assertFalse(
                self.release.rebuild_allowed(
                    project,
                    catastrophic_repair=False,
                    reason="minor_crop_visual_gain",
                )
            )
            self.assertFalse(
                self.release.rebuild_allowed(
                    project,
                    catastrophic_repair=True,
                    reason="minor_crop_visual_gain",
                )
            )

    def test_only_one_catastrophic_repair_is_authorized(self):
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory)
            failure = {
                "schema_version": "6.2",
                "construction_mode": "bitmap",
                "decision": "catastrophic_repair_required",
                "build_locked": False,
                "build_attempt": 1,
                "catastrophic_blockers": [{"code": "BITMAP_PPTX_INVALID"}],
            }
            path = project / ".build" / "bitmap_acceptance.json"
            path.parent.mkdir()
            path.write_text(json.dumps(failure), encoding="utf-8")
            self.assertTrue(
                self.release.rebuild_allowed(
                    project,
                    catastrophic_repair=True,
                    reason="BITMAP_PPTX_INVALID",
                )
            )
            failure["build_attempt"] = 2
            path.write_text(json.dumps(failure), encoding="utf-8")
            self.assertFalse(
                self.release.rebuild_allowed(
                    project,
                    catastrophic_repair=True,
                    reason="BITMAP_PPTX_INVALID",
                )
            )


if __name__ == "__main__":
    unittest.main()
