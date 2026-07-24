from __future__ import annotations

import hashlib
import zipfile
from pathlib import Path
from typing import Any
from xml.etree import ElementTree


SCHEMA_VERSION = "6.0"
DECONSTRUCTION_EDITABILITY_FAILED = "DECONSTRUCTION_EDITABILITY_FAILED"
BITMAP_CONTRACT_INVALID = "BITMAP_CONTRACT_INVALID"
_EMU_PER_INCH = 914400.0
_TOLERANCE_IN = 0.02
_ASPECT_TOLERANCE = 0.02
_CHART_TYPES = {"hbar_chart", "column_chart", "line_chart", "combo_chart", "donut_chart", "grouped_hbar_chart"}
_SKELETON_NAMES = {"SKEL_CHAPTER", "SKEL_TITLE", "SKEL_CORE", "SKEL_SOURCE", "SKEL_PAGE_NUMBER"}


def _pages(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        return {}
    nested = value.get("pages")
    return nested if isinstance(nested, dict) else value


def _issue(code: str, slide_id: str, message: str) -> dict[str, Any]:
    return {"code": code, "severity": "blocker", "stage": "pptx_editability", "slide_id": slide_id, "message": message}


def _shape_box(shape) -> tuple[float, float, float, float]:
    return tuple(float(value) / _EMU_PER_INCH for value in (shape.left, shape.top, shape.width, shape.height))


def _runtime_body(slide, presentation) -> tuple[float, float, float, float]:
    core_bottom = 0.0
    source_top = float(presentation.slide_height) / _EMU_PER_INCH
    for shape in slide.shapes:
        if shape.name == "SKEL_CORE":
            core_bottom = (float(shape.top) + float(shape.height)) / _EMU_PER_INCH
        elif shape.name == "SKEL_SOURCE":
            source_top = float(shape.top) / _EMU_PER_INCH
    return (0.0, core_bottom, float(presentation.slide_width) / _EMU_PER_INCH, max(0.0, source_top - core_bottom))


def _overlap_area(a: tuple[float, float, float, float], b: tuple[float, float, float, float]) -> float:
    left, top = max(a[0], b[0]), max(a[1], b[1])
    right, bottom = min(a[0] + a[2], b[0] + b[2]), min(a[1] + a[3], b[1] + b[3])
    return max(0.0, right - left) * max(0.0, bottom - top)


def _slide_xml_text(pptx_path: str | Path) -> dict[str, list[str]]:
    values: dict[str, list[str]] = {}
    with zipfile.ZipFile(pptx_path) as archive:
        for name in archive.namelist():
            if name.startswith("ppt/slides/slide") and name.endswith(".xml"):
                try:
                    root = ElementTree.fromstring(archive.read(name))
                except ElementTree.ParseError:
                    continue
                slide_name = Path(name).stem
                try:
                    slide_index = int(slide_name.removeprefix("slide"))
                except ValueError:
                    continue
                values[f"S{slide_index:02d}"] = [node.text or "" for node in root.iter() if node.tag.endswith("}t")]
    return values


def _selected_text(page: dict[str, Any]) -> list[str]:
    contract = page.get("reconstruction_contract") if isinstance(page.get("reconstruction_contract"), dict) else {}
    decisions = contract.get("text_decisions", []) if isinstance(contract.get("text_decisions"), list) else []
    return [item["selected"] for item in decisions if isinstance(item, dict) and isinstance(item.get("selected"), str) and item["selected"].strip()]


def _contains_text(xml_text: list[str], expected: str) -> bool:
    return expected in "".join(xml_text)


def audit_deconstruction_pptx(pptx_path: str | Path, page_specs: dict[str, Any], alignment: dict[str, Any], allowed_large_visual_asset_ids: list[str] | None = None) -> dict[str, Any]:
    """Check that deconstruction output keeps declared body modules editable."""
    from pptx import Presentation

    presentation = Presentation(str(Path(pptx_path)))
    pages = _pages(page_specs)
    xml_text = _slide_xml_text(pptx_path)
    allowed = set(allowed_large_visual_asset_ids or [])
    blockers: list[dict[str, Any]] = []
    rendered_slide_ids: set[str] = set()
    for index, slide in enumerate(presentation.slides, start=1):
        slide_id = f"S{index:02d}"
        rendered_slide_ids.add(slide_id)
        page = pages.get(slide_id, {})
        page = page if isinstance(page, dict) else {}
        elements = [item for item in page.get("elements", []) if isinstance(item, dict)]
        names = {shape.name: shape for shape in slide.shapes}
        declared_basic_names = {
            f"EL_{element['element_id']}"
            for element in elements
            if element.get("type") in {"rect", "oval", "line", "arrow", "flow"}
            and isinstance(element.get("element_id"), str)
        }
        for element in elements:
            element_id = element.get("element_id")
            if not isinstance(element_id, str) or not element_id:
                continue
            matching = [shape for name, shape in names.items() if name.startswith(f"EL_{element_id}")]
            if not matching:
                blockers.append(_issue(DECONSTRUCTION_EDITABILITY_FAILED, slide_id, f"missing named element EL_{element_id}"))
                continue
            kind = element.get("type")
            if kind == "matrix" and not any(shape.has_table for shape in matching):
                blockers.append(_issue(DECONSTRUCTION_EDITABILITY_FAILED, slide_id, f"{element_id} requires a native table"))
            elif kind in _CHART_TYPES and not any(shape.has_chart for shape in matching):
                blockers.append(_issue(DECONSTRUCTION_EDITABILITY_FAILED, slide_id, f"{element_id} requires a native chart"))
            elif kind == "flow" and not any(not shape.shape_type == 13 for shape in matching):
                blockers.append(_issue(DECONSTRUCTION_EDITABILITY_FAILED, slide_id, f"{element_id} requires a native flow node or connector"))
        for selected in _selected_text(page):
            if not _contains_text(xml_text.get(slide_id, []), selected):
                blockers.append(_issue(DECONSTRUCTION_EDITABILITY_FAILED, slide_id, f"selected editable text is absent from slide XML: {selected!r}"))

        body = _runtime_body(slide, presentation)
        body_area = body[2] * body[3]
        native_body = any(
            shape.name not in _SKELETON_NAMES and _overlap_area(_shape_box(shape), body) > 0 and (shape.has_text_frame and bool(shape.text.strip()) or shape.has_table or shape.has_chart or shape.name in declared_basic_names or (shape.shape_type not in {13, 18} and not shape.name.startswith("EL_")))
            for shape in slide.shapes
        )
        for shape in slide.shapes:
            if shape.shape_type != 13 or body_area <= 0:
                continue
            asset_id = shape.name[3:] if shape.name.startswith("EL_") else shape.name
            if _overlap_area(_shape_box(shape), body) / body_area >= 0.60 and not native_body and asset_id not in allowed:
                blockers.append(_issue(DECONSTRUCTION_EDITABILITY_FAILED, slide_id, f"large body picture {shape.name} has no editable native body content"))
    for slide_id in sorted(set(pages) - rendered_slide_ids):
        blockers.append(_issue(DECONSTRUCTION_EDITABILITY_FAILED, str(slide_id), "page spec has no matching PPTX slide"))
    return {"schema_version": SCHEMA_VERSION, "status": "blocked" if blockers else "pass", "ok": not blockers, "warnings": [], "blockers": blockers, "warning_count": 0, "blocker_count": len(blockers), "page_count": len(presentation.slides), "allowed_large_visual_asset_ids": sorted(allowed)}


def audit_bitmap_pptx(pptx_path: str | Path, bitmap_contract: dict[str, Any]) -> dict[str, Any]:
    """Audit the one-picture V6 bitmap body contract using python-pptx only."""
    from pptx import Presentation

    presentation = Presentation(str(Path(pptx_path)))
    contract_pages = _pages(bitmap_contract)
    blockers: list[dict[str, Any]] = []
    for index, slide in enumerate(presentation.slides, start=1):
        slide_id = f"S{index:02d}"
        record = contract_pages.get(slide_id, {})
        record = record if isinstance(record, dict) else {}
        for name in _SKELETON_NAMES:
            if not any(shape.name == name for shape in slide.shapes):
                blockers.append(_issue(BITMAP_CONTRACT_INVALID, slide_id, f"missing native skeleton shape {name}"))
        asset_id = record.get("asset_id")
        expected_name = f"EL_{asset_id}" if isinstance(asset_id, str) and asset_id else ""
        matches = [shape for shape in slide.shapes if shape.name == expected_name and shape.shape_type == 13]
        if len(matches) != 1:
            blockers.append(_issue(BITMAP_CONTRACT_INVALID, slide_id, f"expected exactly one named body picture {expected_name}, found {len(matches)}"))
            continue
        shape = matches[0]
        expected_hash = record.get("asset_sha256")
        actual_hash = hashlib.sha256(shape.image.blob).hexdigest()
        if not isinstance(expected_hash, str) or actual_hash != expected_hash:
            blockers.append(_issue(BITMAP_CONTRACT_INVALID, slide_id, "body picture SHA-256 does not match bitmap contract"))
        left, top, width, height = _shape_box(shape)
        body = _runtime_body(slide, presentation)
        if left < body[0] - _TOLERANCE_IN or top < body[1] - _TOLERANCE_IN or left + width > body[0] + body[2] + _TOLERANCE_IN or top + height > body[1] + body[3] + _TOLERANCE_IN:
            blockers.append(_issue(BITMAP_CONTRACT_INVALID, slide_id, "body picture is outside runtime body"))
        target = record.get("runtime_body_box", record.get("target_box_in"))
        if isinstance(target, list) and len(target) == 4 and all(isinstance(value, (int, float)) for value in target):
            if left < target[0] - _TOLERANCE_IN or top < target[1] - _TOLERANCE_IN or left + width > target[0] + target[2] + _TOLERANCE_IN or top + height > target[1] + target[3] + _TOLERANCE_IN:
                blockers.append(_issue(BITMAP_CONTRACT_INVALID, slide_id, "body picture is outside its contain target"))
        if height <= 0 or width <= 0 or abs((width / height) / (shape.image.size[0] / shape.image.size[1]) - 1.0) > _ASPECT_TOLERANCE:
            blockers.append(_issue(BITMAP_CONTRACT_INVALID, slide_id, "body picture aspect ratio is not preserved"))
    return {"schema_version": SCHEMA_VERSION, "status": "blocked" if blockers else "pass", "ok": not blockers, "warnings": [], "blockers": blockers, "warning_count": 0, "blocker_count": len(blockers), "page_count": len(presentation.slides)}
