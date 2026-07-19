from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


SCHEMA_VERSION = "5.8"
SKILL_VERSION = "5.8.4"


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def _issue(code: str, message: str, slide_id: str, metrics: dict[str, Any]) -> dict[str, Any]:
    return {
        "code": code,
        "severity": "warning",
        "stage": "blueprint_alignment",
        "slide_id": slide_id,
        "message": message,
        "metrics": metrics,
    }


def _declared_data_labels(elements: list[dict[str, Any]]) -> int:
    count = 0
    for element in elements:
        if not isinstance(element, dict) or not element.get("show_data_labels"):
            continue
        data = element.get("data", [])
        if element.get("type") == "grouped_hbar_chart":
            series = element.get("series", [])
            width = len(series) or max(
                (len(item.get("values", [])) for item in data if isinstance(item, dict)),
                default=0,
            )
            count += len(data) * width
        else:
            count += len(data)
    return count


def audit_project(project_dir: str | Path) -> dict[str, Any]:
    project = Path(project_dir).resolve()
    brief = json.loads((project / "project_brief.json").read_text(encoding="utf-8"))
    schema_version = "5.9" if brief.get("schema_version") == "5.9" else SCHEMA_VERSION
    skill_version = "5.9.0" if schema_version == "5.9" else SKILL_VERSION
    build = project / ".build"
    alignment = json.loads((build / "blueprint_alignment.json").read_text(encoding="utf-8"))
    specs = json.loads((build / "page_specs.json").read_text(encoding="utf-8"))
    warnings: list[dict[str, Any]] = []
    pages: list[dict[str, Any]] = []
    for slide_id, aligned in alignment.get("pages", {}).items():
        elements = specs.get(slide_id, {}).get("elements", [])
        modules = aligned.get("structure_modules", [])
        expected_labels = sum(
            int(item.get("data_labels", 0))
            for item in modules
            if isinstance(item, dict)
        )
        declared_labels = _declared_data_labels(elements)
        visuals = aligned.get("visuals", [])
        treatments = {
            name: sum(
                1
                for item in visuals
                if isinstance(item, dict) and item.get("treatment") == name
            )
            for name in ("crop", "native", "omit")
        }
        paired_expected = any(
            isinstance(item, dict)
            and item.get("observed_expression") == "paired_hbar_columns"
            for item in modules
        )
        paired_declared = any(
            isinstance(item, dict)
            and item.get("type") == "grouped_hbar_chart"
            and item.get("layout") == "paired_columns"
            for item in elements
        )
        metrics = {
            "module_count": len(modules),
            "module_topology_match": not paired_expected or paired_declared,
            "expected_data_labels": expected_labels,
            "declared_data_labels": declared_labels,
            "observed_visuals": len(visuals),
            "treated_visuals": sum(treatments.values()),
            **{f"{key}_visuals": value for key, value in treatments.items()},
        }
        if paired_expected and not paired_declared:
            warnings.append(
                _issue(
                    "ALIGNMENT_TOPOLOGY_MISMATCH",
                    "resolved page spec does not preserve the reviewed paired-column chart",
                    str(slide_id),
                    metrics,
                )
            )
        if expected_labels and declared_labels < expected_labels:
            warnings.append(
                _issue(
                    "ALIGNMENT_DATA_LABEL_COVERAGE",
                    "resolved page spec declares fewer data labels than the reviewed blueprint",
                    str(slide_id),
                    metrics,
                )
            )
        pages.append({"slide_id": slide_id, **metrics})
    status = "pass_with_warnings" if warnings else "pass"
    report = {
        "schema_version": schema_version,
        "skill_version": skill_version,
        "status": status,
        "warnings": warnings,
        "blockers": [],
        "warning_count": len(warnings),
        "blocker_count": 0,
        "pages": pages,
    }
    _write_json(build / "blueprint_alignment_audit.json", report)
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description="Audit V5.8.4 blueprint alignment semantics.")
    parser.add_argument("project", type=Path)
    args = parser.parse_args()
    print(json.dumps(audit_project(args.project), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
