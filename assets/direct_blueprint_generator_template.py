"""V5.6 manifest-compiled fast/Direct Blueprint whole-deck generator template.

Copy this file to <project>/generate_deck.py, embed all canonical content and
page-specific builders in that one file, and keep the accepted blueprints in
<project>/blueprints. The final project must not contain per-page Python files.
"""

from __future__ import annotations

import math
import re
import argparse
import hashlib
from pathlib import Path


DECK_META = {
    "schema_version": "__PROJECT_SCHEMA_VERSION__",
    "production_mode": "__PRODUCTION_MODE__",
    "page_count": 0,  # __PAGE_COUNT__
    "slide_size": "16:9",
    "template_path": "__COMPANY_TEMPLATE_PATH__",
    "template_sha256": "__COMPANY_TEMPLATE_SHA256__",
}
SLIDES = []
BLUEPRINTS = {}
ASSET_CROPS = {}
PAGE_SPECS = {}


NAVY = 0x6B381E  # PowerPoint COM uses BGR integers: RGB #1E386B.
BLUE = 0xC59973  # RGB #7399C5.
LIGHT_BLUE = 0xF2E9DD
LIGHT_GRAY = 0xD9D9D9
DARK_RED = 0x0000C0
BLACK = 0x000000
WHITE = 0xFFFFFF
FONT_NAME = "Microsoft YaHei"

SLIDE_W = 13.333333
SLIDE_H = 7.5
LEFT = 0.56
RIGHT = 12.76
CM_PER_INCH = 2.54
CHAPTER_TOP = 0.4 / CM_PER_INCH
CHAPTER_H = 0.46
TITLE_TOP = 1.5 / CM_PER_INCH
TITLE_H = 0.39
CORE_TOP = 2.7 / CM_PER_INCH
FOOTER_TOP = 7.215
BODY_BOTTOM = 7.02


def inches(value: float) -> float:
    return value * 72.0


def rgb(hex_value: str) -> int:
    clean = hex_value.lstrip("#")
    red, green, blue = int(clean[:2], 16), int(clean[2:4], 16), int(clean[4:], 16)
    return red | (green << 8) | (blue << 16)


def clear_shape_effects(shape) -> None:
    """Neutralize explicit and theme-inherited visual effects on one shape."""

    # Reflection.Type = 0 alone does not clear some Office theme effectRefs.
    # Applying the neutral built-in style first removes the inherited effect,
    # after which callers set the required fill/line/text formatting.
    try:
        shape.ShapeStyle = 1
    except Exception:
        pass
    try:
        shape.Shadow.Visible = 0
    except Exception:
        pass
    try:
        shape.Reflection.Type = 0
    except Exception:
        pass
    try:
        shape.Glow.Radius = 0
    except Exception:
        pass
    try:
        shape.SoftEdge.Radius = 0
    except Exception:
        pass
    try:
        shape.ThreeD.Visible = 0
    except Exception:
        pass


def _shape_has_forbidden_effect(shape) -> bool:
    checks = []
    try:
        checks.append(int(shape.Shadow.Visible) != 0)
    except Exception:
        pass
    try:
        checks.append(int(shape.Reflection.Type) != 0)
    except Exception:
        pass
    try:
        checks.append(float(shape.Glow.Radius) > 0)
    except Exception:
        pass
    try:
        checks.append(float(shape.SoftEdge.Radius) > 0)
    except Exception:
        pass
    try:
        checks.append(int(shape.ThreeD.Visible) != 0)
    except Exception:
        pass
    return any(checks)


def _clear_shapes_effects(shapes) -> int:
    cleared = 0
    for index in range(1, shapes.Count + 1):
        shape = shapes(index)
        if _shape_has_forbidden_effect(shape):
            clear_shape_effects(shape)
            cleared += 1
    return cleared


