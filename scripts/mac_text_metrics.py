from __future__ import annotations

import re
import sys
from pathlib import Path
from typing import Mapping, NamedTuple, Sequence

from PIL import ImageFont

try:
    from fontTools.ttLib import TTCollection, TTFont
except ImportError:
    vendor = Path(__file__).resolve().parents[1] / "assets" / "vendor" / "fonttools-4.63.0-py3.zip"
    if vendor.is_file():
        sys.path.insert(0, str(vendor))
    from fontTools.ttLib import TTCollection, TTFont


class ResolvedFont(NamedTuple):
    name: str
    path: Path
    face_index: int
    fallback_used: bool


class TextMeasurement(NamedTuple):
    measurement_backend: str
    font_resolved: str
    lines: tuple[str, ...]
    predicted_height_pt: float
    allocated_height_pt: float
    safety_margin_ratio: float


FontLocation = str | Path | tuple[str | Path, int]


def build_font_catalog(search_roots: Sequence[str | Path] | None = None) -> dict[str, tuple[Path, int]]:
    roots = (
        [Path("/System/Library/Fonts"), Path("/Library/Fonts"), Path.home() / "Library" / "Fonts"]
        if search_roots is None else [Path(root) for root in search_roots]
    )
    catalog: dict[str, tuple[Path, int]] = {}
    for root in roots:
        if not root.is_dir():
            continue
        for path in sorted(root.rglob("*"), key=lambda item: str(item).casefold()):
            if path.suffix.casefold() not in {".otf", ".ttf", ".ttc"}:
                continue
            fonts = []
            try:
                fonts = list(TTCollection(path, lazy=True).fonts) if path.suffix.casefold() == ".ttc" else [TTFont(path, lazy=True)]
                for face_index, font in enumerate(fonts):
                    for record in font["name"].names:
                        if record.nameID in {1, 4, 6}:
                            try:
                                name = record.toUnicode().strip()
                            except (UnicodeDecodeError, AttributeError):
                                continue
                            if name:
                                catalog.setdefault(name, (path, face_index))
            except (OSError, KeyError):
                continue
            finally:
                for font in fonts:
                    font.close()
    return catalog


def resolve_font(preferred_names: Sequence[str], *, catalog: Mapping[str, FontLocation]) -> ResolvedFont:
    if not preferred_names:
        raise ValueError("preferred_names must not be empty")
    for index, name in enumerate(preferred_names):
        location = catalog.get(name)
        if location is None:
            continue
        raw_path, face_index = location if isinstance(location, tuple) else (location, 0)
        path = Path(raw_path)
        if path.is_file():
            return ResolvedFont(name, path, int(face_index), index > 0)
    raise RuntimeError("no usable Chinese font found")


def _font(font_path: str | Path, font_size_pt: float, font_index: int):
    scale = 4
    return ImageFont.truetype(
        str(font_path), max(1, round(font_size_pt * scale)), index=font_index
    ), scale


def _width(text: str, font, scale: int) -> float:
    left, _, right, _ = font.getbbox(text or " ")
    return (right - left) / scale


def _tokens(text: str) -> list[str]:
    return [token for token in re.findall(r"[A-Za-z0-9][A-Za-z0-9.,%+\-_/]*|\n|[^\S\n]+|.", text) if token]


def wrap_text(
    text: str, *, font_path: str | Path, font_size_pt: float,
    max_width_pt: float, font_index: int = 0,
) -> tuple[str, ...]:
    if max_width_pt <= 0:
        raise ValueError("max_width_pt must be positive")
    font, scale = _font(font_path, font_size_pt, font_index)
    lines: list[str] = []
    current = ""
    for token in _tokens(text):
        if token == "\n":
            lines.append(current.rstrip())
            current = ""
            continue
        candidate = current + token
        if current and _width(candidate, font, scale) > max_width_pt:
            lines.append(current.rstrip())
            current = token.lstrip()
        elif not current and _width(token, font, scale) > max_width_pt:
            for char in token:
                if current and _width(current + char, font, scale) > max_width_pt:
                    lines.append(current)
                    current = char
                else:
                    current += char
        else:
            current = candidate
    if current or not lines:
        lines.append(current.rstrip())
    return tuple(lines)


def measure_text_box(
    text: str, *, font_path: str | Path, resolved_font_name: str,
    font_size_pt: float, max_width_pt: float, font_index: int = 0,
    line_spacing: float = 1.15, paragraph_after_pt: float = 0.0,
    margin_top_pt: float = 0.0, margin_bottom_pt: float = 0.0,
    safety_margin_ratio: float = 1.10,
) -> TextMeasurement:
    if safety_margin_ratio < 1:
        raise ValueError("safety_margin_ratio must be at least 1.0")
    lines = wrap_text(
        text, font_path=font_path, font_index=font_index,
        font_size_pt=font_size_pt, max_width_pt=max_width_pt,
    )
    predicted = (
        len(lines) * font_size_pt * line_spacing
        + max(0, text.count("\n")) * paragraph_after_pt
        + margin_top_pt + margin_bottom_pt
    )
    return TextMeasurement(
        "pillow_font_metrics", resolved_font_name, lines,
        round(predicted, 3), round(predicted * safety_margin_ratio, 3),
        safety_margin_ratio,
    )
