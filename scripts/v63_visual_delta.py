from __future__ import annotations

import json
from pathlib import Path
from typing import Any


SCHEMA_VERSION = "6.3"
RUNTIME_REVISION = "6.3.1"


def _warning(page: dict[str, Any]) -> dict[str, Any]:
    return {
        "code": "V63_VISUAL_DELTA",
        "severity": "warning",
        "stage": "v63_visual_delta",
        "slide_id": str(page.get("slide_id", "")),
        "message": "rendered body differs materially from the locked blueprint benchmark",
        "metrics": {
            key: page.get(key)
            for key in ("score", "layout_score", "ink_mass_ratio")
            if page.get(key) is not None
        },
    }


def evaluate_visual_delta(
    *,
    build_attempt: int,
    structural_ok: bool,
    fidelity_report: dict[str, Any] | None,
    visual_review: dict[str, Any] | None = None,
    require_visual_review: bool = False,
) -> dict[str, Any]:
    if build_attempt not in {1, 2}:
        raise ValueError("V63_REFINEMENT_ATTEMPT_INVALID")
    report = fidelity_report if isinstance(fidelity_report, dict) else {}
    failed_ids = {
        str(item) for item in report.get("failed_slide_ids", []) if str(item)
    }
    warnings = [
        _warning(page)
        for page in report.get("pages", [])
        if isinstance(page, dict)
        and (
            page.get("passed") is False
            or str(page.get("slide_id", "")) in failed_ids
        )
    ]
    if failed_ids and not warnings:
        warnings = [
            _warning({"slide_id": slide_id}) for slide_id in sorted(failed_ids)
        ]
    fidelity_passed = report.get("passed") is True
    visual_findings = []
    if isinstance(visual_review, dict):
        visual_findings = [dict(finding, slide_id=page.get('slide_id', ''))
                           for page in visual_review.get('pages', [])
                           for finding in page.get('differences', [])]
        warnings = visual_findings
    material = any(item.get('severity') in {'material', 'blocker'} for item in visual_findings)
    if not structural_ok:
        action = "block"
    elif require_visual_review and (not isinstance(visual_review, dict) or visual_review.get('reviewed') is not True):
        action = 'awaiting_visual_review'
    elif isinstance(visual_review, dict):
        if any(item.get('severity') == 'blocker' for item in visual_findings):
            action = 'targeted_refinement' if build_attempt == 1 else 'block'
        elif material:
            action = 'targeted_refinement' if build_attempt == 1 else 'deliver_with_warnings'
        else:
            action = 'deliver_with_warnings' if warnings else 'deliver'
    elif fidelity_passed:
        action = "deliver"
    elif build_attempt == 1:
        action = "targeted_refinement"
    else:
        action = "deliver_with_warnings"
    return {
        "schema_version": SCHEMA_VERSION,
        "deconstruction_runtime_revision": RUNTIME_REVISION,
        "build_attempt": build_attempt,
        "structural_ok": bool(structural_ok),
        "fidelity_passed": fidelity_passed,
        "visual_acceptance_passed": isinstance(visual_review, dict) and visual_review.get('reviewed') is True and not material,
        "action": action,
        "refinement_allowed": action == "targeted_refinement",
        "delivery_blocked": action == "block",
        "warnings": warnings,
    }


def write_visual_delta(project_dir: str | Path, value: dict[str, Any]) -> Path:
    project = Path(project_dir).resolve()
    path = project / ".build" / "v63_visual_delta.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    temporary.replace(path)
    return path
