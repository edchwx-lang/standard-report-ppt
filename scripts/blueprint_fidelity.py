from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
from typing import Iterable

from PIL import Image, ImageChops, ImageFilter, ImageOps, ImageStat


DEFAULT_BODY_BOUNDS = (0.025, 0.27, 0.975, 0.90)
DEFAULT_CANONICAL_SIZE = (960, 540)
DEFAULT_GRID_SIZE = (64, 36)
DEFAULT_INK_THRESHOLD = 35
DEFAULT_BLUR_RADIUS = 12
MIN_INK_DENSITY = 0.015
MIN_LAYOUT_SCORE = 0.38
MIN_MASS_RATIO = 0.55
MIN_SCORE = 0.45


def sha256_file(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _is_widescreen(size: tuple[int, int], tolerance: float = 0.04) -> bool:
    width, height = size
    return width > 0 and height > 0 and abs(width / height - 16 / 9) <= tolerance


def _rgb_on_white(source: Image.Image) -> Image.Image:
    image = ImageOps.exif_transpose(source)
    if image.mode in {"RGBA", "LA"} or "transparency" in image.info:
        rgba = image.convert("RGBA")
        white = Image.new("RGBA", rgba.size, "white")
        white.alpha_composite(rgba)
        return white.convert("RGB")
    return image.convert("RGB")


def _body_crop(image: Image.Image, bounds: tuple[float, float, float, float]) -> Image.Image:
    left, top, right, bottom = bounds
    if not (0 <= left < right <= 1 and 0 <= top < bottom <= 1):
        raise ValueError(f"invalid normalized body bounds: {bounds}")
    width, height = image.size
    return image.crop((int(left * width), int(top * height), int(right * width), int(bottom * height)))


def _layout_vector(
    path: str | Path,
    *,
    body_box: tuple[float, float, float, float],
    canonical_size: tuple[int, int],
    grid_size: tuple[int, int],
    ink_threshold: int,
    blur_radius: int,
) -> tuple[list[float], float, bool]:
    with Image.open(path) as source:
        original_size = source.size
        body = _body_crop(_rgb_on_white(source), body_box)
    body = ImageOps.fit(body, canonical_size, method=Image.Resampling.LANCZOS)
    red, green, blue = body.split()
    minimum_channel = ImageChops.darker(ImageChops.darker(red, green), blue)
    ink = ImageOps.invert(minimum_channel)
    binary = ink.point(lambda value: 255 if value >= ink_threshold else 0)
    ink_density = ImageStat.Stat(binary).mean[0] / 255.0
    low_frequency = binary.filter(ImageFilter.GaussianBlur(blur_radius))
    grid = low_frequency.resize(grid_size, Image.Resampling.BOX)
    vector = [value / 255.0 for value in grid.tobytes()]
    return vector, ink_density, _is_widescreen(original_size)


def _soft_iou(first: list[float], second: list[float]) -> float:
    union = sum(max(a, b) for a, b in zip(first, second))
    if union <= 1e-12:
        return 0.0
    return sum(min(a, b) for a, b in zip(first, second)) / union


def _cosine(first: list[float], second: list[float]) -> float:
    numerator = sum(a * b for a, b in zip(first, second))
    first_norm = math.sqrt(sum(value * value for value in first))
    second_norm = math.sqrt(sum(value * value for value in second))
    if first_norm <= 1e-12 or second_norm <= 1e-12:
        return 0.0
    return numerator / (first_norm * second_norm)


def _mass_ratio(first: list[float], second: list[float]) -> float:
    first_mass = sum(first)
    second_mass = sum(second)
    maximum = max(first_mass, second_mass)
    return min(first_mass, second_mass) / maximum if maximum > 1e-12 else 0.0


def compare_slide(
    blueprint_path: str | Path,
    rendered_path: str | Path,
    *,
    body_box: tuple[float, float, float, float] = DEFAULT_BODY_BOUNDS,
    canonical_size: tuple[int, int] = DEFAULT_CANONICAL_SIZE,
    grid_size: tuple[int, int] = DEFAULT_GRID_SIZE,
    ink_threshold: int = DEFAULT_INK_THRESHOLD,
    blur_radius: int = DEFAULT_BLUR_RADIUS,
    min_layout_score: float = MIN_LAYOUT_SCORE,
    min_mass_ratio: float = MIN_MASS_RATIO,
    min_score: float = MIN_SCORE,
) -> dict:
    blueprint_vector, blueprint_density, blueprint_widescreen = _layout_vector(
        blueprint_path,
        body_box=body_box,
        canonical_size=canonical_size,
        grid_size=grid_size,
        ink_threshold=ink_threshold,
        blur_radius=blur_radius,
    )
    render_vector, render_density, render_widescreen = _layout_vector(
        rendered_path,
        body_box=body_box,
        canonical_size=canonical_size,
        grid_size=grid_size,
        ink_threshold=ink_threshold,
        blur_radius=blur_radius,
    )
    soft_iou = _soft_iou(blueprint_vector, render_vector)
    cosine = _cosine(blueprint_vector, render_vector)
    layout_score = 0.65 * soft_iou + 0.35 * cosine
    mass_ratio = _mass_ratio(blueprint_vector, render_vector)
    score = 0.75 * layout_score + 0.25 * mass_ratio
    aspect_valid = blueprint_widescreen and render_widescreen
    density_valid = blueprint_density >= MIN_INK_DENSITY and render_density >= MIN_INK_DENSITY
    passed = (
        aspect_valid
        and density_valid
        and layout_score >= min_layout_score
        and mass_ratio >= min_mass_ratio
        and score >= min_score
    )
    return {
        "passed": passed,
        "score": round(score, 4),
        "layout_score": round(layout_score, 4),
        "soft_iou": round(soft_iou, 4),
        "cosine": round(cosine, 4),
        "ink_mass_ratio": round(mass_ratio, 4),
        "blueprint_ink_density": round(blueprint_density, 4),
        "render_ink_density": round(render_density, 4),
        "aspect_ratio_valid": aspect_valid,
        "threshold": min_score,
        "thresholds": {
            "minimum_ink_density": MIN_INK_DENSITY,
            "minimum_layout_score": min_layout_score,
            "minimum_ink_mass_ratio": min_mass_ratio,
            "minimum_score": min_score,
        },
        "blueprint_sha256": sha256_file(blueprint_path),
        "render_sha256": sha256_file(rendered_path),
    }


def compare_deck(
    pairs: Iterable[tuple[str, str | Path, str | Path]],
    *,
    expected_page_count: int | None = None,
) -> dict:
    pages = [
        {"slide_id": slide_id, **compare_slide(blueprint, render)}
        for slide_id, blueprint, render in pairs
    ]
    count_matches = expected_page_count is None or len(pages) == expected_page_count
    failed = [page["slide_id"] for page in pages if not page["passed"]]
    if not count_matches:
        failed.append("PAGE_COUNT_MISMATCH")
    return {
        "schema_version": "5.6",
        "passed": bool(pages) and count_matches and not failed,
        "page_count": len(pages),
        "expected_page_count": expected_page_count,
        "failed_slide_ids": failed,
        "pages": pages,
    }


def compare_project(
    pairs: Iterable[tuple[str, str | Path, str | Path]],
    output_path: str | Path,
    *,
    expected_page_count: int | None = None,
) -> dict:
    payload = compare_deck(pairs, expected_page_count=expected_page_count)
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_suffix(output.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(output)
    return payload


def main() -> None:
    parser = argparse.ArgumentParser(description="Compare blueprint and rendered body-layout structure.")
    parser.add_argument("blueprint", type=Path)
    parser.add_argument("render", type=Path)
    args = parser.parse_args()
    result = compare_slide(args.blueprint, args.render)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    raise SystemExit(0 if result["passed"] else 2)


if __name__ == "__main__":
    main()