def clear_presentation_effects(presentation) -> dict[str, int]:
    """Clear effects on slides, slide masters, and custom layouts."""

    cleared = 0
    scopes = 0
    for slide_index in range(1, presentation.Slides.Count + 1):
        cleared += _clear_shapes_effects(presentation.Slides(slide_index).Shapes)
        scopes += 1
    designs = getattr(presentation, "Designs", None)
    if designs is not None:
        for design_index in range(1, designs.Count + 1):
            master = designs(design_index).SlideMaster
            cleared += _clear_shapes_effects(master.Shapes)
            scopes += 1
            for layout_index in range(1, master.CustomLayouts.Count + 1):
                layout = master.CustomLayouts(layout_index)
                cleared += _clear_shapes_effects(layout.Shapes)
                scopes += 1
    return {"cleared": cleared, "scopes": scopes}


def _delete_off_canvas_shapes(shapes, slide_width: float, slide_height: float) -> int:
    """Delete shapes wholly outside the slide and return the deletion count."""

    deleted = 0
    for shape_index in range(shapes.Count, 0, -1):
        shape = shapes(shape_index)
        if (
            shape.Left + shape.Width <= 0
            or shape.Top + shape.Height <= 0
            or shape.Left >= slide_width
            or shape.Top >= slide_height
        ):
            shape.Delete()
            deleted += 1
    return deleted


def _delete_tiny_master_artifacts(shapes) -> int:
    """Delete sub-point residual theme objects that are not visible slide content."""

    deleted = 0
    for shape_index in range(shapes.Count, 0, -1):
        shape = shapes(shape_index)
        if float(shape.Width) < 1.0 and float(shape.Height) < 1.0:
            shape.Delete()
            deleted += 1
    return deleted


def remove_off_slide_shapes(slide) -> int:
    """Delete generated pasteboard objects such as left-side palette swatches."""

    return _delete_off_canvas_shapes(slide.Shapes, inches(SLIDE_W), inches(SLIDE_H))


def sanitize_presentation_pasteboard(presentation) -> dict[str, int]:
    """Remove off-canvas objects from slides, masters, and custom layouts."""

    slide_width = float(presentation.PageSetup.SlideWidth)
    slide_height = float(presentation.PageSetup.SlideHeight)
    deleted = 0
    scopes = 0
    for slide_index in range(1, presentation.Slides.Count + 1):
        deleted += _delete_off_canvas_shapes(presentation.Slides(slide_index).Shapes, slide_width, slide_height)
        scopes += 1
    designs = getattr(presentation, "Designs", None)
    if designs is not None:
        for design_index in range(1, designs.Count + 1):
            master = designs(design_index).SlideMaster
            deleted += _delete_off_canvas_shapes(master.Shapes, slide_width, slide_height)
            deleted += _delete_tiny_master_artifacts(master.Shapes)
            scopes += 1
            for layout_index in range(1, master.CustomLayouts.Count + 1):
                layout = master.CustomLayouts(layout_index)
                deleted += _delete_off_canvas_shapes(layout.Shapes, slide_width, slide_height)
                deleted += _delete_tiny_master_artifacts(layout.Shapes)
                scopes += 1
    return {"deleted": deleted, "scopes": scopes}


def visible_character_count(value: str) -> int:
    return len(re.sub(r"\s+", "", value or ""))


