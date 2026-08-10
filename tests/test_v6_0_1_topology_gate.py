from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BACKENDS = ("windows_com_v584", "mac_python_pptx_v2")


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def brief() -> dict:
    return {
        "schema_version": "6.0",
        "pipeline_revision": "6.0.0",
        "construction_mode": "deconstruct",
    }


def flow_case(observed_topology: str | None) -> tuple[dict, dict]:
    module = {
        "module_id": "M1",
        "module_kind": "flow",
        "contains_editable_text": True,
    }
    visual = {
        "visual_id": "V1",
        "element_id": "E1",
        "kind": "line",
        "treatment": "native",
        "source_px": [10, 10, 500, 300],
        "target_box_in": [0.2, 0.2, 5.0, 2.0],
        "rebuild_recipe": "line_arrow",
    }
    if observed_topology is not None:
        module["observed_topology"] = observed_topology
        visual["observed_topology"] = observed_topology
    specs = {
        "S01": {
            "elements": [
                {
                    "element_id": "E1",
                    "type": "flow",
                    "steps": [
                        {"title": "A", "body": "a"},
                        {"title": "B", "body": "b"},
                    ],
                }
            ]
        }
    }
    alignment = {
        "pages": {
            "S01": {
                "structure_modules": [module],
                "visuals": [visual],
                "text_decisions": [],
                "reconstruction_contract": {
                    "module_bindings": [
                        {"module_id": "M1", "element_ids": ["E1"]}
                    ]
                },
            }
        }
    }
    return specs, alignment


def card_collapse_case(observed_topology: str) -> tuple[dict, dict]:
    specs = {
        "S01": {
            "elements": [
                {
                    "element_id": "E1",
                    "type": "text_card",
                    "title": "A",
                    "body": "B",
                }
            ]
        }
    }
    alignment = {
        "pages": {
            "S01": {
                "structure_modules": [
                    {
                        "module_id": "M1",
                        "module_kind": "mixed",
                        "contains_editable_text": True,
                        "observed_topology": observed_topology,
                    }
                ],
                "visuals": [],
                "text_decisions": [],
                "reconstruction_contract": {
                    "module_bindings": [
                        {"module_id": "M1", "element_ids": ["E1"]}
                    ]
                },
            }
        }
    }
    return specs, alignment


class V601TopologyGateTests(unittest.TestCase):
    def setUp(self):
        self.subject = load_module(
            "v601_topology_gate", ROOT / "scripts" / "v6_deconstruction.py"
        )

    def test_non_flow_topologies_cannot_collapse_to_generic_flow(self):
        for topology in ("timeline", "cycle", "network"):
            specs, alignment = flow_case(topology)
            for backend in BACKENDS:
                with self.subTest(topology=topology, backend=backend):
                    report = self.subject.validate_deconstruction_prebuild(
                        brief(), specs, alignment, backend
                    )
                    self.assertIn(
                        "DECONSTRUCTION_TOPOLOGY_MISMATCH",
                        {item["code"] for item in report["blockers"]},
                    )

    def test_generic_flow_requires_an_explicit_observed_topology(self):
        specs, alignment = flow_case(None)
        for backend in BACKENDS:
            with self.subTest(backend=backend):
                report = self.subject.validate_deconstruction_prebuild(
                    brief(), specs, alignment, backend
                )
                self.assertIn(
                    "DECONSTRUCTION_TOPOLOGY_REQUIRED",
                    {item["code"] for item in report["blockers"]},
                )

    def test_connected_topologies_cannot_collapse_to_text_cards(self):
        for topology in ("timeline", "cycle", "network"):
            specs, alignment = card_collapse_case(topology)
            for backend in BACKENDS:
                with self.subTest(topology=topology, backend=backend):
                    report = self.subject.validate_deconstruction_prebuild(
                        brief(), specs, alignment, backend
                    )
                    self.assertIn(
                        "DECONSTRUCTION_TOPOLOGY_MISMATCH",
                        {item["code"] for item in report["blockers"]},
                    )

    def test_true_sequential_and_causal_flows_remain_supported(self):
        for topology in ("sequential_flow", "causal_flow"):
            specs, alignment = flow_case(topology)
            for backend in BACKENDS:
                with self.subTest(topology=topology, backend=backend):
                    report = self.subject.validate_deconstruction_prebuild(
                        brief(), specs, alignment, backend
                    )
                    self.assertTrue(report["ok"], report["blockers"])


if __name__ == "__main__":
    unittest.main()
