from __future__ import annotations

import json
import re
import math
from copy import deepcopy
from pathlib import Path
from typing import Any


SCHEMA_VERSION = "6.3"
RUNTIME_REVISION = "6.3.1"
ATOMIC_TYPES = frozenset(
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
GENERIC_COMPONENT_TYPES = frozenset(
    {"matrix", "flow", "text_card", "metric_strip", "chart", "table"}
)
_COLOR = re.compile(r"^#[0-9A-Fa-f]{6}$")


def _read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"expected object: {path}")
    return value


def _write_json_atomic(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    temporary.replace(path)


def _issue(code: str, slide_id: str, message: str) -> dict[str, str]:
    return {
        "code": code,
        "severity": "blocker",
        "stage": "v63_scene_graph",
        "slide_id": slide_id,
        "message": message,
    }


def _valid_box(box: Any, body: list[int], *, allow_line: bool = False) -> bool:
    if not isinstance(box, list) or len(box) != 4:
        return False
    try:
        x1, y1, x2, y2 = [float(value) for value in box]
        left, top, width, height = [float(value) for value in body]
    except (TypeError, ValueError):
        return False
    return (
        all(math.isfinite(v) for v in (x1, y1, x2, y2))
        and ((x2 >= x1 and y2 >= y1 and (x2 > x1 or y2 > y1)) if allow_line else (x2 > x1 and y2 > y1))
        and x1 >= left
        and y1 >= top
        and x2 <= left + width
        and y2 <= top + height
    )


def _style_errors(style: Any) -> list[str]:
    if not isinstance(style, dict):
        return ["style must be an object"]
    errors: list[str] = []
    for key in ("fill", "line", "color"):
        value = style.get(key)
        if value is not None and value != "none" and (
            not isinstance(value, str) or _COLOR.fullmatch(value) is None
        ):
            errors.append(f"{key} must be #RRGGBB or none")
    return errors


def body_contain_transform(source_roi_px: list[float], target_roi_in: list[float]) -> dict:
    sx, sy, sw, sh = map(float, source_roi_px)
    tx, ty, tw, th = map(float, target_roi_in)
    if not all(math.isfinite(v) for v in (sx, sy, sw, sh, tx, ty, tw, th)) or min(sw, sh, tw, th) <= 0:
        raise ValueError('V63_SCENE_COORDINATE_INVALID')
    scale = min(tw / sw, th / sh)
    return {'scale': scale, 'offset_x': tx + (tw - sw * scale) / 2 - sx * scale,
            'offset_y': ty + (th - sh * scale) / 2 - sy * scale}


def map_source_point(point_px: list[float], transform: dict) -> list[float]:
    return [float(point_px[0]) * transform['scale'] + transform['offset_x'],
            float(point_px[1]) * transform['scale'] + transform['offset_y']]


def normalize_element_geometry(element: dict) -> dict:
    result = deepcopy(element)
    kind = result.get('type')
    radius = result.get('style', {}).get('corner_radius_px')
    if kind == 'round_rect' and radius is not None:
        x, y, right, bottom = map(float, result['bbox_px'])
        if isinstance(radius, bool) or not isinstance(radius, (int, float)) or not math.isfinite(radius) or not 0 <= radius <= min(right-x, bottom-y)/2:
            raise ValueError('V63_CORNER_RADIUS_INVALID')
        if radius == 0:
            result['type'] = 'rect'
            return result
        points = []
        for cx, cy, start in [(right-radius,y+radius,-90),(right-radius,bottom-radius,0),
                              (x+radius,bottom-radius,90),(x+radius,y+radius,180)]:
            for step in range(9):
                angle = math.radians(start + step*90/8)
                points.append([cx+radius*math.cos(angle),cy+radius*math.sin(angle)])
        result.update(type='freeform', points_px=points, closed=True)
        kind = 'freeform'
    if kind not in {'line', 'connector', 'arrow', 'freeform'} or 'points_px' not in result:
        return result
    points = result['points_px']
    minimum = 3 if kind == 'freeform' and result.get('closed', True) else 2
    if not isinstance(points, list) or len(points) < minimum:
        raise ValueError('V63_PATH_POINTS_INVALID')
    if any(not isinstance(p, list) or len(p) != 2 or
           any(not isinstance(v, (int, float)) or not math.isfinite(v) for v in p) for p in points):
        raise ValueError('V63_PATH_POINTS_INVALID')
    if len({tuple(p) for p in points}) < minimum:
        raise ValueError('V63_PATH_DEGENERATE')
    xs, ys = zip(*points)
    result['bbox_px'] = [float(min(xs)), float(min(ys)), float(max(xs)), float(max(ys))]
    if kind == 'freeform' and not isinstance(result.get('closed', True), bool):
        raise ValueError('V63_PATH_CLOSED_INVALID')
    return result


def pixel_box_to_slide_box(
    bbox_px: list[float], body_roi_px: list[float], body_roi_in: list[float],
    *, coordinate_mode: str = 'legacy_stretch', allow_line: bool = False,
) -> list[float]:
    if len(bbox_px) != 4 or len(body_roi_px) != 4 or len(body_roi_in) != 4:
        raise ValueError("V63_SCENE_COORDINATE_INVALID")
    x1, y1, x2, y2 = [float(value) for value in bbox_px]
    body_x, body_y, body_width, body_height = [float(value) for value in body_roi_px]
    slide_x, slide_y, slide_width, slide_height = [float(value) for value in body_roi_in]
    if body_width <= 0 or body_height <= 0 or not _valid_box(bbox_px, body_roi_px, allow_line=allow_line):
        raise ValueError("V63_SCENE_COORDINATE_INVALID")
    if coordinate_mode == 'source_pixels_contain':
        transform = body_contain_transform(body_roi_px, body_roi_in)
        x, y = map_source_point([x1, y1], transform)
        return [round(v, 4) for v in (x, y, (x2-x1)*transform['scale'], (y2-y1)*transform['scale'])]
    if coordinate_mode != 'legacy_stretch':
        raise ValueError('V63_COORDINATE_MODE_INVALID')
    mapped = [
        slide_x + (x1 - body_x) / body_width * slide_width,
        slide_y + (y1 - body_y) / body_height * slide_height,
        (x2 - x1) / body_width * slide_width,
        (y2 - y1) / body_height * slide_height,
    ]
    return [round(value, 4) for value in mapped]


def validate_scene_graph(
    project_dir: str | Path, scene_graph: dict[str, Any]
) -> dict[str, Any]:
    project = Path(project_dir).resolve()
    census_path = project / ".build" / "v63_visual_census.json"
    if not census_path.is_file():
        return {
            "schema_version": SCHEMA_VERSION,
            "ok": False,
            "element_count": 0,
            "blockers": [_issue("V63_SCENE_CENSUS_MISSING", "", str(census_path))],
        }
    census = _read_json(census_path)
    blockers: list[dict[str, str]] = []
    pages = scene_graph.get("pages") if isinstance(scene_graph, dict) else None
    census_pages = census.get("pages", {})
    if (
        scene_graph.get("schema_version") != SCHEMA_VERSION
        or scene_graph.get("deconstruction_runtime_revision") != RUNTIME_REVISION
        or scene_graph.get("color_authority") != "blueprint_body"
        or not isinstance(pages, dict)
        or set(pages) != set(census_pages)
    ):
        blockers.append(_issue("V63_SCENE_HEADER_INVALID", "", "scene graph header, color authority, or page set is invalid"))
        pages = pages if isinstance(pages, dict) else {}
    element_count = 0
    for slide_id, census_page in census_pages.items():
        page = pages.get(slide_id, {}) if isinstance(pages.get(slide_id), dict) else {}
        body = census_page.get("body_roi_px", [])
        if page.get("blueprint_sha256") != census_page.get("blueprint_sha256"):
            blockers.append(_issue("V63_SCENE_BLUEPRINT_HASH_MISMATCH", slide_id, "scene graph is not bound to the census blueprint"))
        if page.get("body_roi_px") != body:
            blockers.append(_issue("V63_SCENE_BODY_ROI_MISMATCH", slide_id, "scene graph body ROI differs from census"))
        elements = page.get("elements", [])
        if not isinstance(elements, list):
            blockers.append(_issue("V63_SCENE_ELEMENTS_INVALID", slide_id, "elements must be a list"))
            elements = []
        element_count += len(elements)
        by_id: dict[str, dict[str, Any]] = {}
        for element in elements:
            if not isinstance(element, dict):
                blockers.append(_issue("V63_SCENE_ELEMENT_INVALID", slide_id, "element must be an object"))
                continue
            element_id = element.get("element_id")
            if not isinstance(element_id, str) or not element_id or element_id in by_id:
                blockers.append(_issue("V63_SCENE_ELEMENT_ID_INVALID", slide_id, f"invalid or duplicate element id {element_id!r}"))
                continue
            by_id[element_id] = element
        candidate_by_id = {
            item.get("candidate_id"): item
            for item in census_page.get("candidates", [])
            if isinstance(item, dict) and isinstance(item.get("candidate_id"), str)
        }
        for element_id, element in by_id.items():
            kind = element.get("type")
            if kind in GENERIC_COMPONENT_TYPES:
                blockers.append(_issue("V63_SCENE_GENERIC_COMPONENT_FORBIDDEN", slide_id, f"{element_id}: {kind} cannot replace atomic blueprint geometry"))
            elif kind not in ATOMIC_TYPES:
                blockers.append(_issue("V63_SCENE_TYPE_INVALID", slide_id, f"{element_id}: unsupported atom {kind!r}"))
            try:
                normalized = normalize_element_geometry(element)
            except ValueError as exc:
                blockers.append(_issue('V63_PATH_POINTS_INVALID', slide_id, f'{element_id}: {exc}'))
                normalized = element
            if not _valid_box(normalized.get("bbox_px"), body, allow_line=kind in {'line', 'connector', 'arrow'} or (kind == 'freeform' and not element.get('closed', True))):
                blockers.append(_issue("V63_SCENE_BOX_INVALID", slide_id, f"{element_id}: invalid body box"))
            if not isinstance(element.get("z_order"), int) or element.get("z_order") < 0:
                blockers.append(_issue("V63_SCENE_Z_ORDER_INVALID", slide_id, f"{element_id}: z_order must be a non-negative integer"))
            for error in _style_errors(element.get("style")):
                blockers.append(_issue("V63_SCENE_STYLE_INVALID", slide_id, f"{element_id}: {error}"))
            group_id = element.get("group_id")
            if group_id is not None and (
                group_id not in by_id or by_id[group_id].get("type") != "group"
            ):
                blockers.append(_issue("V63_SCENE_GROUP_INVALID", slide_id, f"{element_id}: group {group_id!r} is missing"))
            sources = element.get("source_candidate_ids")
            if not isinstance(sources, list) or any(source not in candidate_by_id for source in sources):
                blockers.append(_issue("V63_SCENE_SOURCE_INVALID", slide_id, f"{element_id}: invalid census source binding"))
            if kind != "group" and not sources:
                blockers.append(_issue("V63_SCENE_SOURCE_INVALID", slide_id, f"{element_id}: every rendered atom needs a census source"))
            if kind == "text" and not (
                isinstance(element.get("text"), str)
                or isinstance(element.get("runs"), list)
            ):
                blockers.append(_issue("V63_SCENE_TEXT_INVALID", slide_id, f"{element_id}: text or runs are required"))
            if kind == "image_crop" and (
                not isinstance(element.get("asset_id"), str)
                or not element.get("asset_id")
                or element.get("intrinsic_text_only") is not True
            ):
                blockers.append(_issue("V63_SCENE_CROP_INVALID", slide_id, f"{element_id}: crop requires asset_id and intrinsic_text_only=true"))
        resolutions = page.get("candidate_resolutions")
        if not isinstance(resolutions, dict):
            resolutions = {}
        for candidate_id, candidate in candidate_by_id.items():
            resolution = resolutions.get(candidate_id)
            if not isinstance(resolution, dict):
                blockers.append(_issue("V63_SCENE_CANDIDATE_UNRESOLVED", slide_id, f"{candidate_id}: missing resolution"))
                continue
            mode = resolution.get("mode")
            element_ids = resolution.get("element_ids", [])
            bound = [by_id[item] for item in element_ids if item in by_id] if isinstance(element_ids, list) else []
            if not isinstance(element_ids, list) or len(bound) != len(element_ids):
                blockers.append(_issue("V63_SCENE_CANDIDATE_UNRESOLVED", slide_id, f"{candidate_id}: resolution references missing elements"))
                continue
            expected = candidate.get("expected_treatment")
            valid = (
                expected == "editable"
                and mode == "editable"
                and bool(bound)
                and all(item.get("type") != "image_crop" for item in bound)
            ) or (
                expected == "crop"
                and mode == "crop"
                and len(bound) == 1
                and bound[0].get("type") == "image_crop"
            ) or (
                expected == "ignore"
                and mode == "ignore"
                and not bound
            )
            if not valid:
                blockers.append(_issue("V63_SCENE_RESOLUTION_MISMATCH", slide_id, f"{candidate_id}: resolution does not preserve expected treatment"))
            for element in bound:
                if candidate_id not in element.get("source_candidate_ids", []):
                    blockers.append(_issue("V63_SCENE_SOURCE_INVALID", slide_id, f"{candidate_id}: bound element lacks reverse census reference"))
        extra_resolutions = set(resolutions) - set(candidate_by_id)
        if extra_resolutions:
            blockers.append(_issue("V63_SCENE_SOURCE_INVALID", slide_id, f"unknown candidate resolutions: {sorted(extra_resolutions)}"))
    return {
        "schema_version": SCHEMA_VERSION,
        "deconstruction_runtime_revision": RUNTIME_REVISION,
        "ok": not blockers,
        "status": "pass" if not blockers else "blocked",
        "element_count": element_count,
        "blockers": blockers,
    }


def validate_and_write_scene_graph(
    project_dir: str | Path, scene_graph: dict[str, Any]
) -> dict[str, Any]:
    project = Path(project_dir).resolve()
    scene_graph = deepcopy(scene_graph)
    report = validate_scene_graph(project, scene_graph)
    _write_json_atomic(project / ".build" / "v63_scene_graph_report.json", report)
    if report["ok"]:
        for page in scene_graph['pages'].values():
            page['elements'] = [normalize_element_geometry(e) for e in page['elements']]
        _write_json_atomic(project / ".build" / "v63_scene_graph.json", scene_graph)
    return report
