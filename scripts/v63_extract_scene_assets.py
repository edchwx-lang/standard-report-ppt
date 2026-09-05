from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw


SCHEMA_VERSION = "6.3"
RUNTIME_REVISION = "6.3.1"
_SAFE_ASSET_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$")
_CROP_KINDS = frozenset({"photo", "logo", "map", "illustration", "complex_icon"})


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


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _issue(code: str, slide_id: str, message: str) -> dict[str, str]:
    return {
        "code": code,
        "severity": "blocker",
        "stage": "v63_scene_asset_extraction",
        "slide_id": slide_id,
        "message": message,
    }


def _box(value: Any, size: tuple[int, int]) -> tuple[int, int, int, int] | None:
    if not isinstance(value, list) or len(value) != 4:
        return None
    try:
        x1, y1, x2, y2 = [int(item) for item in value]
    except (TypeError, ValueError):
        return None
    width, height = size
    if x2 <= x1 or y2 <= y1 or x1 < 0 or y1 < 0 or x2 > width or y2 > height:
        return None
    return x1, y1, x2, y2


def _dark(pixel: tuple[int, ...]) -> bool:
    red, green, blue = pixel[:3]
    return (red * 299 + green * 587 + blue * 114) / 1000 < 72


def _has_complete_dark_perimeter(image: Image.Image) -> bool:
    rgb = image.convert("RGB")
    width, height = rgb.size
    if width < 4 or height < 4:
        return False
    edges = [
        [rgb.getpixel((x, 0)) for x in range(width)],
        [rgb.getpixel((x, height - 1)) for x in range(width)],
        [rgb.getpixel((0, y)) for y in range(height)],
        [rgb.getpixel((width - 1, y)) for y in range(height)],
    ]
    return all(sum(_dark(pixel) for pixel in edge) / len(edge) >= 0.90 for edge in edges)


def _atomic_crop(element: dict[str, Any]) -> bool:
    return (
        element.get("subject_count") == 1
        and element.get("tight_crop") is True
        and element.get("contains_editable_text") is False
        and element.get("contains_native_geometry") is False
        and element.get("intrinsic_text_only") is True
    )


def apply_crop_recipe(source_rgba: Image.Image, source_box: list[int], recipe: dict) -> Image.Image:
    box = _box(source_box, source_rgba.size)
    if box is None or not isinstance(recipe, dict):
        raise ValueError('V63_ASSET_RECIPE_INVALID')
    mode = recipe.get('mode', 'rect_crop')
    if mode not in {'rect_crop', 'masked_crop', 'local_cleanup'}:
        raise ValueError('V63_ASSET_RECIPE_INVALID')
    result = source_rgba.convert('RGBA').crop(box)
    draw = ImageDraw.Draw(result)
    regions = recipe.get('exclude_regions', [])
    if not isinstance(regions, list) or (mode == 'rect_crop' and regions):
        raise ValueError('V63_ASSET_RECIPE_INVALID')
    for region in regions:
        points = region.get('polygon_px')
        if not isinstance(points, list) or len(points) < 3 or not region.get('overlay_element_ids'):
            raise ValueError('V63_ASSET_MASK_INVALID')
        if any(not isinstance(p, list) or len(p) != 2 or any(not isinstance(v, (float, int)) for v in p)
               or not (0 <= p[0] < result.width and 0 <= p[1] < result.height) for p in points):
            raise ValueError('V63_ASSET_MASK_INVALID')
        fill = (0, 0, 0, 0)
        if 'sample_px' in region:
            if mode != 'local_cleanup' or not region.get('uniform_background_reviewed'):
                raise ValueError('V63_ASSET_CLEANUP_EVIDENCE_REQUIRED')
            sample = region['sample_px']
            if not isinstance(sample, list) or len(sample) != 2 or not (0 <= sample[0] < result.width and 0 <= sample[1] < result.height):
                raise ValueError('V63_ASSET_MASK_INVALID')
            # Sample original pixels, not an earlier cleanup operation.
            fill = source_rgba.convert('RGBA').getpixel((box[0]+int(sample[0]), box[1]+int(sample[1])))
        draw.polygon([tuple(p) for p in points], fill=fill)
    if result.getchannel('A').getbbox() is None:
        raise ValueError('V63_ASSET_EMPTY_MASK')
    return result


