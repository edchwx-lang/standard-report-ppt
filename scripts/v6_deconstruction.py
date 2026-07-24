from __future__ import annotations

from typing import Any


SCHEMA_VERSION = "6.0"
DECONSTRUCTION_BODY_BITMAP_FORBIDDEN = "DECONSTRUCTION_BODY_BITMAP_FORBIDDEN"
MAC_RECONSTRUCTION_UNSUPPORTED = "MAC_RECONSTRUCTION_UNSUPPORTED"
_ASSET_TYPES = {"asset", "body_asset"}
_PURE_VISUAL_KINDS = {"map", "photo", "illustration"}
_SKELETON_ROLES = {"chapter", "title", "core_point", "source", "page_number"}
_MAC_TYPES = {"asset", "section_header", "text", "rect", "oval", "line", "arrow", "text_card", "metric_strip", "hbar_chart", "column_chart", "line_chart", "combo_chart", "donut_chart", "grouped_hbar_chart", "flow", "matrix"}


def _pages(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        return {}
    return value["pages"] if isinstance(value.get("pages"), dict) else value


def _issue(code: str, slide_id: str, message: str) -> dict[str, Any]:
    return {"code": code, "severity": "blocker", "stage": "deconstruction_prebuild", "slide_id": slide_id, "message": message}


def _is_v6_deconstruct(brief: Any) -> bool:
    return isinstance(brief, dict) and brief.get("schema_version") == "6.0" and brief.get("pipeline_revision") == "6.0.0" and brief.get("construction_mode") == "deconstruct"


def _body_selected_text(page: dict[str, Any], module_id: str) -> list[str]:
    decisions = page.get("text_decisions", []) if isinstance(page.get("text_decisions"), list) else []
    return [item["selected"] for item in decisions if isinstance(item, dict) and item.get("module_id") == module_id and isinstance(item.get("selected"), str) and item["selected"].strip() and item.get("role") not in _SKELETON_ROLES]


def validate_deconstruction_prebuild(brief: dict[str, Any], page_specs: dict[str, Any], alignment: dict[str, Any], backend: str) -> dict[str, Any]:
    """Guard V6 deconstruction against replacing reviewed editable modules with a bitmap."""
    if not _is_v6_deconstruct(brief):
        return {"schema_version": SCHEMA_VERSION, "status": "pass", "ok": True, "warnings": [], "blockers": [], "warning_count": 0, "blocker_count": 0, "page_count": 0, "allowed_large_visual_assets_by_page": {}}

    blockers: list[dict[str, Any]] = []
    allowed_by_page: dict[str, list[str]] = {}
    specs = _pages(page_specs)
    aligned = _pages(alignment)
    for slide_id, raw_spec in specs.items():
        spec = raw_spec if isinstance(raw_spec, dict) else {}
        page = aligned.get(slide_id, {}) if isinstance(aligned.get(slide_id, {}), dict) else {}
        elements = [item for item in spec.get("elements", []) if isinstance(item, dict)]
        by_id = {item["element_id"]: item for item in elements if isinstance(item.get("element_id"), str) and item["element_id"]}
        contract = page.get("reconstruction_contract", {}) if isinstance(page.get("reconstruction_contract"), dict) else {}
        bindings = [item for item in contract.get("module_bindings", []) if isinstance(item, dict)]
        modules = {
            item.get("module_id"): item
            for item in page.get("structure_modules", [])
            if isinstance(item, dict) and isinstance(item.get("module_id"), str)
        }

        if backend == "mac_python_pptx_v2":
            for element in elements:
                if element.get("type") not in _MAC_TYPES:
                    blockers.append(_issue(MAC_RECONSTRUCTION_UNSUPPORTED, str(slide_id), f"unsupported Mac element type {element.get('type')!r}"))
        if any(element.get("type") == "body_asset" for element in elements):
            blockers.append(_issue(DECONSTRUCTION_BODY_BITMAP_FORBIDDEN, str(slide_id), "body_asset is reserved for bitmap mode"))

        bound_modules: list[tuple[dict[str, Any], list[dict[str, Any]]]] = []
        asset_references: dict[str, int] = {}
        for binding in bindings:
            ids = binding.get("element_ids", []) if isinstance(binding.get("element_ids"), list) else []
            bound = [by_id[item] for item in ids if isinstance(item, str) and item in by_id]
            bound_modules.append((binding, bound))
            for element in bound:
                if element.get("type") in _ASSET_TYPES:
                    asset_id = element.get("asset_id", element.get("element_id"))
                    if isinstance(asset_id, str):
                        asset_references[asset_id] = asset_references.get(asset_id, 0) + 1
        if any(count > 1 for count in asset_references.values()):
            blockers.append(_issue(DECONSTRUCTION_BODY_BITMAP_FORBIDDEN, str(slide_id), "one asset element is referenced by multiple module bindings"))

        visuals = [item for item in page.get("visuals", []) if isinstance(item, dict)]
        page_allowed: set[str] = set()
        asset_only_modules = [(binding, bound) for binding, bound in bound_modules if bound and all(element.get("type") in _ASSET_TYPES for element in bound)]
        for binding, bound in asset_only_modules:
            module_id = binding.get("module_id")
            element = bound[0] if len(bound) == 1 else None
            asset_id = element.get("asset_id") if isinstance(element, dict) else None
            semantics = modules.get(module_id)
            matched = [visual for visual in visuals if isinstance(asset_id, str) and (visual.get("asset_id") == asset_id or visual.get("element_id") == element.get("element_id"))]
            permitted = (
                isinstance(module_id, str)
                and isinstance(asset_id, str)
                and len(bound) == 1
                and asset_references.get(asset_id) == 1
                and isinstance(semantics, dict)
                and semantics.get("module_kind") == "pure_visual"
                and semantics.get("contains_editable_text") is False
                and len(matched) == 1
                and matched[0].get("kind") in _PURE_VISUAL_KINDS
                and not _body_selected_text(page, module_id)
            )
            if permitted:
                page_allowed.add(asset_id)
            else:
                blockers.append(_issue(DECONSTRUCTION_BODY_BITMAP_FORBIDDEN, str(slide_id), f"asset-only module {module_id or '?'} is not an approved pure visual"))
        asset_elements = [element for element in elements if element.get("type") in _ASSET_TYPES]
        if len(elements) == 1 and len(asset_elements) == 1 and not page_allowed:
            blockers.append(_issue(DECONSTRUCTION_BODY_BITMAP_FORBIDDEN, str(slide_id), "classic skeleton plus one composite body-image page spec is forbidden"))
        if page_allowed:
            allowed_by_page[str(slide_id)] = sorted(page_allowed)

    return {"schema_version": SCHEMA_VERSION, "status": "blocked" if blockers else "pass", "ok": not blockers, "warnings": [], "blockers": blockers, "warning_count": 0, "blocker_count": len(blockers), "page_count": len(specs), "allowed_large_visual_assets_by_page": allowed_by_page}
