from __future__ import annotations

import hashlib
import json
import re
from copy import deepcopy
from pathlib import Path
from typing import Any


SCHEMA_VERSION = "6.0"
PIPELINE_REVISION = "6.0.0"
BUILDER_BACKEND = "mac_python_pptx_v2"
ERROR_UNSUPPORTED = "MAC_RECONSTRUCTION_UNSUPPORTED"
V63_ATOMIC_TYPES = frozenset(
    {
        "text",
        "rect",
        "round_rect",
        "ellipse",
        "freeform",
        "line",
        "connector",
        "arrow",
        "image_crop",
        "group",
    }
)

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
        "title_fill",
        "title_color",
        "body_color",
        "value_color",
        "label_color",
    }
)
_STYLE_KEYS = frozenset(
    {
        "style",
        "color",
        "fill",
        "line",
        "line_color",
        "title_fill",
        "body_fill",
        "title_color",
        "body_color",
        "value_color",
        "label_color",
        "font_size",
        "bold",
        "align",
        "alignment",
        "text_align",
        "valign",
        "vertical_align",
        "vertical_alignment",
        "vertical_anchor",
        "margin_left",
        "margin_right",
        "margin_top",
        "margin_bottom",
        "weight",
        "show_legend",
    }
)
_ELEMENT_STYLE_KEYS = {
    "section_header": frozenset({"color", "font_size"}),
    "text": frozenset(
        {
            "color",
            "fill",
            "line",
            "font_size",
            "bold",
            "align",
            "valign",
            "vertical_alignment",
            "margin_left",
            "margin_right",
            "margin_top",
            "margin_bottom",
        }
    ),
    "rect": frozenset({"fill", "line", "line_color"}),
    "oval": frozenset(
        {
            "fill",
            "line",
            "line_color",
            "color",
            "font_size",
            "bold",
            "align",
            "valign",
            "vertical_alignment",
            "margin_left",
            "margin_right",
            "margin_top",
            "margin_bottom",
        }
    ),
    "line": frozenset({"color", "weight"}),
    "arrow": frozenset({"color", "weight"}),
    "text_card": frozenset(
        {"title_fill", "body_fill", "title_color", "body_color"}
    ),
    "metric_strip": frozenset(),
    "hbar_chart": frozenset({"style", "show_legend"}),
    "column_chart": frozenset({"style", "show_legend"}),
    "line_chart": frozenset({"style", "show_legend"}),
    "combo_chart": frozenset({"style", "show_legend"}),
    "donut_chart": frozenset({"style", "show_legend"}),
    "grouped_hbar_chart": frozenset({"style", "show_legend"}),
    "flow": frozenset(),
    "matrix": frozenset(),
    "asset": frozenset(),
}
_FLOW_STEP_STYLE_KEYS = frozenset(
    {
        "title_fill",
        "body_fill",
        "fill",
        "line_color",
        "title_color",
        "body_color",
    }
)
_METRIC_STYLE_KEYS = frozenset({"color", "value_color", "label_color"})
_HORIZONTAL_ALIGNMENT_KEYS = frozenset({"align", "alignment", "text_align"})
_VERTICAL_ALIGNMENT_KEYS = frozenset(
    {"valign", "vertical_align", "vertical_alignment", "vertical_anchor"}
)
_SAFE_ASSET_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]*$")
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