def sha256_file(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def estimated_core_height(points: list[str], width: float = RIGHT - LEFT) -> float:
    usable_width_pt = max(1.0, width * 72.0 - 14.0)
    chars_per_line = max(18, int(usable_width_pt / (12.0 * 1.05)))
    lines = sum(max(1, math.ceil(visible_character_count(point) / chars_per_line)) for point in points)
    return max(0.62, 0.18 + lines * (12.0 * 1.20 / 72.0) + max(0, len(points) - 1) * (6.0 / 72.0))


def add_textbox(
    slide,
    text: str,
    x: float,
    y: float,
    w: float,
    h: float,
    *,
    font_size: float,
    color: int = BLACK,
    bold: bool = False,
    align: int = 1,
    valign: int = 3,
    fill: int | None = None,
    line: int | None = None,
    margin_left: float = 0.0,
    margin_right: float = 0.0,
    margin_top: float = 0.0,
    margin_bottom: float = 0.0,
):
    shape = slide.Shapes.AddTextbox(1, inches(x), inches(y), inches(w), inches(h))
    clear_shape_effects(shape)
    if fill is None:
        shape.Fill.Visible = 0
    else:
        shape.Fill.Visible = -1
        shape.Fill.Solid()
        shape.Fill.ForeColor.RGB = fill
    if line is None:
        shape.Line.Visible = 0
    else:
        shape.Line.Visible = -1
        shape.Line.ForeColor.RGB = line
        shape.Line.Weight = 1.0
    frame = shape.TextFrame2
    frame.MarginLeft = inches(margin_left)
    frame.MarginRight = inches(margin_right)
    frame.MarginTop = inches(margin_top)
    frame.MarginBottom = inches(margin_bottom)
    frame.WordWrap = -1
    frame.AutoSize = 0
    frame.VerticalAnchor = valign
    text_range = frame.TextRange
    text_range.Text = text
    text_range.Font.Name = FONT_NAME
    text_range.Font.NameFarEast = FONT_NAME
    text_range.Font.Size = font_size
    text_range.Font.Bold = -1 if bold else 0
    text_range.Font.Fill.ForeColor.RGB = color
    text_range.ParagraphFormat.Alignment = align
    return shape


def add_rect(slide, x: float, y: float, w: float, h: float, *, fill: int, line: int | None = None):
    shape = slide.Shapes.AddShape(1, inches(x), inches(y), inches(w), inches(h))
    clear_shape_effects(shape)
    shape.Fill.Visible = -1
    shape.Fill.Solid()
    shape.Fill.ForeColor.RGB = fill
    if line is None:
        shape.Line.Visible = 0
    else:
        shape.Line.Visible = -1
        shape.Line.ForeColor.RGB = line
        shape.Line.Weight = 1.0
    return shape


def add_section_header(
    slide,
    text: str,
    x: float,
    y: float,
    w: float,
    h: float = 0.30,
    *,
    fill: int = NAVY,
):
    """Add a reusable editable navy section header."""

    shape = add_rect(slide, x, y, w, h, fill=fill)
    shape.TextFrame2.MarginLeft = inches(0.08)
    shape.TextFrame2.MarginRight = inches(0.04)
    shape.TextFrame2.MarginTop = 0
    shape.TextFrame2.MarginBottom = 0
    shape.TextFrame2.VerticalAnchor = 3
    text_range = shape.TextFrame2.TextRange
    text_range.Text = text
    text_range.Font.Name = FONT_NAME
    text_range.Font.NameFarEast = FONT_NAME
    text_range.Font.Size = 10.5
    text_range.Font.Bold = -1
    text_range.Font.Fill.ForeColor.RGB = WHITE
    text_range.ParagraphFormat.Alignment = 1
    return shape


def add_text_card(
    slide,
    title: str,
    body_text: str,
    x: float,
    y: float,
    w: float,
    h: float,
    *,
    title_fill: int = NAVY,
    body_fill: int = WHITE,
):
    """Add a compact editable card using stable company styling."""

    header_h = min(0.34, max(0.26, h * 0.20))
    border = add_rect(slide, x, y, w, h, fill=body_fill, line=BLUE)
    add_section_header(slide, title, x, y, w, header_h, fill=title_fill)
    body = add_textbox(
        slide,
        body_text,
        x + 0.10,
        y + header_h + 0.06,
        w - 0.20,
        h - header_h - 0.12,
        font_size=9,
        color=BLACK,
        valign=1,
    )
    return {"border": border, "body": body}


def add_metric_strip(slide, metrics: list[dict], x: float, y: float, w: float, h: float = 0.42):
    """Add equal-width editable metric cells without theme effects."""

    if not metrics:
        return []
    gap = 0.08
    cell_w = (w - gap * (len(metrics) - 1)) / len(metrics)
    shapes = []
    for index, metric in enumerate(metrics):
        left = x + index * (cell_w + gap)
        box = add_rect(slide, left, y, cell_w, h, fill=LIGHT_BLUE, line=BLUE)
        text = f"{metric.get('label', '')}  {metric.get('value', '')}".strip()
        label = add_textbox(
            slide, text, left + 0.05, y + 0.02, cell_w - 0.10, h - 0.04,
            font_size=9, color=metric.get("color", NAVY), bold=True, valign=3, align=2,
        )
        shapes.extend((box, label))
    return shapes


def add_hbar_chart(slide, data: list[dict], x: float, y: float, w: float, h: float):
    """Add a deterministic editable horizontal bar chart."""

    if not data:
        return []
    maximum = max(float(item.get("value", 0)) for item in data) or 1.0
    row_h = h / len(data)
    label_w = min(1.55, w * 0.28)
    bar_w = w - label_w - 0.55
    shapes = []
    for index, item in enumerate(data):
        top = y + index * row_h
        shapes.append(add_textbox(slide, str(item.get("label", "")), x, top, label_w - 0.06, row_h, font_size=8.5, valign=3))
        value = float(item.get("value", 0))
        fill = DARK_RED if item.get("highlight") else item.get("fill", BLUE)
        shapes.append(add_rect(slide, x + label_w, top + row_h * 0.22, bar_w * value / maximum, row_h * 0.56, fill=fill))
        shapes.append(add_textbox(slide, str(item.get("display", item.get("value", ""))), x + label_w + bar_w + 0.06, top, 0.48, row_h, font_size=8.5, color=DARK_RED if item.get("highlight") else BLACK, bold=bool(item.get("highlight")), valign=3))
    return shapes


def add_matrix(slide, headers: list[str], rows: list[list[str]], x: float, y: float, w: float, h: float):
    """Add an editable shape-grid matrix with deterministic row and column sizes."""

    if not headers or not rows:
        return []
    columns = len(headers)
    row_h = h / (len(rows) + 1)
    col_w = w / columns
    shapes = []
    for column, header in enumerate(headers):
        left = x + column * col_w
        shapes.append(add_rect(slide, left, y, col_w, row_h, fill=NAVY, line=WHITE))
        shapes.append(add_textbox(slide, str(header), left + 0.03, y, col_w - 0.06, row_h, font_size=8.5, color=WHITE, bold=True, align=2, valign=3))
    for row_index, row in enumerate(rows, start=1):
        for column in range(columns):
            left = x + column * col_w
            top = y + row_index * row_h
            fill = LIGHT_BLUE if row_index % 2 else WHITE
            shapes.append(add_rect(slide, left, top, col_w, row_h, fill=fill, line=LIGHT_GRAY))
            value = row[column] if column < len(row) else ""
            shapes.append(add_textbox(slide, str(value), left + 0.04, top, col_w - 0.08, row_h, font_size=8.2, align=1, valign=3))
    return shapes


def add_skeleton(slide, spec: dict, page_number: int) -> dict[str, float]:
    """Add the fixed five-layer skeleton and return the measured body rectangle."""

    chapter_shape = add_textbox(
        slide,
        spec["chapter"],
        LEFT,
        CHAPTER_TOP,
        RIGHT - LEFT,
        CHAPTER_H,
        font_size=20,
        color=NAVY,
        bold=True,
        valign=1,
    )
    chapter_shape.Name = "SKEL_CHAPTER"
    title_bar = add_rect(slide, LEFT, TITLE_TOP, RIGHT - LEFT, TITLE_H, fill=NAVY)
    title_bar.Name = "SKEL_TITLE"
    title_bar.TextFrame2.MarginLeft = 0
    title_bar.TextFrame2.MarginRight = 0
    title_bar.TextFrame2.MarginTop = 0
    title_bar.TextFrame2.MarginBottom = 0
    title_bar.TextFrame2.VerticalAnchor = 3
    title_bar.TextFrame2.TextRange.Text = spec["title"]
    title_bar.TextFrame2.TextRange.Font.Name = FONT_NAME
    title_bar.TextFrame2.TextRange.Font.NameFarEast = FONT_NAME
    title_bar.TextFrame2.TextRange.Font.Size = 16
    title_bar.TextFrame2.TextRange.Font.Bold = -1
    title_bar.TextFrame2.TextRange.Font.Fill.ForeColor.RGB = WHITE
    title_bar.TextFrame2.TextRange.ParagraphFormat.Alignment = 1

    points = spec["core_points"]
    core_text = "\r".join(f"\u25A0 {point}" for point in points)
    estimated_height = estimated_core_height(points)
    core_box = add_textbox(
        slide,
        core_text,
        LEFT,
        CORE_TOP,
        RIGHT - LEFT,
        estimated_height,
        font_size=12,
        color=BLACK,
        align=1,
        valign=1,
        fill=WHITE,
        line=BLACK,
        margin_left=0,
        margin_right=0.04,
        margin_top=0.06,
        margin_bottom=0.05,
    )
    core_box.Name = "SKEL_CORE"
    core_box.Line.DashStyle = 4
    core_box.TextFrame.Ruler.Levels(1).FirstMargin = 0
    core_box.TextFrame.Ruler.Levels(1).LeftMargin = inches(0.25)
    legacy_text_range = core_box.TextFrame.TextRange
    paragraph_count = len(points)
    for paragraph_index in range(1, paragraph_count + 1):
        paragraph = legacy_text_range.Paragraphs(paragraph_index, 1)
        paragraph.ParagraphFormat.SpaceAfter = 0 if paragraph_index == paragraph_count else 6
        paragraph.ParagraphFormat.SpaceWithin = 1.2
        paragraph.ParagraphFormat.Alignment = 1
    try:
        measured_text_height = float(core_box.TextFrame2.TextRange.BoundHeight) / 72.0
        core_height = max(0.62, measured_text_height + 0.13)
        core_box.Height = inches(core_height)
    except Exception:
        core_height = estimated_height
    core_bottom = CORE_TOP + core_height
    body_top = core_bottom + 0.12

    source_shape = add_textbox(
        slide,
        spec.get("source", ""),
        LEFT,
        FOOTER_TOP,
        10.5,
        0.18,
        font_size=7.5,
        color=rgb("#666666"),
        valign=1,
    )
    source_shape.Name = "SKEL_SOURCE"
    page_shape = add_textbox(
        slide,
        str(page_number),
        12.27,
        FOOTER_TOP,
        0.43,
        0.18,
        font_size=8,
        color=BLACK,
        align=3,
        valign=1,
    )
    page_shape.Name = "SKEL_PAGE_NUMBER"
    return {
        "left": LEFT,
        "top": body_top,
        "width": RIGHT - LEFT,
        "height": BODY_BOTTOM - body_top,
        "bottom": BODY_BOTTOM,
        "core_bottom": core_bottom,
    }


def contain_rect(image_size: tuple[int, int], target_box_in: list[float]) -> list[float]:
    """Return a centered contain-fit rectangle without changing aspect ratio."""

    image_width, image_height = image_size
    x, y, box_width, box_height = [float(value) for value in target_box_in]
    if image_width <= 0 or image_height <= 0 or box_width <= 0 or box_height <= 0:
        raise ValueError("image and target box dimensions must be positive")
    scale = min(box_width / image_width, box_height / image_height)
    width, height = image_width * scale, image_height * scale
    return [x + (box_width - width) / 2, y + (box_height - height) / 2, width, height]


def add_blueprint_asset(slide, project_dir: Path, slide_id: str, asset_id: str):
    from PIL import Image

    crop_spec = ASSET_CROPS[asset_id]
    if crop_spec["slide_id"] != slide_id:
        raise ValueError(f"asset {asset_id} does not belong to {slide_id}")
    image_path = project_dir / ".build" / "assets" / slide_id / f"{asset_id}.png"
    if not image_path.is_file():
        raise FileNotFoundError(f"run extract_direct_assets.py before building: {image_path}")
    with Image.open(image_path) as image:
        placement = contain_rect(image.size, crop_spec["target_box_in"])
    x, y, w, h = placement
    shape = slide.Shapes.AddPicture(str(image_path), 0, -1, inches(x), inches(y), inches(w), inches(h))
    clear_shape_effects(shape)
    shape.Name = f"ASSET_{asset_id}"
    return shape


def add_line(
    slide,
    x1: float,
    y1: float,
    x2: float,
    y2: float,
    *,
    color: int = NAVY,
    weight: float = 1.0,
    arrow_end: bool = False,
):
    shape = slide.Shapes.AddLine(inches(x1), inches(y1), inches(x2), inches(y2))
    clear_shape_effects(shape)
    shape.Line.ForeColor.RGB = color
    shape.Line.Weight = weight
    if arrow_end:
        shape.Line.EndArrowheadStyle = 3
    return shape


def add_oval(slide, x: float, y: float, w: float, h: float, *, fill: int = WHITE, line: int = BLUE):
    shape = slide.Shapes.AddShape(9, inches(x), inches(y), inches(w), inches(h))
    clear_shape_effects(shape)
    shape.Fill.Visible = -1
    shape.Fill.Solid()
    shape.Fill.ForeColor.RGB = fill
    shape.Line.Visible = -1
    shape.Line.ForeColor.RGB = line
    shape.Line.Weight = 1.0
    return shape


def _spec_color(value, default: int):
    if value is None:
        return default
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        return rgb(value)
    raise ValueError(f"invalid color value: {value!r}")


def _element_box(element: dict, body: dict[str, float]) -> tuple[float, float, float, float]:
    box = element.get("box")
    if not isinstance(box, list) or len(box) != 4:
        raise ValueError("page element requires box=[x,y,w,h]")
    x, y, w, h = [float(item) for item in box]
    if element.get("coord_space", "body") == "body":
        x += body["left"]
        y += body["top"]
    return x, y, w, h


def render_page_spec(slide, page_spec: dict, body: dict[str, float], project_dir: Path, slide_id: str) -> None:
    """Render literal page-specific geometry without choosing or cycling layouts."""

    elements = page_spec.get("elements")
    if not isinstance(elements, list):
        raise ValueError(f"{slide_id}: page spec elements must be a list")
    for index, element in enumerate(elements):
        if not isinstance(element, dict):
            raise ValueError(f"{slide_id}/element[{index}]: must be a mapping")
        kind = element.get("type")
        if kind == "asset":
            add_blueprint_asset(slide, project_dir, slide_id, element["asset_id"])
            continue
        x, y, w, h = _element_box(element, body)
        if kind == "section_header":
            add_section_header(slide, str(element.get("text", "")), x, y, w, h, fill=_spec_color(element.get("fill"), NAVY))
        elif kind == "text":
            add_textbox(
                slide,
                str(element.get("text", "")),
                x,
                y,
                w,
                h,
                font_size=float(element.get("font_size", 9)),
                color=_spec_color(element.get("color"), BLACK),
                bold=bool(element.get("bold", False)),
                align=int(element.get("align", 1)),
                valign=int(element.get("valign", 3)),
                fill=_spec_color(element["fill"], WHITE) if element.get("fill") is not None else None,
                line=_spec_color(element["line"], LIGHT_GRAY) if element.get("line") is not None else None,
                margin_left=float(element.get("margin_left", 0.04)),
                margin_right=float(element.get("margin_right", 0.04)),
                margin_top=float(element.get("margin_top", 0.02)),
                margin_bottom=float(element.get("margin_bottom", 0.02)),
            )
        elif kind == "rect":
            add_rect(slide, x, y, w, h, fill=_spec_color(element.get("fill"), WHITE), line=_spec_color(element["line"], LIGHT_GRAY) if element.get("line") is not None else None)
        elif kind == "oval":
            oval = add_oval(slide, x, y, w, h, fill=_spec_color(element.get("fill"), WHITE), line=_spec_color(element.get("line"), BLUE))
            if element.get("text"):
                oval.TextFrame2.TextRange.Text = str(element["text"])
                oval.TextFrame2.TextRange.Font.Name = FONT_NAME
                oval.TextFrame2.TextRange.Font.NameFarEast = FONT_NAME
                oval.TextFrame2.TextRange.Font.Size = float(element.get("font_size", 10))
                oval.TextFrame2.TextRange.Font.Bold = -1 if element.get("bold", True) else 0
                oval.TextFrame2.TextRange.Font.Fill.ForeColor.RGB = _spec_color(element.get("color"), NAVY)
                oval.TextFrame2.TextRange.ParagraphFormat.Alignment = 2
                oval.TextFrame2.VerticalAnchor = 3
        elif kind in {"line", "arrow"}:
            add_line(slide, x, y, x + w, y + h, color=_spec_color(element.get("color"), NAVY), weight=float(element.get("weight", 1.0)), arrow_end=kind == "arrow")
        elif kind == "text_card":
            add_text_card(slide, str(element.get("title", "")), str(element.get("body", "")), x, y, w, h, title_fill=_spec_color(element.get("title_fill"), NAVY), body_fill=_spec_color(element.get("body_fill"), WHITE))
        elif kind == "metric_strip":
            add_metric_strip(slide, list(element.get("metrics", [])), x, y, w, h)
        elif kind == "hbar_chart":
            add_hbar_chart(slide, list(element.get("data", [])), x, y, w, h)
        elif kind == "matrix":
            add_matrix(slide, list(element.get("headers", [])), list(element.get("rows", [])), x, y, w, h)
        else:
            raise ValueError(f"{slide_id}/element[{index}]: unsupported type {kind!r}")


# __PAGE_BUILDERS__


def validate_spec_evidence(spec: dict) -> None:
    """Fail before PowerPoint opens when canonical evidence mapping is incomplete."""

    slide_id = spec.get("slide_id", "?")
    modules = spec.get("modules")
    if not isinstance(modules, list) or not modules:
        raise ValueError(f"{slide_id}: modules must be non-empty")
    module_ids = {
        module.get("module_id")
        for module in modules
        if isinstance(module, dict) and isinstance(module.get("module_id"), str)
    }
    if spec.get("primary_visual_module_id") not in module_ids:
        raise ValueError(f"{slide_id}: primary_visual_module_id must reference a real module")
    inventory = spec.get("evidence_inventory")
    if not isinstance(inventory, list) or not inventory:
        raise ValueError(f"{slide_id}: evidence_inventory must be non-empty")
    high_priority = 0
    mapped = 0
    for item in inventory:
        if not isinstance(item, dict):
            raise ValueError(f"{slide_id}: every evidence item must be a dictionary")
        priority = item.get("priority")
        module_id = item.get("module_id")
        if priority not in {"must_keep", "supporting", "optional"}:
            raise ValueError(f"{slide_id}: evidence priority is invalid")
        if module_id is not None and module_id not in module_ids:
            raise ValueError(f"{slide_id}: evidence module_id does not reference a real module")
        if priority in {"must_keep", "supporting"}:
            high_priority += 1
            if module_id in module_ids:
                mapped += 1
        if priority == "must_keep" and module_id not in module_ids:
            raise ValueError(f"{slide_id}: must_keep evidence must map to a real module")
    if high_priority and mapped / high_priority < 0.80:
        raise ValueError(f"{slide_id}: must_keep/supporting evidence coverage must be at least 80%")


def validate_embedded_contract(
    slide_ids: list[str] | None = None,
    project_dir: Path | None = None,
) -> list[str]:
    page_count = DECK_META["page_count"]
    expected_ids = [f"S{index:02d}" for index in range(1, page_count + 1)]
    selected_ids = slide_ids or expected_ids
    if any(slide_id not in expected_ids for slide_id in selected_ids):
        raise ValueError(f"unknown slide_ids: {selected_ids}")
    selected_indexes = [expected_ids.index(slide_id) for slide_id in selected_ids]
    if slide_ids is not None and (
        selected_indexes != sorted(selected_indexes)
        or selected_indexes != list(range(selected_indexes[0], selected_indexes[0] + len(selected_indexes)))
    ):
        raise ValueError("slide_ids must follow canonical consecutive order")
    actual_ids = [slide["slide_id"] for slide in SLIDES]
    if actual_ids != expected_ids:
        raise ValueError(f"SLIDES must be ordered exactly as {expected_ids}; got {actual_ids}")
    required_blueprint_ids = expected_ids if slide_ids is None else selected_ids
    if DECK_META["production_mode"] == "blueprint" and not set(required_blueprint_ids).issubset(BLUEPRINTS):
        raise ValueError("BLUEPRINTS must cover every selected slide; final build requires every final slide")
    if DECK_META["production_mode"] == "blueprint":
        for slide_id in required_blueprint_ids:
            record = BLUEPRINTS.get(slide_id)
            if not isinstance(record, dict) or set(record) != {"path", "sha256"}:
                raise ValueError(f"{slide_id}: BLUEPRINTS requires path and sha256")
            if project_dir is not None:
                blueprint = project_dir / record["path"]
                if not blueprint.is_file() or sha256_file(blueprint) != record["sha256"]:
                    raise ValueError(f"{slide_id}: blueprint file/hash mismatch")
        for spec in SLIDES:
            review = spec.get("visual_review")
            visuals = spec.get("complex_visuals")
            if review not in {"extract_declared", "reviewed_no_raster"}:
                raise ValueError(f"{spec['slide_id']}: visual_review must record the blueprint visual inventory decision")
            if not isinstance(visuals, list):
                raise ValueError(f"{spec['slide_id']}: complex_visuals must be a reviewed list")
            if review == "extract_declared" and not visuals:
                raise ValueError(f"{spec['slide_id']}: extract_declared requires at least one complex visual")
            if review == "reviewed_no_raster" and visuals:
                raise ValueError(f"{spec['slide_id']}: reviewed_no_raster requires an empty complex_visuals list")
    if not set(selected_ids).issubset(PAGE_BUILDERS):
        raise ValueError("PAGE_BUILDERS must contain every selected page-specific builder")
    for spec in SLIDES:
        points = spec.get("core_points", [])
        total = sum(visible_character_count(point) for point in points)
        if not 1 <= len(points) <= 2 or not 80 <= total <= 160:
            raise ValueError(f"{spec['slide_id']}: core judgment must be one or two points totaling 80-160 characters")
        if spec.get("density_profile") != "medium":
            raise ValueError(f"{spec['slide_id']}: density_profile must be medium")
        validate_spec_evidence(spec)
    return selected_ids


def build_deck(
    output_path: str | Path | None = None,
    slide_ids: list[str] | None = None,
) -> Path:
    """Build every slide in one PowerPoint COM session and save one PPTX."""

    import win32com.client

    project_dir = Path(__file__).resolve().parent
    selected_ids = validate_embedded_contract(slide_ids, project_dir)
    output = Path(output_path) if output_path else project_dir / "output" / "report.pptx"
    output.parent.mkdir(parents=True, exist_ok=True)
    powerpoint = win32com.client.DispatchEx("PowerPoint.Application")
    template_path = Path(DECK_META["template_path"]).expanduser()
    if not template_path.is_file() or sha256_file(template_path) != DECK_META["template_sha256"]:
        powerpoint.Quit()
        raise ValueError("company template file/hash mismatch")
    presentation = powerpoint.Presentations.Open(str(template_path), False, True, False)
    try:
        sanitize_presentation_pasteboard(presentation)
        clear_presentation_effects(presentation)
        selected_specs = [spec for spec in SLIDES if spec["slide_id"] in selected_ids]
        while presentation.Slides.Count < len(selected_specs):
            presentation.Slides(1).Duplicate()
        while presentation.Slides.Count > len(selected_specs):
            presentation.Slides(presentation.Slides.Count).Delete()
        for page_number, spec in enumerate(selected_specs, start=1):
            slide = presentation.Slides(page_number)
            slide.FollowMasterBackground = 0
            slide.Background.Fill.Visible = -1
            slide.Background.Fill.Solid()
            slide.Background.Fill.ForeColor.RGB = WHITE
            for shape_index in range(slide.Shapes.Count, 0, -1):
                slide.Shapes(shape_index).Delete()
            builder = PAGE_BUILDERS[spec["slide_id"]]
            final_page_number = int(spec["slide_id"][1:])
            builder(
                presentation,
                slide,
                spec,
                add_skeleton(slide, spec, final_page_number),
                project_dir,
            )
            remove_off_slide_shapes(slide)
        sanitize_presentation_pasteboard(presentation)
        clear_presentation_effects(presentation)
        presentation.SaveAs(str(output), 24)
    finally:
        presentation.Close()
        powerpoint.Quit()
    return output


def main() -> None:
    parser = argparse.ArgumentParser(description="Build the full deck or one Direct Blueprint batch.")
    parser.add_argument("--output", type=Path)
    parser.add_argument(
        "--slide-ids",
        help="Comma-separated SNN IDs for a one-to-five-page working batch; omit for the final whole deck",
    )
    args = parser.parse_args()
    slide_ids = [value.strip() for value in args.slide_ids.split(",")] if args.slide_ids else None
    if slide_ids is not None and not 1 <= len(slide_ids) <= 5:
        raise SystemExit("--slide-ids must contain between one and five pages")
    print(build_deck(args.output, slide_ids))


if __name__ == "__main__":
    main()
