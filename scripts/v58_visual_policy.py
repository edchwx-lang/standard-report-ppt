from __future__ import annotations

from typing import Any, Iterable


BODY_WIDTH = 12.2
BODY_HEIGHT = 4.35

ROUTE_TYPES = {
    "time_series": {"line_chart", "combo_chart", "column_chart"},
    "category_comparison": {"hbar_chart", "column_chart", "grouped_hbar_chart"},
    "composition": {"donut_chart"},
    "multi_metric_comparison": {"grouped_hbar_chart", "hbar_chart"},
    "lookup": {"matrix"},
    "process": {"flow"},
    "qualitative": {"text_card", "flow"},
    "mixed": {
        "line_chart",
        "combo_chart",
        "column_chart",
        "hbar_chart",
        "grouped_hbar_chart",
        "donut_chart",
        "matrix",
        "flow",
        "text_card",
        "metric_strip",
    },
}

QUALITATIVE_FORM_TYPES = {
    "parallel": {"text_card"},
    "narrative": {"text_card"},
    "causal": {"flow"},
}

DENSITY_BANDS = {
    "time_series": (0.60, 0.96),
    "category_comparison": (0.60, 0.96),
    "composition": (0.58, 0.94),
    "multi_metric_comparison": (0.60, 0.96),
    "lookup": (0.54, 0.94),
    "process": (0.52, 0.92),
    "qualitative": (0.48, 0.90),
    "mixed": (0.55, 0.94),
}


def recommended_visual(data_kind: str) -> set[str]:
    return set(ROUTE_TYPES.get(data_kind, set()))


def density_band(data_kind: str) -> tuple[float, float]:
    return DENSITY_BANDS.get(data_kind, DENSITY_BANDS["mixed"])


def _box(element: dict[str, Any]) -> tuple[float, float, float, float] | None:
    if element.get("coord_space", "body") != "body":
        return None
    box = element.get("box")
    if not isinstance(box, list) or len(box) != 4:
        return None
    try:
        x, y, width, height = (float(value) for value in box)
    except (TypeError, ValueError):
        return None
    left = max(0.0, x)
    top = max(0.0, y)
    right = min(BODY_WIDTH, x + width)
    bottom = min(BODY_HEIGHT, y + height)
    if right <= left or bottom <= top:
        return None
    return left, top, right, bottom


def _union_length(intervals: Iterable[tuple[float, float]]) -> float:
    ordered = sorted(intervals)
    if not ordered:
        return 0.0
    total = 0.0
    start, end = ordered[0]
    for next_start, next_end in ordered[1:]:
        if next_start <= end:
            end = max(end, next_end)
        else:
            total += end - start
            start, end = next_start, next_end
    return total + end - start


def body_occupancy(page_spec: dict[str, Any]) -> float:
    rectangles = [rect for element in page_spec.get("elements", []) if isinstance(element, dict) if (rect := _box(element))]
    if not rectangles:
        return 0.0
    x_values = sorted({value for left, _, right, _ in rectangles for value in (left, right)})
    area = 0.0
    for left, right in zip(x_values, x_values[1:]):
        if right <= left:
            continue
        intervals = [
            (top, bottom)
            for rect_left, top, rect_right, bottom in rectangles
            if rect_left < right and rect_right > left
        ]
        area += (right - left) * _union_length(intervals)
    return area / (BODY_WIDTH * BODY_HEIGHT)


def _primary_type(page_spec: dict[str, Any]) -> str | None:
    elements = [element for element in page_spec.get("elements", []) if isinstance(element, dict)]
    explicit = [element for element in elements if element.get("role") == "primary_evidence"]
    candidates = explicit or [
        element
        for element in elements
        if element.get("type") not in {"section_header", "text", "rect", "line", "arrow", "asset"}
    ]
    if not candidates:
        return None
    primary = max(
        candidates,
        key=lambda element: (
            float(element.get("box", [0, 0, 0, 0])[2]) * float(element.get("box", [0, 0, 0, 0])[3])
            if isinstance(element.get("box"), list) and len(element["box"]) == 4
            else 0.0
        ),
    )
    return str(primary.get("type")) if primary.get("type") else None


def validate_visual_route(slide: dict[str, Any], page_spec: dict[str, Any]) -> list[str]:
    slide_id = str(slide.get("slide_id", "?"))
    route = slide.get("visual_route")
    if not isinstance(route, dict):
        return [f"{slide_id}: V5.8 requires visual_route"]
    data_kind = str(route.get("data_kind", ""))
    allowed = recommended_visual(data_kind)
    if not allowed:
        return [f"{slide_id}: unsupported visual_route data_kind {data_kind!r}"]
    if data_kind == "qualitative":
        qualitative_form = str(route.get("qualitative_form", ""))
        if qualitative_form not in QUALITATIVE_FORM_TYPES:
            return [
                f"{slide_id}: qualitative visual_route requires qualitative_form "
                f"in {sorted(QUALITATIVE_FORM_TYPES)}"
            ]
        allowed = QUALITATIVE_FORM_TYPES[qualitative_form]
    primary_type = _primary_type(page_spec)
    if primary_type not in allowed:
        form_hint = f"/{route.get('qualitative_form')}" if data_kind == "qualitative" else ""
        return [
            f"{slide_id}: {data_kind}{form_hint} primary evidence must use one of {sorted(allowed)}; "
            f"got {primary_type!r}"
        ]
    return []


