from __future__ import annotations

import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


CASES = (
    "tests.test_v63_deconstruction.V63DeconstructionTests.test_full_windows_pipeline_uses_v63_acceptance_and_runtime_revision",
    "tests.test_v63_windows_scene_renderer.V63WindowsSceneRendererTests.test_real_powerpoint_build_preserves_placeholders_and_adds_editable_atoms",
    "tests.test_v63_mac_scene_compile.V63MacSceneCompileTests.test_mac_compiler_builds_shared_atoms_and_preserves_five_placeholders",
    "tests.test_v63_acceptance",
    "tests.test_v63_boundary",
)


def main() -> int:
    suite = unittest.TestLoader().loadTestsFromNames(CASES)
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    sys.exit(main())
