from __future__ import annotations

import re
from typing import Any, Iterable


SCHEMA_VERSION = "5.7"
SUPPORTED_SCHEMA_VERSIONS = {"5.6", "5.7"}
MANDATORY_CROP_KINDS = {
    "photo",
    "logo",
    "map",
    "pictogram",
    "compound_mark",
    "decorative_motif",
    "chemical_structure",
    "device",
    "product",
    "character",
}
NATIVE_KINDS = {"text", "rect", "line", "arrow", "oval", "chart", "table", "primitive"}
ALLOWED_REBUILD_RECIPES = {
    "text",
    "rect",
    "line",
    "arrow",
    "oval",
    "bar_chart",
    "column_chart",
    "donut_chart",
    "table",
    "circle_plus_text",
    "bars_plus_arrow",
}


def scan_text_integrity(text: str, *, location: str = "text") -> list[str]:
    errors: list[str] = []
    for match in re.finditer(r"\?{3,}", text):
        errors.append(f"{location}: question_mark_run at {match.start()} length={len(match.group(0))}")
    if "\ufffd" in text:
        errors.append(f"{location}: unicode_replacement_character")
    if re.search(r"[\x80-\x9f]", text):
        errors.append(f"{location}: c1_control_character")
    for token in ("锟斤拷", "ï¿½", "Ã¤", "Â·"):
        if token in text:
            errors.append(f"{location}: mojibake_token {token!r}")
    return errors


def iter_visible_strings(value: Any) -> Iterable[str]:
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for key, item in value.items():
            if isinstance(key, str):
                yield key
            yield from iter_visible_strings(item)
    elif isinstance(value, (list, tuple)):
        for item in value:
            yield from iter_visible_strings(item)


def validate_structured_text(value: Any, *, location: str) -> list[str]:
    errors: list[str] = []
    for index, text in enumerate(iter_visible_strings(value)):
        errors.extend(scan_text_integrity(text, location=f"{location}[{index}]"))
    return errors


def _valid_source_rect(value: Any) -> bool:
    return (
        isinstance(value, list)
        and len(value) == 4
        and all(isinstance(item, int) for item in value)
        and value[0] < value[2]
        and value[1] < value[3]
    )


def _valid_target_box(value: Any) -> bool:
    return (
        isinstance(value, list)
        and len(value) == 4
        and all(isinstance(item, (int, float)) for item in value)
        and value[2] > 0
        and value[3] > 0
    )


