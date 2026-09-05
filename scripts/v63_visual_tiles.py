from __future__ import annotations

import hashlib
import importlib.util
import json
import re
from pathlib import Path
from typing import Any

from PIL import Image


SCHEMA_VERSION = "6.3"
RUNTIME_REVISION = "6.3.1"
_SLIDE_ID = re.compile(r"^S\d{2,3}$")


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write_json_atomic(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    temporary.replace(path)


def _load_skeleton_module():
    path = Path(__file__).with_name("v63_skeleton_contract.py")
    spec = importlib.util.spec_from_file_location("v63_visual_tiles_skeleton", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def overlapping_tile_boxes(
    body_roi_px: list[int],
    *,
    columns: int = 3,
    rows: int = 2,
    overlap_ratio: float = 0.10,
) -> list[list[int]]:
    if len(body_roi_px) != 4:
        raise ValueError("V63_BODY_ROI_INVALID")
    left, top, width, height = [int(value) for value in body_roi_px]
    if width <= 0 or height <= 0 or columns <= 0 or rows <= 0:
        raise ValueError("V63_BODY_ROI_INVALID")
    if not 0 <= overlap_ratio < 0.5:
        raise ValueError("V63_TILE_OVERLAP_INVALID")
    cell_width = width / columns
    cell_height = height / rows
    margin_x = cell_width * overlap_ratio
    margin_y = cell_height * overlap_ratio
    right = left + width
    bottom = top + height
    boxes: list[list[int]] = []
    for row in range(rows):
        for column in range(columns):
            x1 = left + column * cell_width
            x2 = left + (column + 1) * cell_width
            y1 = top + row * cell_height
            y2 = top + (row + 1) * cell_height
            if column > 0:
                x1 -= margin_x
            if column < columns - 1:
                x2 += margin_x
            if row > 0:
                y1 -= margin_y
            if row < rows - 1:
                y2 += margin_y
            boxes.append(
                [
                    max(left, round(x1)),
                    max(top, round(y1)),
                    min(right, round(x2)),
                    min(bottom, round(y2)),
                ]
            )
    return boxes


def _body_roi_pixels(
    image_size: tuple[int, int], template_contract: dict[str, Any]
) -> list[int]:
    width, height = image_size
    slide_width, slide_height = template_contract["slide_size_in"]
    left, top, roi_width, roi_height = template_contract["body_roi_in"]
    values = [
        round(left / slide_width * width),
        round(top / slide_height * height),
        round(roi_width / slide_width * width),
        round(roi_height / slide_height * height),
    ]
    values[0] = max(0, min(width - 1, values[0]))
    values[1] = max(0, min(height - 1, values[1]))
    values[2] = max(1, min(width - values[0], values[2]))
    values[3] = max(1, min(height - values[1], values[3]))
    return values


def generate_review_tiles(
    project_dir: str | Path,
    *,
    template_path: str | Path | None = None,
    source_body_rois: dict[str, list[int]] | None = None,
    legacy_template_roi: bool = False,
) -> dict[str, Any]:
    project = Path(project_dir).resolve()
    template = Path(template_path or Path(__file__).parents[1] / "assets" / "company_template.pptx").resolve()
    skeleton = _load_skeleton_module().read_template_contract(template)
    blueprints = sorted(
        path
        for path in (project / "blueprints").glob("S*.png")
        if _SLIDE_ID.fullmatch(path.stem)
    )
    if not blueprints:
        raise ValueError("V63_BLUEPRINTS_MISSING")
    roi_path = project / '.build' / 'v63_source_body_rois.json'
    roi_records = json.loads(roi_path.read_text(encoding='utf-8')).get('pages', {}) if roi_path.is_file() else {}
    if source_body_rois is None and roi_records:
        source_body_rois = {}
        for blueprint in blueprints:
            record = roi_records.get(blueprint.stem, {})
            if record.get('blueprint_sha256') != _sha256(blueprint):
                raise ValueError('V63_SOURCE_ROI_HASH_MISMATCH')
            source_body_rois[blueprint.stem] = record.get('source_body_roi_px')
    if source_body_rois is None and not legacy_template_roi:
        return {'schema_version': SCHEMA_VERSION, 'deconstruction_runtime_revision': RUNTIME_REVISION,
                'status': 'source_roi_review_required', 'pages': {},
                'message': 'Inspect complete blueprint pages and write .build/v63_source_body_rois.json; no user confirmation needed.'}
    if source_body_rois is not None and set(source_body_rois) != {p.stem for p in blueprints}:
        raise ValueError('V63_SOURCE_ROI_PAGE_SET_INVALID')
    pages: dict[str, Any] = {}
    for blueprint in blueprints:
        slide_id = blueprint.stem
        destination = project / ".build" / "v63_visual_review_tiles" / slide_id
        destination.mkdir(parents=True, exist_ok=True)
        with Image.open(blueprint) as source:
            image = source.convert("RGB")
            body_roi = source_body_rois[slide_id] if source_body_rois is not None else _body_roi_pixels(image.size, skeleton)
            if not isinstance(body_roi, list) or len(body_roi) != 4 or any(not isinstance(v, int) for v in body_roi):
                raise ValueError('V63_SOURCE_ROI_INVALID')
            left, top, width, height = body_roi
            if min(left, top) < 0 or min(width, height) <= 0 or left+width > image.width or top+height > image.height:
                raise ValueError('V63_SOURCE_ROI_INVALID')
            full_box = [left, top, left + width, top + height]
            boxes = [full_box, *overlapping_tile_boxes(body_roi)]
            ids = ["FULL", *[f"B{index:02d}" for index in range(1, 7)]]
            if source_body_rois is not None:
                boxes.append([0, 0, image.width, image.height])
                ids.append('PAGE')
            tiles: list[dict[str, Any]] = []
            for tile_id, box in zip(ids, boxes, strict=True):
                output = destination / f"{tile_id}.png"
                image.crop(tuple(box)).save(output)
                tiles.append(
                    {
                        "tile_id": tile_id,
                        "source_px": box,
                        "path": output.relative_to(project).as_posix(),
                        "sha256": _sha256(output),
                    }
                )
        pages[slide_id] = {
            "blueprint_path": blueprint.relative_to(project).as_posix(),
            "blueprint_sha256": _sha256(blueprint),
            "body_roi_px": body_roi,
            "coordinate_mode": 'source_pixels_contain' if source_body_rois is not None else 'legacy_stretch',
            "tiles": tiles,
        }
    result = {
        "schema_version": SCHEMA_VERSION,
        "deconstruction_runtime_revision": RUNTIME_REVISION,
        "template_path": str(template),
        "template_sha256": _sha256(template),
        "skeleton_contract": skeleton,
        "pages": pages,
    }
    _write_json_atomic(project / ".build" / "v63_visual_review_tiles.json", result)
    return result
