"""Turn a complete ImageGen draft into the deterministic V5.5 consulting blueprint."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


CANVAS_W, CANVAS_H = 1600, 900
LEFT, RIGHT = 68, 1532
CHAPTER_TOP, CHAPTER_H = 19, 54
TITLE_TOP, TITLE_H = 71, 48
CORE_TOP = 128
FOOTER_TOP = 864
NAVY = "#1E386B"
BLACK = "#000000"
WHITE = "#FFFFFF"
GRAY = "#666666"


def sha256_file(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _font(size: int, bold: bool = False):
    names = ["msyhbd.ttc", "msyh.ttc"] if bold else ["msyh.ttc", "msyhbd.ttc"]
    for name in names:
        path = Path("C:/Windows/Fonts") / name
        if path.is_file():
            return ImageFont.truetype(str(path), size=size)
    return ImageFont.load_default()


def _wrap(text: str, font, max_width: int) -> list[str]:
    lines: list[str] = []
    current = ""
    probe = ImageDraw.Draw(Image.new("RGB", (1, 1)))
    for char in text:
        candidate = current + char
        if current and probe.textbbox((0, 0), candidate, font=font)[2] > max_width:
            lines.append(current)
            current = char
        else:
            current = candidate
    if current:
        lines.append(current)
    return lines or [""]


def _dashed_rectangle(draw: ImageDraw.ImageDraw, box, color=BLACK, width=2, dash=10, gap=7):
    left, top, right, bottom = box
    for start in range(left, right, dash + gap):
        draw.line((start, top, min(start + dash, right), top), fill=color, width=width)
        draw.line((start, bottom, min(start + dash, right), bottom), fill=color, width=width)
    for start in range(top, bottom, dash + gap):
        draw.line((left, start, left, min(start + dash, bottom)), fill=color, width=width)
        draw.line((right, start, right, min(start + dash, bottom)), fill=color, width=width)


def has_forbidden_top_rule(image: Image.Image) -> bool:
    """Return True for a long navy/blue rule above the chapter title."""
    rgb = image.convert("RGB")
    for y in range(0, CHAPTER_TOP):
        blue_pixels = 0
        for x in range(CANVAS_W):
            red, green, blue = rgb.getpixel((x, y))
            if blue > red * 1.15 and blue > green * 1.05 and blue > 55:
                blue_pixels += 1
        if blue_pixels >= int(CANVAS_W * 0.45):
            return True
    return False


def compose_blueprint(source_path: str | Path, output_path: str | Path, spec: dict) -> dict:
    source = Image.open(source_path).convert("RGB")
    if abs(source.width / source.height - 16 / 9) > 0.03:
        raise ValueError("source blueprint must use a 16:9 aspect ratio")
    canvas = Image.new("RGB", (CANVAS_W, CANVAS_H), WHITE)
    draw = ImageDraw.Draw(canvas)
    chapter_font = _font(38, True)
    title_font = _font(30, True)
    core_font = _font(23, False)
    source_font = _font(15, False)

    draw.text((LEFT, CHAPTER_TOP), spec["chapter"], font=chapter_font, fill=NAVY)
    draw.rectangle((LEFT, TITLE_TOP, RIGHT, TITLE_TOP + TITLE_H), fill=NAVY)
    draw.text((LEFT, TITLE_TOP + 6), spec["title"], font=title_font, fill=WHITE)

    core_lines: list[str] = []
    for point in spec.get("core_points", []):
        wrapped = _wrap("■ " + point, core_font, RIGHT - LEFT - 24)
        core_lines.extend(wrapped)
    line_height = 34
    core_height = max(72, 20 + line_height * len(core_lines))
    core_bottom = CORE_TOP + core_height
    _dashed_rectangle(draw, (LEFT, CORE_TOP, RIGHT, core_bottom), width=2)
    for index, line in enumerate(core_lines):
        draw.text((LEFT, CORE_TOP + 10 + index * line_height), line, font=core_font, fill=BLACK)

    body_top = core_bottom + 14
    body_bottom = FOOTER_TOP - 14
    source_crop_top = int(source.height * 0.29)
    source_crop_bottom = int(source.height * 0.91)
    body = source.crop((0, source_crop_top, source.width, max(source_crop_top + 1, source_crop_bottom)))
    target_size = (RIGHT - LEFT, body_bottom - body_top)
    body.thumbnail(target_size, Image.Resampling.LANCZOS)
    paste_x = LEFT + (target_size[0] - body.width) // 2
    paste_y = body_top + (target_size[1] - body.height) // 2
    canvas.paste(body, (paste_x, paste_y))

    draw.rectangle((0, FOOTER_TOP - 5, CANVAS_W, CANVAS_H), fill=WHITE)
    draw.text((LEFT, FOOTER_TOP), spec.get("source", ""), font=source_font, fill=GRAY)
    page_text = str(spec.get("page_number", ""))
    page_width = draw.textbbox((0, 0), page_text, font=source_font)[2]
    draw.text((RIGHT - page_width, FOOTER_TOP), page_text, font=source_font, fill=BLACK)

    destination = Path(output_path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(destination)
    record = {
        "schema_version": "5.5",
        "complete_slide_reference": True,
        "raw_input_role": "complete_slide_draft",
        "output": str(destination),
        "anchors": {"chapter_left": LEFT, "title_left": LEFT, "core_left": LEFT},
        "tops_px": {"chapter": CHAPTER_TOP, "title": TITLE_TOP, "core": CORE_TOP},
        "body_roi": [LEFT, body_top, RIGHT, body_bottom],
        "forbidden_top_rule": has_forbidden_top_rule(canvas),
        "output_sha256": sha256_file(destination),
    }
    destination.with_suffix(".composition.json").write_text(
        json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return record


def main() -> None:
    parser = argparse.ArgumentParser(description="Compose a complete ImageGen page draft onto the V5.5 fixed skeleton.")
    parser.add_argument("source", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--spec", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(compose_blueprint(args.source, args.output, json.loads(args.spec.read_text(encoding="utf-8"))), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