def extract_scene_assets(project_dir: str | Path) -> dict[str, Any]:
    project = Path(project_dir).resolve()
    graph = _read_json(project / ".build" / "v63_scene_graph.json")
    census = _read_json(project / ".build" / "v63_visual_census.json")
    blockers: list[dict[str, str]] = []
    assets: list[dict[str, Any]] = []
    seen_asset_ids: set[str] = set()
    census_pages = census.get("pages", {})
    for slide_id, page in graph.get("pages", {}).items():
        blueprint = project / "blueprints" / f"{slide_id}.png"
        if not blueprint.is_file():
            blockers.append(_issue("V63_ASSET_BLUEPRINT_MISSING", slide_id, str(blueprint)))
            continue
        candidate_by_id = {
            item.get("candidate_id"): item
            for item in census_pages.get(slide_id, {}).get("candidates", [])
            if isinstance(item, dict)
        }
        element_by_id = {e.get('element_id'): e for e in page.get('elements', []) if isinstance(e, dict)}
        with Image.open(blueprint) as source_image:
            source = source_image.convert("RGBA")
            for element in page.get("elements", []):
                if not isinstance(element, dict) or element.get("type") != "image_crop":
                    continue
                element_id = str(element.get("element_id", "?"))
                asset_id = element.get("asset_id")
                if (
                    not isinstance(asset_id, str)
                    or _SAFE_ASSET_ID.fullmatch(asset_id) is None
                    or asset_id in seen_asset_ids
                ):
                    blockers.append(_issue("V63_ASSET_ID_INVALID", slide_id, f"{element_id}: invalid or duplicate asset id {asset_id!r}"))
                    continue
                seen_asset_ids.add(asset_id)
                sources = element.get("source_candidate_ids", [])
                candidates = [candidate_by_id.get(item) for item in sources]
                if (
                    len(candidates) != 1
                    or not isinstance(candidates[0], dict)
                    or candidates[0].get("kind") not in _CROP_KINDS
                    or candidates[0].get("expected_treatment") != "crop"
                ):
                    blockers.append(_issue("V63_ASSET_CENSUS_MISMATCH", slide_id, f"{element_id}: crop is not bound to one approved census subject"))
                    continue
                if not _atomic_crop(element):
                    blockers.append(_issue("V63_ASSET_NON_ATOMIC", slide_id, f"{element_id}: crop must be one tight subject without editable text or native geometry"))
                    continue
                source_box = _box(element.get("source_px", element.get("bbox_px")), source.size)
                if source_box is None:
                    blockers.append(_issue("V63_ASSET_BOX_INVALID", slide_id, f"{element_id}: invalid source pixels"))
                    continue
                recipe = element.get('crop_recipe', {'mode': 'rect_crop'})
                try:
                    for region in recipe.get('exclude_regions', []):
                        for overlay_id in region.get('overlay_element_ids', []):
                            overlay = element_by_id.get(overlay_id)
                            if overlay is None or overlay.get('type') in {'image_crop', 'group'}:
                                raise ValueError('V63_ASSET_OVERLAY_MISSING')
                    cropped = apply_crop_recipe(source, list(source_box), recipe)
                except (ValueError, TypeError, AttributeError) as exc:
                    blockers.append(_issue('V63_ASSET_RECIPE_INVALID', slide_id, f'{element_id}: {exc}'))
                    continue
                # A visible independently inventoried native object inside the source
                # crop requires an explicit removal binding, not a self-declared flag.
                removed_ids = {key for r in recipe.get('exclude_regions', []) for key in r.get('overlay_element_ids', [])}
                sx1, sy1, sx2, sy2 = source_box
                contamination = []
                for other_id, other in element_by_id.items():
                    if other_id == element_id or other.get('type') in {'group', 'image_crop'}:
                        continue
                    if other.get('type') not in {'text', 'line', 'connector', 'arrow'}:
                        continue
                    other_box = other.get('bbox_px', [])
                    if len(other_box) == 4 and sx1 <= other_box[0] and sy1 <= other_box[1] and other_box[2] <= sx2 and other_box[3] <= sy2 and other_id not in removed_ids:
                        contamination.append(other_id)
                if contamination:
                    blockers.append(_issue('V63_ASSET_NATIVE_CONTENT_INCLUDED', slide_id, f'{element_id}: {contamination}'))
                    continue
                if _has_complete_dark_perimeter(cropped):
                    blockers.append(_issue("V63_ASSET_FRAME_INCLUDED", slide_id, f"{element_id}: crop includes a complete dark perimeter"))
                    continue
                destination = project / ".build" / "assets" / slide_id / f"{asset_id}.png"
                destination.parent.mkdir(parents=True, exist_ok=True)
                cropped.save(destination)
                assets.append(
                    {
                        "slide_id": slide_id,
                        "element_id": element_id,
                        "asset_id": asset_id,
                        "candidate_id": sources[0],
                        "kind": candidates[0].get("kind"),
                        "blueprint_path": blueprint.relative_to(project).as_posix(),
                        "blueprint_sha256": _sha256(blueprint),
                        "source_px": list(source_box),
                        "crop_recipe": recipe,
                        "recipe_sha256": hashlib.sha256(json.dumps(recipe, sort_keys=True, ensure_ascii=False).encode('utf-8')).hexdigest(),
                        "alpha_sha256": hashlib.sha256(cropped.getchannel('A').tobytes()).hexdigest(),
                        "asset_path": destination.relative_to(project).as_posix(),
                        "asset_sha256": _sha256(destination),
                        "expected_insertions": 1,
                    }
                )
    report = {
        "schema_version": SCHEMA_VERSION,
        "deconstruction_runtime_revision": RUNTIME_REVISION,
        "ok": not blockers,
        "status": "pass" if not blockers else "blocked",
        "asset_count": len(assets),
        "blockers": blockers,
    }
    _write_json_atomic(project / ".build" / "v63_asset_extraction_report.json", report)
    if not blockers:
        _write_json_atomic(
            project / ".build" / "v63_asset_ledger.json",
            {
                "schema_version": SCHEMA_VERSION,
                "deconstruction_runtime_revision": RUNTIME_REVISION,
                "assets": assets,
            },
        )
    return report
