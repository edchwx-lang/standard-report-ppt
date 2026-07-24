from __future__ import annotations

from typing import Any


SCHEMA_VERSION = "6.0"
DECONSTRUCTION_BODY_BITMAP_FORBIDDEN = "DECONSTRUCTION_BODY_BITMAP_FORBIDDEN"
MAC_RECONSTRUCTION_UNSUPPORTED = "MAC_RECONSTRUCTION_UNSUPPORTED"

_MAC_SUPPORTED_TYPES = frozenset(
    {
        "asset", "section_header", "text", "rect", "oval", "line", "arrow",
        "text_card", "metric_strip", "hbar_chart", "column_chart", "line_chart",
        "combo_chart", "donut_chart", "grouped_hbar_chart", "flow", "matrix",
    }
)
_ASSET_TYPES = frozenset({"asset", "body_asset"})
_PURE_VISUAL_KINDS = frozenset({"map", "photo", "illustration", "device", "person", "product"})


def _pages(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        return {}
    nested = value.get("pages")
    return nested if isinstance(nested, dict) else value


def _issue(code: str, slide_id: str, message: str) -> dict[str, Any]:
    return {"code": code, "severity": "blocker", "stage": "deconstruction_prebuild", "slide_id": slide_id, "message": message}


def _is_deconstruct_v6(brief: Any) -> bool:
    return isinstance(brief, dict) and brief.get("schema_version") == "6.0" and brief.get("pipeline_revision") == "6.0.0" and brief.get("construction_mode") == "deconstruct"


def _element_asset_id(element: dict[str, Any]) -> str | None:
    for key in ("asset_id", "element_id"):
        value = element.get(key)
        if isinstance(value, str) and value:
            return value
    return None


def _selected_text(contract: dict[str, Any]) -> list[str]:
    values: list[str] = []
    for decision in contract.get("text_decisions", []) if isinstance(contract.get("text_decisions"), list) else []:
        if isinstance(decision, dict) and isinstance(decision.get("selected"), str) and decision["selected"].strip():
            values.append(decision["selected"])
    return values


def validate_deconstruction_prebuild(
    brief: dict[str, Any], page_specs: dict[str, Any], alignment: dict[str, Any], backend: str
) -> dict[str, Any]:
    """Reject V6 deconstruction specs that replace editable content with body bitmaps."""
    if not _is_deconstruct_v6(brief):
        return {"schema_version": SCHEMA_VERSION, "status": "pass", "ok": True, "warnings": [], "blockers": [], "warning_count": 0, "blocker_count": 0, "page_count": 0, "allowed_large_visual_asset_ids": []}

    blockers: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []
    allowed: set[str] = set()
    spec_pages = _pages(page_specs)
    alignment_pages = _pages(alignment)
    for slide_id, raw_page in spec_pages.items():
        page = raw_page if isinstance(raw_page, dict) else {}
        elements = [item for item in page.get("elements", []) if isinstance(item, dict)]
        element_by_id = {item.get("element_id"): item for item in elements if isinstance(item.get("element_id"), str) and item["element_id"]}
        contract = page.get("reconstruction_contract") if isinstance(page.get("reconstruction_contract"), dict) else {}
        bindings = [item for item in contract.get("module_bindings", []) if isinstance(item, dict)]
        if backend == "mac_python_pptx_v2":
            for element in elements:
                if element.get("type") not in _MAC_SUPPORTED_TYPES:
                    blockers.append(_issue(MAC_RECONSTRUCTION_UNSUPPORTED, str(slide_id), f"{element.get('element_id', '?')}: unsupported Mac element type {element.get('type')!r}"))
        if any(element.get("type") == "body_asset" for element in elements):
            blockers.append(_issue(DECONSTRUCTION_BODY_BITMAP_FORBIDDEN, str(slide_id), "body_asset is reserved for bitmap construction mode"))

        asset_binding_counts: dict[str, int] = {}
        binding_elements: list[tuple[dict[str, Any], list[dict[str, Any]]]] = []
        for binding in bindings:
            ids = binding.get("element_ids") if isinstance(binding.get("element_ids"), list) else []
            bound = [element_by_id[item] for item in ids if isinstance(item, str) and item in element_by_id]
            binding_elements.append((binding, bound))
            for element in bound:
                if element.get("type") in _ASSET_TYPES:
                    asset_id = _element_asset_id(element)
                    if asset_id:
                        asset_binding_counts[asset_id] = asset_binding_counts.get(asset_id, 0) + 1
            if bound and all(element.get("type") in _ASSET_TYPES for element in bound):
                declared_editable = bool(binding.get("editable") or binding.get("native") or binding.get("requires_editable"))
                if declared_editable or _selected_text(contract):
                    blockers.append(_issue(DECONSTRUCTION_BODY_BITMAP_FORBIDDEN, str(slide_id), f"module {binding.get('module_id', '?')} contains editable content but is represented only by assets"))
        if any(count > 1 for count in asset_binding_counts.values()):
            blockers.append(_issue(DECONSTRUCTION_BODY_BITMAP_FORBIDDEN, str(slide_id), "one asset element is bound to multiple modules"))
        asset_only = [bound for _, bound in binding_elements if bound and all(item.get("type") in _ASSET_TYPES for item in bound)]
        if len(asset_only) > 1 and len({ _element_asset_id(item) for bound in asset_only for item in bound }) == 1:
            blockers.append(_issue(DECONSTRUCTION_BODY_BITMAP_FORBIDDEN, str(slide_id), "visible body modules collapse to one composite asset"))
        if len(elements) == 1 and elements[0].get("type") in _ASSET_TYPES and len(bindings) > 1:
            blockers.append(_issue(DECONSTRUCTION_BODY_BITMAP_FORBIDDEN, str(slide_id), "classic skeleton plus one composite body image is forbidden"))

        visual_page = alignment_pages.get(slide_id, {})
        visuals = visual_page.get("visuals", []) if isinstance(visual_page, dict) else []
        visuals = [item for item in visuals if isinstance(item, dict)]
        page_allowed: set[str] = set()
        for element in elements:
            if element.get("type") not in _ASSET_TYPES:
                continue
            asset_id = _element_asset_id(element)
            matched = [item for item in visuals if item.get("asset_id") == asset_id or item.get("element_id") == element.get("element_id")]
            modules = [bound for _, bound in binding_elements if element in bound]
            module_is_pure = len(modules) == 1 and all(item.get("type") in _ASSET_TYPES for item in modules[0])
            if len(matched) == 1 and matched[0].get("kind") in _PURE_VISUAL_KINDS and module_is_pure and not _selected_text(contract):
                page_allowed.add(asset_id or str(element.get("element_id")))
        asset_elements = [element for element in elements if element.get("type") in _ASSET_TYPES]
        if len(elements) == 1 and len(asset_elements) == 1 and not page_allowed:
            blockers.append(_issue(DECONSTRUCTION_BODY_BITMAP_FORBIDDEN, str(slide_id), "a composite body-image page spec is not a deconstruction"))
        allowed.update(page_allowed)

    return {
        "schema_version": SCHEMA_VERSION,
        "status": "blocked" if blockers else "pass",
        "ok": not blockers,
        "warnings": warnings,
        "blockers": blockers,
        "warning_count": len(warnings),
        "blocker_count": len(blockers),
        "page_count": len(spec_pages),
        "allowed_large_visual_asset_ids": sorted(allowed),
    }