def validate_visual_manifest(manifest: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if manifest.get("schema_version") not in SUPPORTED_SCHEMA_VERSIONS:
        errors.append(f"visual manifest schema_version must be one of {sorted(SUPPORTED_SCHEMA_VERSIONS)}")
    pages = manifest.get("pages")
    if not isinstance(pages, dict) or not pages:
        return errors + ["visual manifest pages must be a non-empty mapping"]
    asset_ids: set[str] = set()
    for slide_id, page in pages.items():
        prefix = str(slide_id)
        if not isinstance(page, dict):
            errors.append(f"{prefix}: visual page record must be a mapping")
            continue
        blueprint_hash = page.get("blueprint_sha256")
        if not isinstance(blueprint_hash, str) or not re.fullmatch(r"[0-9a-f]{64}", blueprint_hash):
            errors.append(f"{prefix}: blueprint_sha256 must be 64 lowercase hex characters")
        candidates = page.get("candidate_count")
        if not isinstance(candidates, int) or candidates < 0:
            errors.append(f"{prefix}: candidate_count must be a non-negative integer")
            candidates = 0
        visuals = page.get("visuals")
        if not isinstance(visuals, list):
            errors.append(f"{prefix}: visuals must be a list")
            continue
        crop_count = 0
        for index, visual in enumerate(visuals):
            label = f"{prefix}/visual[{index}]"
            if not isinstance(visual, dict):
                errors.append(f"{label}: visual must be a mapping")
                continue
            kind = visual.get("kind")
            disposition = visual.get("disposition")
            if kind in MANDATORY_CROP_KINDS and disposition != "crop":
                errors.append(f"{label}: {kind} must use crop")
            if disposition == "crop":
                crop_count += 1
                asset_id = visual.get("asset_id")
                if not isinstance(asset_id, str) or not asset_id:
                    errors.append(f"{label}: crop requires asset_id")
                elif asset_id in asset_ids:
                    errors.append(f"{label}: duplicate asset_id {asset_id}")
                else:
                    asset_ids.add(asset_id)
                if not _valid_source_rect(visual.get("source_px")):
                    errors.append(f"{label}: crop requires a valid source_px rectangle")
                if not _valid_target_box(visual.get("target_box_in")):
                    errors.append(f"{label}: crop requires a valid target_box_in")
            elif disposition == "native_rebuild":
                if kind not in NATIVE_KINDS:
                    errors.append(f"{label}: unsupported native kind {kind!r}")
                if visual.get("rebuild_recipe") not in ALLOWED_REBUILD_RECIPES:
                    errors.append(f"{label}: native_rebuild requires an allowed rebuild_recipe")
            else:
                errors.append(f"{label}: disposition must be crop or native_rebuild")
        if candidates > 0 and crop_count == 0:
            errors.append(f"{prefix}: candidate_count={candidates} forbids a zero-asset review")
        if candidates < crop_count:
            errors.append(f"{prefix}: candidate_count cannot be smaller than crop count")
    errors.extend(validate_structured_text(manifest, location="visual_manifest"))
    return errors


def visual_page_to_slide_fields(page: dict[str, Any]) -> dict[str, Any]:
    visuals = list(page.get("visuals", []))
    crops = [visual for visual in visuals if visual.get("disposition") == "crop"]
    return {
        "visual_review": "extract_declared" if crops else "reviewed_no_raster",
        "visual_review_evidence": {
            "blueprint_sha256": page["blueprint_sha256"],
            "full_page_reviewed": True,
            "checked_classes": ["photo", "logo", "map", "pictogram", "decorative_motif"],
            "decision_reason": "The manifest gate resolved every visual candidate before compilation.",
        },
        "visual_inventory": [
            {
                key: visual[key]
                for key in ("visual_id", "kind", "description", "disposition", "asset_id", "rebuild_recipe")
                if key in visual
            }
            for visual in visuals
        ],
        "complex_visuals": [
            {"asset_id": visual["asset_id"], "kind": visual["kind"], "description": visual.get("description", "")}
            for visual in crops
        ],
    }


def validate_blueprint_visual_balance(
    page_specs: dict[str, Any],
    manifest: dict[str, Any],
    *,
    body_box: tuple[float, float, float, float] = (0.72, 2.90, 12.00, 3.80),
) -> list[str]:
    """Enforce the V5.7 analytical-canvas recipe without imposing an image quota.

    Supporting raster accents are optional. When present, they must stay inside
    a compact 6-12% body-area band and no single accent may become a hero image.
    """

    if manifest.get("schema_version") != "5.7":
        return []
    errors: list[str] = []
    analytical_types = {
        "hbar_chart",
        "bar_chart",
        "column_chart",
        "line_chart",
        "table",
        "matrix",
        "flow",
        "text_card",
        "metric_strip",
        "process",
    }
    body_area = float(body_box[2] * body_box[3])
    for slide_id, page in manifest.get("pages", {}).items():
        spec = page_specs.get(slide_id, {}) if isinstance(page_specs, dict) else {}
        elements = spec.get("elements", []) if isinstance(spec, dict) else []
        if not any(isinstance(item, dict) and item.get("type") in analytical_types for item in elements):
            errors.append(f"{slide_id}: analytical canvas requires at least one chart, table, matrix, flow, card, or metric strip")
        accent_ids = {
            item.get("asset_id")
            for item in page.get("visuals", [])
            if isinstance(item, dict)
            and item.get("disposition") == "crop"
            and item.get("role", "supporting_accent") == "supporting_accent"
            and item.get("asset_id")
        }
        accent_area = 0.0
        for element in elements:
            if not isinstance(element, dict) or element.get("asset_id") not in accent_ids:
                continue
            box = element.get("box")
            if not _valid_target_box(box):
                continue
            width, height = float(box[2]), float(box[3])
            accent_area += width * height
            if width > 1.40 or height > 1.40:
                errors.append(f"{slide_id}/{element.get('asset_id')}: supporting accent must remain inside a reserved icon lane")
        if accent_area:
            ratio = accent_area / body_area
            if ratio < 0.06 or ratio > 0.12:
                errors.append(
                    f"{slide_id}: supporting accents must occupy 6-12% of the body area; got {ratio:.1%}"
                )
    return errors
