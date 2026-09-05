from __future__ import annotations

import importlib.util
import json
import re
from copy import deepcopy
from pathlib import Path
from typing import Any


SCHEMA_VERSION = "6.3"
RUNTIME_REVISION = "6.3.1"
_SHAPE_TYPES = {"rect": 1, "round_rect": 5, "ellipse": 9}
_ALIGNMENTS = {"left": 1, "center": 2, "right": 3, "justify": 4}
_VERTICAL = {"top": 1, "middle": 3, "center": 3, "bottom": 4}


def _load(name: str):
    path = Path(__file__).with_name(f"{name}.py")
    spec = importlib.util.spec_from_file_location(f"v63_windows_{name}", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _read_json(path: Path) -> dict[str, Any] | list[Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json_atomic(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    temporary.replace(path)


def _colorref(value: str) -> int:
    normalized = value.lstrip("#")
    red, green, blue = (int(normalized[index : index + 2], 16) for index in (0, 2, 4))
    return red + green * 256 + blue * 65536


def _map_point(
    point: list[float], body_roi_px: list[float], body_roi_in: list[float]
) -> list[float]:
    x, y = [float(value) for value in point]
    body_x, body_y, body_width, body_height = [float(value) for value in body_roi_px]
    slide_x, slide_y, slide_width, slide_height = [float(value) for value in body_roi_in]
    return [
        slide_x + (x - body_x) / body_width * slide_width,
        slide_y + (y - body_y) / body_height * slide_height,
    ]


def render_plan(page: dict[str, Any], body_roi_in: list[float]) -> list[dict[str, Any]]:
    body_roi_px = page["body_roi_px"]
    mapper = _load("v63_scene_graph")
    plan: list[dict[str, Any]] = []
    for element in sorted(page.get("elements", []), key=lambda item: item.get("z_order", 0)):
        if element.get("type") == "group":
            continue
        command = mapper.normalize_element_geometry(element)
        command["bbox_in"] = mapper.pixel_box_to_slide_box(
            command["bbox_px"], body_roi_px, body_roi_in,
            coordinate_mode=page.get('coordinate_mode', 'legacy_stretch'),
            allow_line=command['type'] in {'line', 'connector', 'arrow'} or not command.get('closed', True),
        )
        if isinstance(command.get("points_px"), list):
            command["points_in"] = [
                [round(value, 4) for value in (
                    mapper.map_source_point(point, mapper.body_contain_transform(body_roi_px, body_roi_in))
                    if page.get('coordinate_mode') == 'source_pixels_contain'
                    else _map_point(point, body_roi_px, body_roi_in))]
                for point in command["points_px"]
            ]
        plan.append(command)
    return plan


def _apply_fill_and_line(shape, style: dict[str, Any]) -> None:
    fill = style.get("fill")
    if fill in {None, "none"}:
        shape.Fill.Visible = 0
    else:
        shape.Fill.Visible = -1
        shape.Fill.Solid()
        shape.Fill.ForeColor.RGB = _colorref(str(fill))
        if style.get("transparency") is not None:
            shape.Fill.Transparency = float(style["transparency"])
    line = style.get("line")
    if line in {None, "none"}:
        shape.Line.Visible = 0
    else:
        shape.Line.Visible = -1
        shape.Line.ForeColor.RGB = _colorref(str(line))
        shape.Line.Weight = float(style.get("line_width", 0.8))
        if style.get("dash") is not None:
            shape.Line.DashStyle = int(style["dash"])


def _clear_effects(shape) -> None:
    operations = (
        lambda: setattr(shape.Shadow, "Visible", 0),
        lambda: setattr(shape.Reflection, "Type", 0),
        lambda: setattr(shape.Glow, "Radius", 0),
        lambda: setattr(shape.SoftEdge, "Radius", 0),
        lambda: setattr(shape.ThreeD, "Visible", 0),
    )
    for operation in operations:
        try:
            operation()
        except Exception:
            pass


def _render_text(slide, command: dict[str, Any]):
    x, y, width, height = [value * 72.0 for value in command["bbox_in"]]
    style = command.get("style", {})
    shape = slide.Shapes.AddTextbox(1, x, y, width, height)
    _apply_fill_and_line(shape, style)
    frame = shape.TextFrame2
    frame.AutoSize = 0
    frame.WordWrap = -1 if style.get('word_wrap', True) else 0
    margin = float(style.get("margin", 1.5))
    frame.MarginLeft = float(style.get("margin_left", margin))
    frame.MarginRight = float(style.get("margin_right", margin))
    frame.MarginTop = float(style.get("margin_top", 0.8))
    frame.MarginBottom = float(style.get("margin_bottom", 0.8))
    frame.VerticalAnchor = _VERTICAL.get(str(style.get("valign", "top")).lower(), 1)
    runs = command.get("runs") if isinstance(command.get("runs"), list) else None
    value = "".join(str(run.get("text", "")) for run in runs) if runs is not None else str(command.get("text", ""))
    value = value.replace("\n", "\r")
    text_range = frame.TextRange
    text_range.Text = value
    text_range.ParagraphFormat.Alignment = _ALIGNMENTS.get(str(style.get("align", "left")).lower(), 1)
    font = text_range.Font
    font.Name = str(style.get("font_name", "Microsoft YaHei"))
    try:
        font.NameFarEast = str(style.get("font_name", "Microsoft YaHei"))
    except Exception:
        pass
    font.Size = float(style.get("font_size", 10.0))
    font.Bold = -1 if style.get("bold") else 0
    font.Fill.ForeColor.RGB = _colorref(str(style.get("color", "#111111")))
    run_fonts = []
    if runs is not None:
        offset = 1
        for run in runs:
            run_text = str(run.get("text", "")).replace("\n", "\r")
            if not run_text:
                continue
            run_style = {**style, **(run.get("style", {}) if isinstance(run.get("style"), dict) else {})}
            # Characters is an indexed COM property, not the default member of
            # the object obtained by evaluating .Characters without arguments.
            import pythoncom
            import win32com.client
            length = len(run_text.encode('utf-16-le')) // 2
            dispatch_id = text_range._oleobj_.GetIDsOfNames('Characters')
            target = win32com.client.Dispatch(text_range._oleobj_.InvokeTypes(
                dispatch_id, 0, pythoncom.DISPATCH_PROPERTYGET,
                (pythoncom.VT_DISPATCH, 0), ((pythoncom.VT_I4, 1), (pythoncom.VT_I4, 1)), offset, length))
            target.Font.Name = str(run_style.get("font_name", "Microsoft YaHei"))
            try:
                target.Font.NameFarEast = str(run_style.get("font_name", "Microsoft YaHei"))
            except Exception:
                pass
            target.Font.Size = float(run_style.get("font_size", 10.0))
            target.Font.Bold = -1 if run_style.get("bold") else 0
            target.Font.Fill.ForeColor.RGB = _colorref(str(run_style.get("color", "#111111")))
            run_fonts.append(target.Font)
            offset += length
    if style.get('fit') == 'shrink_to_box':
        # Opt-in BODY-only fit. Preserve explicit line breaks and box geometry;
        # one native metric measurement and one scale application, never a loop.
        frame.WordWrap = 0
        available_w = max(0.1, width - frame.MarginLeft - frame.MarginRight)
        available_h = max(0.1, height - frame.MarginTop - frame.MarginBottom)
        factor = min(1.0, available_w / max(0.1, text_range.BoundWidth),
                     available_h / max(0.1, text_range.BoundHeight))
        if factor < 1:
            factor *= 0.98
            for target_font in run_fonts or [font]:
                target_font.Size = float(target_font.Size) * factor
        shape.Tags.Add('V63_TEXT_FIT_SCALE', str(round(factor, 4)))
    return shape


def _render_shape(slide, command: dict[str, Any]):
    x, y, width, height = [value * 72.0 for value in command["bbox_in"]]
    shape = slide.Shapes.AddShape(_SHAPE_TYPES[command["type"]], x, y, width, height)
    _apply_fill_and_line(shape, command.get("style", {}))
    return shape


def _render_line(slide, command: dict[str, Any]):
    points = command.get("points_in")
    if isinstance(points, list) and len(points) > 2:
        shape = _render_freeform(slide, {**command, 'closed': False})
        if command['type'] == 'arrow' or command.get('style', {}).get('arrow_end'):
            shape.Line.EndArrowheadStyle = int(command.get('style', {}).get('arrowhead', 3))
        return shape
    if not isinstance(points, list) or len(points) < 2:
        x, y, width, height = command["bbox_in"]
        points = [[x, y], [x + width, y + height]]
    start, end = points[0], points[-1]
    shape = slide.Shapes.AddLine(
        start[0] * 72.0, start[1] * 72.0, end[0] * 72.0, end[1] * 72.0
    )
    style = command.get("style", {})
    shape.Line.Visible = -1
    shape.Line.ForeColor.RGB = _colorref(str(style.get("line", "#111111")))
    shape.Line.Weight = float(style.get("line_width", 1.0))
    if style.get("dash") is not None:
        shape.Line.DashStyle = int(style["dash"])
    if command["type"] == "arrow" or style.get("arrow_end"):
        shape.Line.EndArrowheadStyle = int(style.get("arrowhead", 3))
    if style.get("arrow_start"):
        shape.Line.BeginArrowheadStyle = int(style.get("arrowhead", 3))
    return shape


def _render_freeform(slide, command: dict[str, Any]):
    points = command.get("points_in")
    if not isinstance(points, list) or len(points) < (3 if command.get('closed', True) else 2):
        raise ValueError(f"V63_FREEFORM_POINTS_INVALID: {command.get('element_id')}")
    scaled = [[point[0] * 72.0, point[1] * 72.0] for point in points]
    builder = slide.Shapes.BuildFreeform(1, scaled[0][0], scaled[0][1])
    for point in scaled[1:]:
        builder.AddNodes(0, 1, point[0], point[1])
    if command.get('closed', True) and scaled[-1] != scaled[0]:
        builder.AddNodes(0, 1, scaled[0][0], scaled[0][1])
    shape = builder.ConvertToShape()
    _apply_fill_and_line(shape, command.get("style", {}))
    style = command.get('style', {})
    if style.get('arrow_end'):
        shape.Line.EndArrowheadStyle = int(style.get('arrowhead', 3))
    if style.get('arrow_start'):
        shape.Line.BeginArrowheadStyle = int(style.get('arrowhead', 3))
    return shape


def _render_picture(slide, command: dict[str, Any], asset_path: Path):
    x, y, width, height = [value * 72.0 for value in command["bbox_in"]]
    shape = slide.Shapes.AddPicture(str(asset_path), 0, -1, x, y, width, height)
    shape.Line.Visible = 0
    return shape


def _render_command(slide, command: dict[str, Any], assets: dict[str, Path]):
    kind = command["type"]
    if kind == "text":
        shape = _render_text(slide, command)
    elif kind in _SHAPE_TYPES:
        shape = _render_shape(slide, command)
    elif kind in {"line", "connector", "arrow"}:
        shape = _render_line(slide, command)
    elif kind == "freeform":
        shape = _render_freeform(slide, command)
    elif kind == "image_crop":
        asset_id = command["asset_id"]
        if asset_id not in assets:
            raise ValueError(f"V63_ASSET_MISSING: {asset_id}")
        shape = _render_picture(slide, command, assets[asset_id])
    else:
        raise ValueError(f"V63_SCENE_TYPE_INVALID: {kind}")
    shape.Name = f"V63_{command['element_id']}"
    if command.get("style", {}).get("rotation") is not None:
        shape.Rotation = float(command["style"]["rotation"])
    _clear_effects(shape)
    return shape


def _skeleton_values(slide: dict[str, Any], page_number: int) -> dict[str, str]:
    raw_points = slide.get("core_points", [])
    if isinstance(raw_points, str):
        raw_points = [raw_points]
    points = []
    for point in raw_points if isinstance(raw_points, list) else []:
        text = re.sub(r"^(?:[■▪▫•●□]\s*)+", "", str(point).strip()).strip()
        points.append(text)
    return {
        "chapter": str(slide.get("chapter", "")),
        "page_title": str(slide.get("title", slide.get("page_title", ""))),
        "core_judgment": "\r".join(points),
        "source": str(slide.get("source", "")),
        "page_number": str(slide.get("page_number", page_number)),
    }


def _remove_body_shapes(slide) -> None:
    allowed_placeholder_types = {1, 2, 7, 13, 15}
    for index in range(int(slide.Shapes.Count), 0, -1):
        shape = slide.Shapes(index)
        try:
            placeholder_type = int(shape.PlaceholderFormat.Type)
        except Exception:
            placeholder_type = None
        if placeholder_type not in allowed_placeholder_types:
            shape.Delete()


def build_deck(
    project_dir: str | Path,
    output_path: str | Path,
    *,
    template_path: str | Path,
) -> dict[str, Any]:
    import pythoncom
    import win32com.client

    project = Path(project_dir).resolve()
    output = Path(output_path).resolve()
    template = Path(template_path).resolve()
    scene_graph = _read_json(project / ".build" / "v63_scene_graph.json")
    slides = _read_json(project / ".build" / "slides.json")
    asset_ledger = _read_json(project / ".build" / "v63_asset_ledger.json")
    if not isinstance(slides, list):
        raise ValueError("V63_SLIDES_INVALID")
    slide_by_id = {str(item.get("slide_id")): item for item in slides if isinstance(item, dict)}
    page_ids = sorted(scene_graph.get("pages", {}))
    if set(page_ids) != set(slide_by_id):
        raise ValueError("V63_SCENE_SLIDE_SET_MISMATCH")
    assets = {
        str(item["asset_id"]): (project / str(item["asset_path"])).resolve()
        for item in asset_ledger.get("assets", [])
        if isinstance(item, dict) and item.get("asset_id") and item.get("asset_path")
    }
    skeleton_module = _load("v63_skeleton_contract")
    skeleton_contract = skeleton_module.read_template_contract(template)
    output.parent.mkdir(parents=True, exist_ok=True)
    if output.is_file():
        output.unlink()
    pythoncom.CoInitialize()
    application = None
    presentation = None
    object_ledger: list[dict[str, Any]] = []
    try:
        application = win32com.client.DispatchEx("PowerPoint.Application")
        presentation = application.Presentations.Open(str(template), WithWindow=False)
        while int(presentation.Slides.Count) < len(page_ids):
            presentation.Slides(int(presentation.Slides.Count)).Duplicate()
        while int(presentation.Slides.Count) > len(page_ids):
            presentation.Slides(int(presentation.Slides.Count)).Delete()
        for page_index, slide_id in enumerate(page_ids, start=1):
            slide = presentation.Slides(page_index)
            _remove_body_shapes(slide)
            skeleton_module.update_com_skeleton(
                slide, _skeleton_values(slide_by_id[slide_id], page_index)
            )
            page = scene_graph["pages"][slide_id]
            for command in render_plan(page, skeleton_contract["body_roi_in"]):
                shape = _render_command(slide, command, assets)
                object_ledger.append(
                    {
                        "slide_id": slide_id,
                        "element_id": command["element_id"],
                        "shape_name": str(shape.Name),
                        "type": command["type"],
                        "bbox_in": [round(float(shape.Left) / 72.0, 4), round(float(shape.Top) / 72.0, 4), round(float(shape.Width) / 72.0, 4), round(float(shape.Height) / 72.0, 4)],
                        "editable": command["type"] != "image_crop",
                        "asset_id": command.get("asset_id"),
                        "text_fit_scale": str(shape.Tags.Item('V63_TEXT_FIT_SCALE')) if command['type'] == 'text' else None,
                    }
                )
        presentation.SaveAs(str(output), 24)
    finally:
        if presentation is not None:
            presentation.Close()
        if application is not None:
            application.Quit()
        pythoncom.CoUninitialize()
    if not output.is_file():
        raise RuntimeError("V63_POWERPOINT_OUTPUT_MISSING")
    report = {
        "schema_version": SCHEMA_VERSION,
        "deconstruction_runtime_revision": RUNTIME_REVISION,
        "ok": True,
        "pptx": str(output),
        "page_count": len(page_ids),
        "object_count": len(object_ledger),
        "editable_body_count": sum(item["editable"] for item in object_ledger),
        "image_count": sum(not item["editable"] for item in object_ledger),
        "objects": object_ledger,
    }
    _write_json_atomic(project / ".build" / "v63_object_ledger.json", report)
    return report


def render_deck(
    pptx_path: str | Path,
    project_dir: str | Path,
    *,
    expected_page_count: int,
) -> dict[str, Any]:
    """Render V6.3 with native PowerPoint, avoiding external Node dependencies."""

    import pythoncom
    import win32com.client

    pptx = Path(pptx_path).resolve()
    project = Path(project_dir).resolve()
    render_dir = project / ".build" / "rendered" / "current"
    render_dir.mkdir(parents=True, exist_ok=True)
    for stale in render_dir.glob("S*.png"):
        stale.unlink()
    pythoncom.CoInitialize()
    application = None
    presentation = None
    images: list[str] = []
    try:
        application = win32com.client.DispatchEx("PowerPoint.Application")
        presentation = application.Presentations.Open(str(pptx), False, True, False)
        if int(presentation.Slides.Count) != int(expected_page_count):
            raise ValueError(
                f"V63_RENDER_PAGE_COUNT_MISMATCH: expected {expected_page_count}, "
                f"got {presentation.Slides.Count}"
            )
        for index in range(1, expected_page_count + 1):
            destination = render_dir / f"S{index:02d}.png"
            presentation.Slides(index).Export(str(destination), "PNG", 1600, 900)
            if not destination.is_file() or destination.stat().st_size <= 0:
                raise RuntimeError(f"V63_RENDER_INVALID: {destination}")
            images.append(destination.name)
    finally:
        if presentation is not None:
            presentation.Close()
        if application is not None:
            application.Quit()
        pythoncom.CoUninitialize()
    report = {
        "schema_version": SCHEMA_VERSION,
        "deconstruction_runtime_revision": RUNTIME_REVISION,
        "ok": True,
        "status": "pass",
        "renderer": "powerpoint_windows_com",
        "visual_verification": True,
        "images": images,
        "output_dir": str(render_dir),
    }
    _write_json_atomic(project / ".build" / "v63_render_report.json", report)
    return report