def normalize_v63_scene_graph(
    scene_graph: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Validate the shared V6.3 IR without redesigning it for macOS."""

    normalized = deepcopy(scene_graph)
    blockers: list[dict[str, Any]] = []
    if (
        not isinstance(scene_graph, dict)
        or scene_graph.get("schema_version") != "6.3"
        or scene_graph.get("deconstruction_runtime_revision") != "6.3.1"
        or scene_graph.get("color_authority") != "blueprint_body"
        or not isinstance(scene_graph.get("pages"), dict)
    ):
        blockers.append(_issue("", "", "invalid V6.3 shared scene header"))
    for slide_id, page in scene_graph.get("pages", {}).items():
        elements = page.get("elements", []) if isinstance(page, dict) else []
        if not isinstance(elements, list):
            blockers.append(_issue(str(slide_id), "", "scene elements must be a list"))
            continue
        for element in elements:
            element_id = str(element.get("element_id", "")) if isinstance(element, dict) else ""
            kind = element.get("type") if isinstance(element, dict) else None
            if kind not in V63_ATOMIC_TYPES:
                blockers.append(
                    _issue(str(slide_id), element_id, f"unsupported V6.3 atom {kind!r}")
                )
            elif kind == "freeform" and (
                not isinstance(element.get("points_px"), list)
                or len(element["points_px"]) < (3 if element.get('closed', True) else 2)
            ):
                blockers.append(
                    _issue(str(slide_id), element_id, "freeform requires at least three points")
                )
    report = {
        "schema_version": "6.3",
        "pipeline_revision": PIPELINE_REVISION,
        "deconstruction_runtime_revision": "6.3.1",
        "construction_mode": "deconstruct",
        "builder_backend": BUILDER_BACKEND,
        "ok": not blockers,
        "status": "pass" if not blockers else "blocked",
        "mac_native_render_unverified": True,
        "blockers": blockers,
    }
    if blockers:
        raise MacSpecError(blockers, "deconstruct")
    return normalized, report


def _write_json_atomic(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def _sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


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
                and value.get("type") in {"rect", "oval", "text"}
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


def _number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _nonempty_text(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _safe_asset_id(value: Any) -> bool:
    return (
        isinstance(value, str)
        and bool(_SAFE_ASSET_ID.fullmatch(value))
        and ".." not in value
    )


def _validate_payload(element: dict[str, Any]) -> list[str]:
    kind = element.get("type")
    errors: list[str] = []
    if kind == "section_header" and not _nonempty_text(
        element.get("text", element.get("title"))
    ):
        errors.append("section_header requires non-empty text/title")
    elif kind == "text":
        if not isinstance(element.get("text"), str):
            errors.append("text element requires text")
        for field in (
            "margin_left",
            "margin_right",
            "margin_top",
            "margin_bottom",
        ):
            if field in element and (
                not _number(element[field]) or float(element[field]) < 0
            ):
                errors.append(f"text {field} must be a non-negative number")
    elif kind == "oval":
        if "text" in element and not isinstance(element["text"], str):
            errors.append("oval text must be a string")
    elif kind in {"line", "arrow"} and (
        "weight" in element
        and (not _number(element["weight"]) or float(element["weight"]) <= 0)
    ):
        errors.append(f"{kind} weight must be a positive number")
    elif kind == "text_card":
        if not _nonempty_text(element.get("title")):
            errors.append("text_card requires a non-empty title")
        if not _nonempty_text(element.get("body")):
            errors.append("text_card requires a non-empty body")
    elif kind == "metric_strip":
        metrics = element.get("metrics")
        if not isinstance(metrics, list) or not metrics:
            errors.append("metric_strip requires non-empty metrics")
        else:
            for index, metric in enumerate(metrics):
                if (
                    not isinstance(metric, dict)
                    or not _nonempty_text(metric.get("label"))
                    or "value" not in metric
                    or not isinstance(metric.get("value"), (str, int, float))
                    or isinstance(metric.get("value"), bool)
                ):
                    errors.append(
                        f"metric_strip metrics[{index}] requires label and value"
                    )
    elif kind in {
        "hbar_chart",
        "column_chart",
        "line_chart",
        "combo_chart",
        "donut_chart",
        "grouped_hbar_chart",
    }:
        rows = element.get("data")
        if not isinstance(rows, list) or not rows:
            errors.append(f"{kind} requires non-empty data")
        else:
            grouped_width: int | None = None
            total = 0.0
            for index, row in enumerate(rows):
                if not isinstance(row, dict):
                    errors.append(f"{kind} data[{index}] must be a mapping")
                    continue
                if not _nonempty_text(row.get("label")):
                    errors.append(f"{kind} data[{index}] requires label")
                if kind == "grouped_hbar_chart":
                    values = row.get("values")
                    if (
                        not isinstance(values, list)
                        or not values
                        or not all(_number(item) for item in values)
                    ):
                        errors.append(
                            f"{kind} data[{index}] requires numeric values"
                        )
                    elif grouped_width is None:
                        grouped_width = len(values)
                    elif len(values) != grouped_width:
                        errors.append(f"{kind} series width must be rectangular")
                    continue
                if not _number(row.get("value")):
                    errors.append(f"{kind} data[{index}] requires numeric value")
                else:
                    total += float(row["value"])
                if kind == "combo_chart":
                    line_value = row.get("line_value")
                    if line_value is None:
                        line_value = row.get("line", row.get("value2"))
                    if not _number(line_value):
                        errors.append(
                            f"combo_chart data[{index}] requires numeric line_value"
                        )
                    else:
                        row["line_value"] = line_value
                        row.pop("line", None)
                        row.pop("value2", None)
            if kind == "donut_chart" and total <= 0:
                errors.append("donut_chart values must sum to a positive number")
    elif kind == "flow":
        steps = element.get("steps")
        if not isinstance(steps, list) or not 2 <= len(steps) <= 6:
            errors.append("flow requires two to six steps")
        else:
            for index, step in enumerate(steps):
                if not isinstance(step, dict):
                    errors.append(f"flow steps[{index}] must be a mapping")
                    continue
                if not _nonempty_text(step.get("title", step.get("label"))):
                    errors.append(
                        f"flow steps[{index}] requires presentable title/label"
                    )
                for field in ("body", "detail"):
                    if field in step and not isinstance(step[field], str):
                        errors.append(f"flow steps[{index}] {field} must be text")
    elif kind == "matrix":
        headers = element.get("headers")
        rows = element.get("rows")
        if (
            not isinstance(headers, list)
            or not headers
            or not all(_nonempty_text(item) for item in headers)
        ):
            errors.append("matrix requires non-empty text headers")
        if not isinstance(rows, list) or not rows:
            errors.append("matrix requires non-empty rows")
        elif isinstance(headers, list):
            for index, row in enumerate(rows):
                if not isinstance(row, list) or len(row) != len(headers):
                    errors.append(
                        f"matrix rows[{index}] must match the header width"
                    )
    elif kind in {"asset", "body_asset"} and not _safe_asset_id(
        element.get("asset_id")
    ):
        errors.append("asset_id is unsafe")
    return errors


def _validate_style_contract(element: dict[str, Any]) -> list[str]:
    kind = str(element.get("type", ""))
    allowed = _ELEMENT_STYLE_KEYS.get(kind, frozenset())
    errors = [
        f"{kind} does not support style field {key!r}"
        for key in element
        if key in _STYLE_KEYS and key not in allowed
    ]
    if kind in {
        "hbar_chart",
        "column_chart",
        "line_chart",
        "combo_chart",
        "donut_chart",
        "grouped_hbar_chart",
    } and "style" in element:
        style = element["style"]
        if (
            not isinstance(style, int)
            or isinstance(style, bool)
            or not 1 <= style <= 48
        ):
            errors.append(f"{kind} style must be an integer from 1 to 48")
    if kind == "flow" and isinstance(element.get("steps"), list):
        allowed_step_keys = {
            "title",
            "label",
            "body",
            "detail",
        } | set(_FLOW_STEP_STYLE_KEYS)
        for index, step in enumerate(element["steps"]):
            if not isinstance(step, dict):
                continue
            unsupported = [key for key in step if key not in allowed_step_keys]
            errors.extend(
                f"flow steps[{index}] does not support field {key!r}"
                for key in unsupported
            )
    if kind == "metric_strip" and isinstance(element.get("metrics"), list):
        allowed_metric_keys = {"label", "value"} | set(_METRIC_STYLE_KEYS)
        for index, metric in enumerate(element["metrics"]):
            if not isinstance(metric, dict):
                continue
            unsupported = [
                key for key in metric if key not in allowed_metric_keys
            ]
            errors.extend(
                f"metric_strip metrics[{index}] does not support field {key!r}"
                for key in unsupported
            )
    chart_types = {
        "hbar_chart",
        "column_chart",
        "line_chart",
        "combo_chart",
        "donut_chart",
        "grouped_hbar_chart",
    }
    if kind in chart_types and isinstance(element.get("data"), list):
        if kind == "grouped_hbar_chart":
            allowed_row_keys = {"label", "values"}
        elif kind == "combo_chart":
            allowed_row_keys = {"label", "value", "line_value"}
        else:
            allowed_row_keys = {"label", "value"}
        for index, row in enumerate(element["data"]):
            if not isinstance(row, dict):
                continue
            errors.extend(
                f"{kind} data[{index}] does not support field {key!r}"
                for key in row
                if key not in allowed_row_keys
            )
    if kind in chart_types and "series" in element:
        series = element["series"]
        if kind != "grouped_hbar_chart":
            errors.append(f"{kind} does not support series declarations")
        elif not isinstance(series, list):
            errors.append("grouped_hbar_chart series must be a list")
        else:
            for index, item in enumerate(series):
                if not isinstance(item, dict):
                    errors.append(
                        f"grouped_hbar_chart series[{index}] must be a mapping"
                    )
                    continue
                errors.extend(
                    "grouped_hbar_chart "
                    f"series[{index}] does not support field {key!r}"
                    for key in item
                    if key != "name"
                )
    return errors


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
        "status": "blocked" if blockers else "pass",
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
                    or element.get("outline") != "none"
                    or any(
                        key in element
                        for key in ("box", "body_box", "absolute_box", "coord_space")
                    )
                ):
                    blockers.append(
                        _issue(
                            slide_id,
                            element_id,
                        "body_asset requires asset_id, contain, runtime target, outline none, and no manual box",
                        )
                    )
                    continue
                payload_errors = _validate_payload(element)
                payload_errors.extend(_validate_style_contract(element))
                if payload_errors:
                    blockers.extend(
                        _issue(slide_id, element_id, message)
                        for message in payload_errors
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
            payload_errors = _validate_payload(element)
            payload_errors.extend(_validate_style_contract(element))
            if payload_errors:
                blockers.extend(
                    _issue(slide_id, element_id, message)
                    for message in payload_errors
                )
                continue
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
        or brief.get("production_mode") != "blueprint"
        or brief.get("construction_mode") not in {"deconstruct", "bitmap"}
    ):
        raise ValueError(
            f"{ERROR_UNSUPPORTED}: Mac v2 specification requires V6.0.0"
        )
    mode = brief.get("construction_mode")
    source_name = "page_specs.json" if mode == "deconstruct" else "bitmap_page_specs.json"
    source_path = project / ".build" / source_name
    page_specs = json.loads(source_path.read_text(encoding="utf-8"))
    try:
        normalized, report = normalize_mac_page_specs(page_specs, str(mode))
    except MacSpecError as exc:
        blocked = dict(
            exc.report,
            source_path=f".build/{source_name}",
            source_sha256=_sha256_file(source_path),
            normalized_path=".build/mac_page_specs.json",
            normalized_sha256=None,
        )
        _write_json_atomic(project / ".build" / "mac_spec_report.json", blocked)
        raise
    normalized_path = project / ".build" / "mac_page_specs.json"
    _write_json_atomic(normalized_path, normalized)
    report.update(
        {
            "source_path": f".build/{source_name}",
            "source_sha256": _sha256_file(source_path),
            "normalized_path": ".build/mac_page_specs.json",
            "normalized_sha256": _sha256_file(normalized_path),
        }
    )
    _write_json_atomic(project / ".build" / "mac_spec_report.json", report)
    return report