def validate_density(slide: dict[str, Any], page_spec: dict[str, Any]) -> list[str]:
    slide_id = str(slide.get("slide_id", "?"))
    route = slide.get("visual_route", {})
    data_kind = str(route.get("data_kind", "mixed")) if isinstance(route, dict) else "mixed"
    minimum, maximum = density_band(data_kind)
    occupancy = body_occupancy(page_spec)
    if occupancy < minimum or occupancy > maximum:
        return [
            f"{slide_id}: {data_kind} effective body occupancy must be {minimum:.0%}-{maximum:.0%}; got {occupancy:.1%}"
        ]
    return []


def _rgb_tuple(value: Any) -> tuple[int, int, int] | None:
    if isinstance(value, str):
        clean = value.strip().lstrip("#")
        if len(clean) != 6:
            return None
        try:
            return int(clean[0:2], 16), int(clean[2:4], 16), int(clean[4:6], 16)
        except ValueError:
            return None
    if isinstance(value, int):
        return value & 0xFF, (value >> 8) & 0xFF, (value >> 16) & 0xFF
    return None


def _is_red(value: Any) -> bool:
    color = _rgb_tuple(value)
    return bool(color and color[0] >= 150 and color[0] > color[1] * 1.8 and color[0] > color[2] * 1.8)


def _is_navy(value: Any) -> bool:
    return _rgb_tuple(value) == (0x1E, 0x38, 0x6B)


def _is_neutral_gray(value: Any) -> bool:
    color = _rgb_tuple(value)
    if not color:
        return False
    red, green, blue = color
    if min(color) >= 248:
        return False
    return max(color) - min(color) <= 10 and 110 <= (red + green + blue) / 3 <= 247


def _element_area(element: dict[str, Any]) -> float:
    box = element.get("box")
    if not isinstance(box, list) or len(box) != 4:
        return 0.0
    try:
        return max(0.0, float(box[2])) * max(0.0, float(box[3]))
    except (TypeError, ValueError):
        return 0.0


def validate_palette_and_visuals(
    page_spec: dict[str, Any],
    manifest_page: dict[str, Any],
) -> list[str]:
    errors: list[str] = []
    visuals = manifest_page.get("visuals", []) if isinstance(manifest_page, dict) else []
    declared_crop_ids = {
        str(visual.get("asset_id"))
        for visual in visuals
        if isinstance(visual, dict) and visual.get("disposition") == "crop" and visual.get("asset_id")
    }
    page_asset_ids = {
        str(element.get("asset_id"))
        for element in page_spec.get("elements", [])
        if isinstance(element, dict) and element.get("type") == "asset" and element.get("asset_id")
    }
    missing_assets = sorted(declared_crop_ids - page_asset_ids)
    if missing_assets:
        errors.append(
            f"reviewed ImageGen visuals must be inserted as asset crops, not native icon approximations: {missing_assets}"
        )

    navy_area = 0.0
    neutral_gray_area = 0.0
    for index, element in enumerate(page_spec.get("elements", [])):
        if not isinstance(element, dict):
            continue
        area = _element_area(element)
        element_emphasis = (
            element.get("semantic_role") == "data_emphasis"
            or element.get("role") == "data_emphasis"
        )
        for field in ("fill", "color", "line", "title_fill", "body_fill"):
            value = element.get(field)
            if _is_red(value):
                if not element_emphasis:
                    errors.append(f"element[{index}] red is reserved for data emphasis")
                if field in {"fill", "body_fill"} and area / (BODY_WIDTH * BODY_HEIGHT) > 0.03:
                    errors.append(f"element[{index}] red fill is too large for a data emphasis mark")
            if _is_navy(value):
                navy_area += area * (0.20 if field == "title_fill" else 1.0 if field == "fill" else 0.0)
            if field in {"fill", "body_fill"} and _is_neutral_gray(value):
                neutral_gray_area += area
        for collection_name in ("data", "metrics", "series"):
            for item in element.get(collection_name, []):
                if not isinstance(item, dict):
                    continue
                item_emphasis = bool(item.get("highlight")) or item.get("semantic_role") == "data_emphasis"
                for field in ("fill", "color", "line_color"):
                    if _is_red(item.get(field)) and not item_emphasis:
                        errors.append(
                            f"element[{index}]/{collection_name} red is reserved for data emphasis"
                        )
    navy_ratio = navy_area / (BODY_WIDTH * BODY_HEIGHT)
    if navy_ratio > 0.20:
        errors.append(f"body navy fill must stay within the 20% cap; got {navy_ratio:.1%}")
    neutral_gray_ratio = neutral_gray_area / (BODY_WIDTH * BODY_HEIGHT)
    if neutral_gray_ratio < 0.08:
        errors.append(f"body neutral gray support must occupy at least 8%; got {neutral_gray_ratio:.1%}")
    if neutral_gray_ratio > 0.35:
        errors.append(f"body neutral gray support must not exceed 35%; got {neutral_gray_ratio:.1%}")
    return errors
