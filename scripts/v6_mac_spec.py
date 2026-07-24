from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path
from typing import Any


SCHEMA_VERSION = "6.0"
PIPELINE_REVISION = "6.0.0"
BUILDER_BACKEND = "mac_python_pptx_v2"
ERROR_UNSUPPORTED = "MAC_RECONSTRUCTION_UNSUPPORTED"

DECONSTRUCT_TYPES = frozenset(
    {
        "asset",
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
    }
)

_COLOR_KEYS = frozenset(
    {
        "color",
        "fill",
        "body_fill",
        "line_color",
        "title_color",
        "value_color",
        "label_color",
    }
)
_HORIZONTAL_ALIGNMENT_KEYS = frozenset({"align", "alignment", "text_align"})
_VERTICAL_ALIGNMENT_KEYS = frozenset(
    {"vertical_align", "vertical_alignment", "vertical_anchor"}
)
_HORIZONTAL_ALIGNMENT = {
    -4152: "right",
    -4131: "left",
    -4130: "justify",
    -4108: "center",
    1: "left",
    2: "center",
    3: "right",
    4: "justify",
    "left": "left",
    "center": "center",
    "centre": "center",
    "right": "right",
    "justify": "justify",
}
_VERTICAL_ALIGNMENT = {
    1: "top",
    3: "middle",
    4: "bottom",
    "top": "top",
    "middle": "middle",
    "center": "middle",
    "centre": "middle",
    "bottom": "bottom",
}


class MacSpecError(ValueError):
    def __init__(self, issues: list[dict[str, Any]], mode: str):
        self.report = _report(mode, [], issues)
        details = "; ".join(
            f"{item.get('slide_id', '')}/{item.get('element_id', '')}: "
            f"{item.get('message', '')}"
            for item in issues
        )
        super().__init__(f"{ERROR_UNSUPPORTED}: {details}")


def _write_json_atomic(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def _normalize_color(value: Any) -> str:
    if isinstance(value, bool):
        raise ValueError("boolean is not a color")
    if isinstance(value, int):
        if not 0 <= value <= 0xFFFFFF:
            raise ValueError("integer color must fit 24 bits")
        red = value & 0xFF
        green = (value >> 8) & 0xFF
        blue = (value >> 16) & 0xFF
        return f"#{red:02X}{green:02X}{blue:02X}"
    if isinstance(value, str):
        token = value.strip().lstrip("#")
        if len(token) == 6:
            try:
                int(token, 16)
            except ValueError as exc:
                raise ValueError("color must contain hexadecimal digits") from exc
            return f"#{token.upper()}"
    raise ValueError("color must be a BGR integer or six-digit hexadecimal string")


def _normalize_alignment(value: Any, *, vertical: bool) -> str:
    mapping = _VERTICAL_ALIGNMENT if vertical else _HORIZONTAL_ALIGNMENT
    key = value.lower().strip() if isinstance(value, str) else value
    try:
        return mapping[key]
    except (KeyError, TypeError) as exc:
        axis = "vertical" if vertical else "horizontal"
        raise ValueError(f"unsupported {axis} alignment {value!r}") from exc


def _normalize_nested(value: Any, parent_key: str | None = None) -> Any:
    if isinstance(value, dict):
        output: dict[str, Any] = {}
        for key, child in value.items():
            if key in _COLOR_KEYS and child is not None:
                output[key] = _normalize_color(child)
            elif (
                key == "line"
                and child is not None
                and value.get("type") in {"rect", "oval"}
            ):
                output[key] = _normalize_color(child)
            elif key in _HORIZONTAL_ALIGNMENT_KEYS and child is not None:
                output[key] = _normalize_alignment(child, vertical=False)
            elif key in _VERTICAL_ALIGNMENT_KEYS and child is not None:
                output[key] = _normalize_alignment(child, vertical=True)
            else:
                output[key] = _normalize_nested(child, key)
        return output
    if isinstance(value, list):
        return [_normalize_nested(item, parent_key) for item in value]
    return deepcopy(value)


def _valid_box(value: Any) -> bool:
    return (
        isinstance(value, list)
        and len(value) == 4
        and all(
            isinstance(item, (int, float)) and not isinstance(item, bool)
            for item in value
        )
        and float(value[2]) > 0
        and float(value[3]) > 0
    )


def _geometry(element: dict[str, Any]) -> tuple[list[float] | None, str | None]:
    declarations = [
        ("box", element.get("box"), element.get("coord_space", "body")),
        ("body_box", element.get("body_box"), "body"),
        ("absolute_box", element.get("absolute_box"), "absolute"),
    ]
    present = [item for item in declarations if item[1] is not None]
    if len(present) != 1:
        return None, None
    _, raw_box, raw_space = present[0]
    space = str(raw_space).strip().lower()
    if space == "slide":
        space = "absolute"
    if space not in {"body", "absolute"} or not _valid_box(raw_box):
        return None, None
    return [float(item) for item in raw_box], space


def _issue(slide_id: str, element_id: str, message: str) -> dict[str, Any]:
    return {
        "code": ERROR_UNSUPPORTED,
        "slide_id": slide_id,
        "element_id": element_id,
        "message": message,
    }


def _report(
    mode: str,
    normalized_pages: list[str],
    blockers: list[dict[str, Any]],
    *,
    element_count: int = 0,
) -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "pipeline_revision": PIPELINE_REVISION,
        "construction_mode": mode,
        "builder_backend": BUILDER_BACKEND,
        "ok": not blockers,
        "pages": normalized_pages,
        "element_count": element_count,
        "blockers": blockers,
    }


