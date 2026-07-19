from __future__ import annotations

import importlib.util
import re
from pathlib import Path
from typing import Any


ALLOWED_ELEMENT_TYPES = {
    "section_header",
    "text",
    "rect",
    "oval",
    "line",
    "arrow",
    "text_card",
    "metric_strip",
    "hbar_chart",
    "column_chart",
    "line_chart",
    "combo_chart",
    "donut_chart",
    "grouped_hbar_chart",
    "flow",
    "matrix",
    "asset",
}
CHART_TYPES = {
    "hbar_chart",
    "column_chart",
    "line_chart",
    "combo_chart",
    "donut_chart",
    "grouped_hbar_chart",
}
COLOR_FIELDS = {"fill", "color", "line", "title_fill", "body_fill", "line_color"}


def _load_policy():
    path = Path(__file__).with_name("v58_visual_policy.py")
    spec = importlib.util.spec_from_file_location("standard_report_v58_prebuild_policy", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _load_quality():
    path = Path(__file__).with_name("v582_quality.py")
    spec = importlib.util.spec_from_file_location("standard_report_v582_prebuild_quality", path)
    if spec is None or spec.loader is None:
        raise ImportError(f"could not load V5.8.2 quality policy from {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _valid_color(value: Any) -> bool:
    return (
        isinstance(value, int)
        and 0 <= value <= 0xFFFFFF
        or isinstance(value, str)
        and re.fullmatch(r"#[0-9A-Fa-f]{6}", value) is not None
    )


def _validate_nested_colors(value: Any, location: str) -> list[str]:
    errors: list[str] = []
    if isinstance(value, dict):
        for key, item in value.items():
            child = f"{location}/{key}"
            if key in COLOR_FIELDS and item is not None and not _valid_color(item):
                errors.append(f"{child}: invalid color {item!r}")
            errors.extend(_validate_nested_colors(item, child))
    elif isinstance(value, list):
        for index, item in enumerate(value):
            errors.extend(_validate_nested_colors(item, f"{location}[{index}]"))
    return errors


def _validate_box(element: dict[str, Any], location: str) -> list[str]:
    box = element.get("box")
    if not isinstance(box, list) or len(box) != 4 or not all(isinstance(item, (int, float)) for item in box):
        return [f"{location}: box must contain four numeric values"]
    x, y, width, height = (float(item) for item in box)
    errors: list[str] = []
    if width <= 0 or height <= 0:
        errors.append(f"{location}: box width and height must be positive")
    if element.get("coord_space", "body") == "body" and (
        x < 0 or y < 0 or x + width > 12.25 or y + height > 4.50
    ):
        errors.append(f"{location}: body-relative box exceeds the V5.8 safe area")
    return errors


def _validate_chart(element: dict[str, Any], location: str) -> list[str]:
    data = element.get("data")
    if not isinstance(data, list) or not data:
        return [f"{location}: chart data must be a non-empty list"]
    errors: list[str] = []
    if element.get("type") == "grouped_hbar_chart":
        for index, item in enumerate(data):
            values = item.get("values") if isinstance(item, dict) else None
            if not isinstance(values, list) or not all(isinstance(value, (int, float)) for value in values):
                errors.append(f"{location}/data[{index}]: grouped values must be a numeric list")
        return errors
    total = 0.0
    for index, item in enumerate(data):
        value = item.get("value") if isinstance(item, dict) else None
        if not isinstance(value, (int, float)):
            errors.append(f"{location}/data[{index}]: chart value must be numeric")
            continue
        total += float(value)
        if element.get("type") == "combo_chart" and item.get("line_value") is not None and not isinstance(
            item.get("line_value"), (int, float)
        ):
            errors.append(f"{location}/data[{index}]: combo line_value must be numeric")
    if element.get("type") == "donut_chart" and total <= 0:
        errors.append(f"{location}: donut values must sum to a positive number")
    return errors


def _validate_flow(element: dict[str, Any], location: str) -> list[str]:
    steps = element.get("steps")
    if not isinstance(steps, list):
        return [f"{location}: flow steps must be a list"]
    errors: list[str] = []
    for index, step in enumerate(steps):
        if not isinstance(step, dict):
            errors.append(f"{location}/steps[{index}]: flow stage must be a mapping")
    return errors


def _validate_runtime_fields(element: dict[str, Any], location: str) -> list[str]:
    kind = element.get("type")
    errors: list[str] = []
    if kind == "asset" and (not isinstance(element.get("asset_id"), str) or not element.get("asset_id")):
        errors.append(f"{location}: asset element requires a non-empty asset_id")
    if kind == "matrix":
        headers = element.get("headers")
        rows = element.get("rows")
        if not isinstance(headers, list):
            errors.append(f"{location}: matrix headers must be a list")
        if not isinstance(rows, list) or any(not isinstance(row, list) for row in rows):
            errors.append(f"{location}: matrix rows must be a list of lists")
    if kind == "metric_strip":
        metrics = element.get("metrics")
        if not isinstance(metrics, list) or any(not isinstance(metric, dict) for metric in metrics):
            errors.append(f"{location}: metric_strip metrics must be a list of mappings")
    return errors


def _semantic_advisories(element: dict[str, Any], location: str) -> list[str]:
    warnings: list[str] = []
    if element.get("type") == "flow":
        steps = element.get("steps")
        if isinstance(steps, list):
            if not 2 <= len(steps) <= 6:
                warnings.append(f"{location}: flow steps normally contain two to six stages")
            for index, step in enumerate(steps):
                if isinstance(step, dict) and not str(step.get("title", "")).strip():
                    warnings.append(f"{location}/steps[{index}]: flow stage has no title")
    if element.get("type") == "grouped_hbar_chart":
        for index, item in enumerate(element.get("data", [])):
            values = item.get("values") if isinstance(item, dict) else None
            if isinstance(values, list) and not 1 <= len(values) <= 2:
                warnings.append(
                    f"{location}/data[{index}]: grouped chart normally uses one or two series; runtime will simplify"
                )
    return warnings


def _validate_core_points(points: Any) -> list[str]:
    if not isinstance(points, list):
        return ["core_points must be a list"]
    errors: list[str] = []
    if not 1 <= len(points) <= 2:
        errors.append("core_points must contain one or two points")
    if any(not isinstance(point, str) or not point.strip() for point in points):
        errors.append("every core point must be a non-empty string")
    total = sum(len(re.sub(r"\s+", "", point)) for point in points if isinstance(point, str))
    if not 80 <= total <= 160:
        errors.append(f"core_points must total 80-160 non-whitespace characters; got {total}")
    return errors


def _intersection_ratio(first: dict[str, Any], second: dict[str, Any]) -> float:
    first_box = first.get("box")
    second_box = second.get("box")
    if (
        not isinstance(first_box, list)
        or len(first_box) != 4
        or not isinstance(second_box, list)
        or len(second_box) != 4
    ):
        return 0.0
    try:
        ax, ay, aw, ah = (float(value) for value in first_box)
        bx, by, bw, bh = (float(value) for value in second_box)
    except (TypeError, ValueError):
        return 0.0
    overlap_width = max(0.0, min(ax + aw, bx + bw) - max(ax, bx))
    overlap_height = max(0.0, min(ay + ah, by + bh) - max(ay, by))
    overlap = overlap_width * overlap_height
    minimum_area = min(max(0.0, aw * ah), max(0.0, bw * bh))
    return overlap / minimum_area if minimum_area > 0 else 0.0


def diagnose_layout(page_specs: dict[str, Any]) -> dict[str, Any]:
    quality = _load_quality()
    warnings: list[dict[str, Any]] = []
    content_types = {
        "asset",
        "text",
        "text_card",
        "metric_strip",
        "hbar_chart",
        "column_chart",
        "line_chart",
        "combo_chart",
        "donut_chart",
        "grouped_hbar_chart",
        "flow",
        "matrix",
    }
    for slide_id, page_spec in page_specs.items():
        if not isinstance(page_spec, dict):
            continue
        elements = [
            (index, element)
            for index, element in enumerate(page_spec.get("elements", []))
            if isinstance(element, dict) and element.get("type") in content_types
        ]
        for position, (first_index, first) in enumerate(elements):
            for second_index, second in elements[position + 1:]:
                if first.get("allow_overlap") is True or second.get("allow_overlap") is True:
                    continue
                kinds = {str(first.get("type")), str(second.get("type"))}
                if "asset" not in kinds and "text" not in kinds:
                    continue
                ratio = _intersection_ratio(first, second)
                if ratio >= 0.10:
                    warnings.append(
                        quality.issue(
                            "LAYOUT_OVERLAP",
                            "warning",
                            "layout_precheck",
                            f"element[{first_index}] and element[{second_index}] overlap {ratio:.0%}; "
                            "set allow_overlap=true only when intentional",
                            str(slide_id),
                            {
                                "first_index": first_index,
                                "second_index": second_index,
                                "overlap_ratio": round(ratio, 4),
                            },
                        )
                    )
        for index, element in elements:
            if element.get("type") not in {"text", "text_card"}:
                continue
            box = element.get("box")
            if not isinstance(box, list) or len(box) != 4:
                continue
            text = " ".join(
                str(element.get(field, ""))
                for field in ("text", "title", "body")
                if element.get(field)
            )
            if not text:
                continue
            try:
                capacity = max(1.0, float(box[2]) * float(box[3]) * 42.0)
            except (TypeError, ValueError):
                continue
            if len(re.sub(r"\s+", "", text)) > capacity * 1.6:
                warnings.append(
                    quality.issue(
                        "LAYOUT_TEXT_CAPACITY",
                        "warning",
                        "layout_precheck",
                        f"element[{index}] text substantially exceeds its estimated box capacity",
                        str(slide_id),
                        {
                            "characters": len(re.sub(r"\s+", "", text)),
                            "estimated_capacity": round(capacity),
                        },
                    )
                )
    return quality.summarize(warnings, [])


def _validate_evidence_inventory(slide: dict[str, Any]) -> list[str]:
    slide_id = str(slide.get("slide_id", "?"))
    modules = slide.get("modules")
    if not isinstance(modules, list) or not modules:
        return [f"{slide_id}: modules must exist before evidence mapping"]
    module_ids = {
        module.get("module_id")
        for module in modules
        if isinstance(module, dict) and isinstance(module.get("module_id"), str)
    }
    errors: list[str] = []
    if slide.get("primary_visual_module_id") not in module_ids:
        errors.append(f"{slide_id}: primary_visual_module_id must reference a real module")
    inventory = slide.get("evidence_inventory")
    if not isinstance(inventory, list) or not inventory:
        errors.append(f"{slide_id}: evidence_inventory must be a non-empty source-evidence list")
        return errors
    seen: set[str] = set()
    high_priority = 0
    mapped_high_priority = 0
    for item in inventory:
        if not isinstance(item, dict):
            errors.append(f"{slide_id}: every evidence_inventory item must be a mapping")
            continue
        evidence_id = item.get("evidence_id")
        if not isinstance(evidence_id, str) or not evidence_id.strip():
            errors.append(f"{slide_id}: every evidence item requires evidence_id")
        elif evidence_id in seen:
            errors.append(f"{slide_id}: duplicate evidence_id {evidence_id}")
        else:
            seen.add(evidence_id)
        if not isinstance(item.get("statement"), str) or not item["statement"].strip():
            errors.append(f"{slide_id}/{evidence_id or '?'}: evidence statement is required")
        priority = item.get("priority")
        if priority not in {"must_keep", "supporting", "optional"}:
            errors.append(f"{slide_id}/{evidence_id or '?'}: invalid evidence priority")
            continue
        module_id = item.get("module_id")
        if module_id is not None and module_id not in module_ids:
            errors.append(f"{slide_id}/{evidence_id or '?'}: module_id does not reference a real module")
        if priority in {"must_keep", "supporting"}:
            high_priority += 1
            if module_id in module_ids:
                mapped_high_priority += 1
        if priority == "must_keep" and module_id not in module_ids:
            errors.append(f"{slide_id}/{evidence_id or '?'}: must_keep evidence must map to a real module")
    if high_priority and mapped_high_priority / high_priority < 0.80:
        errors.append(
            f"{slide_id}: mapped must_keep/supporting evidence coverage must be at least 80%; "
            f"got {mapped_high_priority}/{high_priority}"
        )
    return errors


def diagnose_project_specs(
    brief: dict[str, Any],
    slides: list[dict[str, Any]],
    page_specs: dict[str, Any],
    visual_manifest: dict[str, Any] | None = None,
) -> dict[str, Any]:
    quality = _load_quality()
    if not isinstance(brief, dict):
        blocker = quality.issue(
            "PROJECT_BRIEF_STRUCTURE",
            "blocker",
            "prebuild",
            "project brief must be a mapping",
        )
        return quality.summarize([], [blocker])
    if brief.get("schema_version") not in {"5.8", "5.9"}:
        return quality.summarize([], [])
    blockers: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []

    def add_blocker(code: str, message: str, slide_id: str | None = None) -> None:
        blockers.append(quality.issue(code, "blocker", "prebuild", message, slide_id))

    def add_warning(code: str, message: str, slide_id: str | None = None) -> None:
        warnings.append(quality.issue(code, "warning", "prebuild", message, slide_id))

    count = brief.get("requested_page_count")
    if not isinstance(count, int) or isinstance(count, bool) or count <= 0:
        add_blocker("PROJECT_PAGE_COUNT", "requested_page_count must be a positive integer")
        expected_ids: list[str] = []
    else:
        expected_ids = [f"S{index:02d}" for index in range(1, count + 1)]
    if not isinstance(slides, list):
        add_blocker("SLIDES_STRUCTURE", "slides must be a list")
        slides = []
    slide_ids = [slide.get("slide_id") if isinstance(slide, dict) else None for slide in slides]
    if slide_ids != expected_ids:
        add_blocker("SLIDE_COVERAGE", f"slides must cover {expected_ids} in canonical order")
    if not isinstance(page_specs, dict):
        add_blocker("PAGE_SPECS_STRUCTURE", "page_specs must be a mapping")
        page_specs = {}
    if sorted(str(key) for key in page_specs) != expected_ids:
        add_blocker("PAGE_SPEC_COVERAGE", f"page_specs must cover {expected_ids}")
    if brief.get("production_mode") == "blueprint":
        manifest_pages = visual_manifest.get("pages") if isinstance(visual_manifest, dict) else None
        if not isinstance(manifest_pages, dict) or sorted(str(key) for key in manifest_pages) != expected_ids:
            actual_ids = sorted(str(key) for key in manifest_pages) if isinstance(manifest_pages, dict) else []
            add_blocker(
                "VISUAL_PAGE_COVERAGE",
                f"visual_manifest pages must cover {expected_ids}; got {actual_ids}",
            )
    for slide_id in expected_ids:
        page_spec = page_specs.get(slide_id, {})
        if not isinstance(page_spec, dict):
            add_blocker("PAGE_SPEC_STRUCTURE", "page spec must be a mapping", slide_id)
            continue
        elements = page_spec.get("elements") if isinstance(page_spec, dict) else None
        if not isinstance(elements, list) or not elements:
            add_blocker("ELEMENTS_STRUCTURE", "page spec elements must be a non-empty list", slide_id)
            continue
        for index, element in enumerate(elements):
            location = f"{slide_id}/element[{index}]"
            if not isinstance(element, dict):
                add_blocker("ELEMENT_STRUCTURE", f"{location}: element must be a mapping", slide_id)
                continue
            kind = element.get("type")
            if kind not in ALLOWED_ELEMENT_TYPES:
                add_blocker("ELEMENT_TYPE", f"{location}: unsupported type {kind!r}", slide_id)
            for message in _validate_box(element, location):
                add_blocker("ELEMENT_COORDINATES", message, slide_id)
            for message in _validate_nested_colors(element, location):
                add_blocker("ELEMENT_COLOR", message, slide_id)
            for message in _validate_runtime_fields(element, location):
                add_blocker("ELEMENT_DATA", message, slide_id)
            if kind in CHART_TYPES:
                for message in _validate_chart(element, location):
                    add_blocker("ELEMENT_DATA", message, slide_id)
            if kind == "flow":
                for message in _validate_flow(element, location):
                    add_blocker("ELEMENT_DATA", message, slide_id)
            for message in _semantic_advisories(element, location):
                add_warning("VISUAL_ROUTE", message, slide_id)
    policy = _load_policy()
    for slide in slides:
        if not isinstance(slide, dict):
            add_blocker("SLIDE_STRUCTURE", "slide record must be a mapping")
            continue
        slide_id = str(slide.get("slide_id", "?"))
        for field in ("chapter", "title", "source"):
            if not isinstance(slide.get(field), str):
                add_blocker(
                    "SLIDE_TEXT_STRUCTURE",
                    f"{slide_id}: {field} must be a string for the PowerPoint runtime",
                    slide_id,
                )
        core_points = slide.get("core_points")
        core_structure_ok = isinstance(core_points, list) and all(
            isinstance(point, str) for point in core_points
        )
        if not core_structure_ok:
            add_blocker(
                "SLIDE_TEXT_STRUCTURE",
                f"{slide_id}: core_points must be a list of strings for the PowerPoint runtime",
                slide_id,
            )
        page_spec = page_specs.get(slide_id, {})
        for message in policy.validate_visual_route(slide, page_spec):
            add_warning("VISUAL_ROUTE", message, slide_id)
        for message in policy.validate_density(slide, page_spec):
            add_warning("BODY_DENSITY", message, slide_id)
        manifest_pages = (visual_manifest or {}).get("pages", {}) if isinstance(visual_manifest, dict) else {}
        manifest_page = manifest_pages.get(slide_id, {}) if isinstance(manifest_pages, dict) else {}
        for message in policy.validate_palette_and_visuals(page_spec, manifest_page):
            add_warning("VISUAL_PALETTE", message, slide_id)
        for message in _validate_evidence_inventory(slide):
            add_warning("EVIDENCE_COVERAGE", message, slide_id)
        if core_structure_ok:
            for message in _validate_core_points(core_points):
                add_warning("CORE_LENGTH", f"{slide_id}: {message}", slide_id)
    if brief.get("pipeline_revision") in {"5.8.3", "5.8.4"}:
        layout = diagnose_layout(page_specs)
        warnings.extend(layout["warnings"])
    return quality.summarize(warnings, blockers)


def validate_project_specs(
    brief: dict[str, Any],
    slides: list[dict[str, Any]],
    page_specs: dict[str, Any],
    visual_manifest: dict[str, Any] | None = None,
) -> list[str]:
    diagnostics = diagnose_project_specs(brief, slides, page_specs, visual_manifest)
    return [str(item["message"]) for item in diagnostics["blockers"]]