def normalize_mac_page_specs(
    page_specs: dict[str, Any], construction_mode: str
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Normalize portable V6 page specs without changing their semantics."""
    if construction_mode not in {"deconstruct", "bitmap"}:
        raise MacSpecError(
            [_issue("", "", f"unsupported construction mode {construction_mode!r}")],
            construction_mode,
        )
    if not isinstance(page_specs, dict) or not page_specs:
        raise MacSpecError(
            [_issue("", "", "page specs must be a non-empty mapping")],
            construction_mode,
        )

    normalized: dict[str, Any] = {}
    blockers: list[dict[str, Any]] = []
    element_count = 0
    for slide_id, raw_page in page_specs.items():
        if not isinstance(slide_id, str) or not isinstance(raw_page, dict):
            blockers.append(_issue(str(slide_id), "", "page must be a mapping"))
            continue
        elements = raw_page.get("elements")
        if not isinstance(elements, list):
            blockers.append(_issue(slide_id, "", "page elements must be a list"))
            continue
        page = deepcopy(raw_page)
        normalized_elements: list[dict[str, Any]] = []
        body_assets = 0
        seen_element_ids: set[str] = set()
        for index, raw_element in enumerate(elements):
            element_count += 1
            if not isinstance(raw_element, dict):
                blockers.append(
                    _issue(slide_id, f"element[{index}]", "element must be a mapping")
                )
                continue
            try:
                element = _normalize_nested(raw_element)
            except ValueError as exc:
                blockers.append(
                    _issue(
                        slide_id,
                        str(raw_element.get("element_id", f"element[{index}]")),
                        str(exc),
                    )
                )
                continue
            element_id = element.get("element_id")
            if not isinstance(element_id, str) or not element_id:
                blockers.append(
                    _issue(slide_id, f"element[{index}]", "stable element_id is required")
                )
                continue
            if element_id in seen_element_ids:
                blockers.append(
                    _issue(slide_id, element_id, "element_id must be unique on its page")
                )
                continue
            seen_element_ids.add(element_id)
            kind = element.get("type")
            if construction_mode == "bitmap":
                if kind != "body_asset":
                    blockers.append(
                        _issue(
                            slide_id,
                            element_id,
                            "bitmap mode accepts only body_asset",
                        )
                    )
                    continue
                body_assets += 1
                if (
                    not isinstance(element.get("asset_id"), str)
                    or not element.get("asset_id")
                    or element.get("fit") != "contain"
                    or element.get("target") != "runtime_body_box"
                    or any(
                        key in element
                        for key in ("box", "body_box", "absolute_box", "coord_space")
                    )
                ):
                    blockers.append(
                        _issue(
                            slide_id,
                            element_id,
                            "body_asset requires asset_id, contain, runtime target, and no manual box",
                        )
                    )
                    continue
                normalized_elements.append(element)
                continue

            if kind == "body_asset" or kind not in DECONSTRUCT_TYPES:
                blockers.append(
                    _issue(slide_id, element_id, f"unsupported native type {kind!r}")
                )
                continue
            box, coord_space = _geometry(element)
            if box is None:
                blockers.append(
                    _issue(slide_id, element_id, "element requires one valid geometry box")
                )
                continue
            element.pop("body_box", None)
            element.pop("absolute_box", None)
            element["box"] = box
            element["coord_space"] = coord_space
            if kind == "asset":
                if (
                    not isinstance(element.get("asset_id"), str)
                    or not element.get("asset_id")
                ):
                    blockers.append(
                        _issue(slide_id, element_id, "bounded asset requires asset_id")
                    )
                    continue
                fit = element.get("fit", "contain")
                if fit != "contain":
                    blockers.append(
                        _issue(slide_id, element_id, "Mac assets require fit=contain")
                    )
                    continue
                element["fit"] = "contain"
            normalized_elements.append(element)
        if construction_mode == "bitmap" and body_assets != 1:
            blockers.append(
                _issue(
                    slide_id,
                    "",
                    "bitmap mode requires exactly one body_asset per page",
                )
            )
        page["elements"] = normalized_elements
        normalized[slide_id] = page

    if blockers:
        raise MacSpecError(blockers, construction_mode)
    report = _report(
        construction_mode,
        list(normalized),
        [],
        element_count=element_count,
    )
    return normalized, report


def materialize_mac_page_specs(project_dir: str | Path) -> dict[str, Any]:
    """Write normalized V6 Mac page specs and their blocking report."""
    project = Path(project_dir).resolve()
    brief_path = project / "project_brief.json"
    brief = json.loads(brief_path.read_text(encoding="utf-8"))
    if (
        brief.get("schema_version") != SCHEMA_VERSION
        or brief.get("pipeline_revision") != PIPELINE_REVISION
    ):
        raise ValueError("Mac v2 specification requires V6.0.0")
    mode = brief.get("construction_mode")
    source_name = "page_specs.json" if mode == "deconstruct" else "bitmap_page_specs.json"
    source_path = project / ".build" / source_name
    page_specs = json.loads(source_path.read_text(encoding="utf-8"))
    try:
        normalized, report = normalize_mac_page_specs(page_specs, str(mode))
    except MacSpecError as exc:
        _write_json_atomic(project / ".build" / "mac_spec_report.json", exc.report)
        raise
    _write_json_atomic(project / ".build" / "mac_page_specs.json", normalized)
    _write_json_atomic(project / ".build" / "mac_spec_report.json", report)
    return report
