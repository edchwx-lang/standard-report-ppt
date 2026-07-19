"""Extract and validate the complete one-object inventory for V5.6 blueprint projects."""

from __future__ import annotations

import argparse
import ast
import hashlib
import importlib.util
import json
from collections import Counter, deque
from pathlib import Path
from typing import Any

from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageFont


SCHEMA_VERSION = "5.6"


def _pixels(image: Image.Image):
    getter = getattr(image, "get_flattened_data", None)
    return getter() if getter is not None else image.getdata()


def sha256_file(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _literal_assignment(tree: ast.AST, name: str) -> Any:
    for node in getattr(tree, "body", []):
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == name:
                    return ast.literal_eval(node.value)
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name) and node.target.id == name:
            return ast.literal_eval(node.value)
    raise ValueError(f"generator is missing literal {name}")


def load_generator_contract(generator_path: str | Path) -> tuple[list[dict], dict, dict]:
    source = Path(generator_path).read_text(encoding="utf-8")
    tree = ast.parse(source)
    try:
        deck_meta = _literal_assignment(tree, "DECK_META")
    except ValueError:
        deck_meta = {}
    visual_source_name = (
        "DESIGN_DRAFTS"
        if deck_meta.get("schema_version") in {"5.8", "5.9"}
        else "BLUEPRINTS"
    )
    return (
        _literal_assignment(tree, "SLIDES"),
        _literal_assignment(tree, visual_source_name),
        _literal_assignment(tree, "ASSET_CROPS"),
    )


def generator_schema_version(generator_path: str | Path) -> str:
    tree = ast.parse(Path(generator_path).read_text(encoding="utf-8"))
    try:
        return str(_literal_assignment(tree, "DECK_META").get("schema_version", SCHEMA_VERSION))
    except (ValueError, AttributeError):
        return SCHEMA_VERSION


def _validate_visual_review_contract(slides: list[dict], blueprints: dict) -> list[str]:
    validator_path = Path(__file__).with_name("direct_project.py")
    spec = importlib.util.spec_from_file_location("standard_report_v55_visual_validator", validator_path)
    if spec is None or spec.loader is None:
        return ["could not load the V5.5 visual inventory validator"]
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.validate_visual_inventory(
        slides,
        production_mode="blueprint",
        blueprints=blueprints,
    )


def contain_rect(image_size: tuple[int, int], target_box_in: list[float]) -> list[float]:
    image_width, image_height = image_size
    x, y, box_width, box_height = [float(value) for value in target_box_in]
    if image_width <= 0 or image_height <= 0 or box_width <= 0 or box_height <= 0:
        raise ValueError("image and target box dimensions must be positive")
    scale = min(box_width / image_width, box_height / image_height)
    width, height = image_width * scale, image_height * scale
    return [x + (box_width - width) / 2, y + (box_height - height) / 2, width, height]


def _background_color(image: Image.Image) -> tuple[int, int, int]:
    rgb = image.convert("RGB")
    width, height = rgb.size
    border = []
    border.extend(_pixels(rgb.crop((0, 0, width, 1))))
    border.extend(_pixels(rgb.crop((0, height - 1, width, height))))
    border.extend(_pixels(rgb.crop((0, 0, 1, height))))
    border.extend(_pixels(rgb.crop((width - 1, 0, width, height))))
    return Counter(border).most_common(1)[0][0]


def _foreground_mask(image: Image.Image, tolerance: int = 34) -> Image.Image:
    rgb = image.convert("RGB")
    background = Image.new("RGB", rgb.size, _background_color(rgb))
    difference = ImageChops.difference(rgb, background).convert("L")
    return difference.point(lambda value: 255 if value >= tolerance else 0)


def _macro_component_count(mask: Image.Image) -> int:
    width, height = mask.size
    scale = min(1.0, 160.0 / max(width, height))
    small = mask.resize((max(1, round(width * scale)), max(1, round(height * scale))), Image.Resampling.NEAREST)
    small = small.filter(ImageFilter.MaxFilter(9 if min(small.size) >= 9 else 3))
    pixels = small.load()
    visited: set[tuple[int, int]] = set()
    areas: list[int] = []
    for y in range(small.height):
        for x in range(small.width):
            if pixels[x, y] == 0 or (x, y) in visited:
                continue
            queue = deque([(x, y)])
            visited.add((x, y))
            area = 0
            while queue:
                cx, cy = queue.popleft()
                area += 1
                for nx, ny in ((cx - 1, cy), (cx + 1, cy), (cx, cy - 1), (cx, cy + 1)):
                    if 0 <= nx < small.width and 0 <= ny < small.height and pixels[nx, ny] and (nx, ny) not in visited:
                        visited.add((nx, ny))
                        queue.append((nx, ny))
            areas.append(area)
    if not areas:
        return 0
    threshold = max(10, int(sum(areas) * 0.08))
    return sum(area >= threshold for area in areas)


def analyze_single_object_crop(image: Image.Image, *, kind: str = "pictogram") -> dict:
    mask = _foreground_mask(image)
    errors: list[str] = []
    if mask.getbbox() is None:
        errors.append("empty_crop")
    row_ratios = [sum(1 for value in _pixels(mask.crop((0, y, mask.width, y + 1))) if value) / mask.width for y in range(mask.height)]
    col_ratios = [sum(1 for value in _pixels(mask.crop((x, 0, x + 1, mask.height))) if value) / mask.height for x in range(mask.width)]
    dense_row_positions = [index for index, ratio in enumerate(row_ratios) if ratio >= 0.82]
    dense_col_positions = [index for index, ratio in enumerate(col_ratios) if ratio >= 0.82]
    dense_rows = len(dense_row_positions)
    dense_cols = len(dense_col_positions)
    row_edge = any(position <= mask.height * 0.18 or position >= mask.height * 0.82 for position in dense_row_positions)
    col_edge = any(position <= mask.width * 0.18 or position >= mask.width * 0.82 for position in dense_col_positions)
    thin_row_band = 0 < dense_rows <= max(3, round(mask.height * 0.15)) and row_edge
    thin_col_band = 0 < dense_cols <= max(3, round(mask.width * 0.15)) and col_edge
    aspect_ratio = mask.width / max(mask.height, 1)
    elongated = aspect_ratio >= 1.75 or aspect_ratio <= 0.57
    if (thin_row_band or thin_col_band) and elongated:
        errors.append("long_rule_contamination")
    components = _macro_component_count(mask)
    if components > 1 and kind != "compound_mark" and elongated:
        errors.append("multiple_macro_objects")
    return {
        "valid": not errors,
        "errors": errors,
        "macro_components": components,
        "dense_rows": dense_rows,
        "dense_cols": dense_cols,
        "aspect_ratio": round(aspect_ratio, 6),
        "content_bbox": list(mask.getbbox() or (0, 0, 0, 0)),
    }


def trim_object(image: Image.Image, padding_px: int = 4) -> Image.Image:
    bbox = _foreground_mask(image).getbbox()
    if bbox is None:
        raise ValueError("cannot trim an empty crop")
    left, top, right, bottom = bbox
    left = max(0, left - padding_px)
    top = max(0, top - padding_px)
    right = min(image.width, right + padding_px)
    bottom = min(image.height, bottom + padding_px)
    return image.crop((left, top, right, bottom)).convert("RGB")


def _visual_kinds(slides: list[dict]) -> dict[str, str]:
    kinds: dict[str, str] = {}
    for slide in slides:
        for visual in slide.get("complex_visuals", []):
            if isinstance(visual, dict) and isinstance(visual.get("asset_id"), str):
                kinds[visual["asset_id"]] = str(visual.get("kind", "pictogram"))
    return kinds


def _declared_visuals(slides: list[dict]) -> dict[str, str]:
    declared: dict[str, str] = {}
    for slide in slides:
        if not isinstance(slide, dict):
            continue
        slide_id = str(slide.get("slide_id", "?"))
        review = slide.get("visual_review")
        visuals = slide.get("complex_visuals")
        if review not in {"extract_declared", "reviewed_no_raster"}:
            raise ValueError(f"{slide_id}: visual_review must be extract_declared or reviewed_no_raster")
        if not isinstance(visuals, list):
            raise ValueError(f"{slide_id}: complex_visuals must be a reviewed list")
        if review == "extract_declared" and not visuals:
            raise ValueError(f"{slide_id}: extract_declared requires at least one complex visual")
        if review == "reviewed_no_raster" and visuals:
            raise ValueError(f"{slide_id}: reviewed_no_raster requires an empty complex_visuals list")
        for visual in visuals:
            asset_id = visual.get("asset_id") if isinstance(visual, dict) else None
            if not isinstance(asset_id, str) or not asset_id:
                raise ValueError(f"{slide_id}: every complex visual requires an asset_id")
            if asset_id in declared:
                raise ValueError(f"{asset_id}: duplicate complex visual asset_id")
            declared[asset_id] = slide_id
    return declared


def _declared_v594_crops(slides: list[dict]) -> dict[str, str]:
    declared: dict[str, str] = {}
    for slide in slides:
        if not isinstance(slide, dict):
            continue
        slide_id = str(slide.get("slide_id", "?"))
        visuals = slide.get("complex_visuals", [])
        if not isinstance(visuals, list):
            raise ValueError(f"{slide_id}: complex_visuals must be a list")
        for visual in visuals:
            asset_id = visual.get("asset_id") if isinstance(visual, dict) else None
            if not isinstance(asset_id, str) or not asset_id:
                raise ValueError(
                    f"{slide_id}: every reviewed crop requires an asset_id"
                )
            if asset_id in declared:
                raise ValueError(f"{asset_id}: duplicate reviewed crop asset_id")
            declared[asset_id] = slide_id
    return declared


def _valid_rect(rect: Any, size: tuple[int, int]) -> bool:
    return isinstance(rect, list) and len(rect) == 4 and all(isinstance(value, int) for value in rect) and 0 <= rect[0] < rect[2] <= size[0] and 0 <= rect[1] < rect[3] <= size[1]


def _inside(rect: list[int], bounds: list[int]) -> bool:
    return rect[0] >= bounds[0] and rect[1] >= bounds[1] and rect[2] <= bounds[2] and rect[3] <= bounds[3]


def _write_montage(records: list[dict], project_dir: Path) -> Path:
    cards = []
    for record in records:
        image = Image.open(project_dir / record["path"]).convert("RGB")
        image.thumbnail((260, 150), Image.Resampling.LANCZOS)
        cards.append((record["asset_id"], image.copy()))
    width = 600
    height = max(100, len(cards) * 190)
    canvas = Image.new("RGB", (width, height), "white")
    draw = ImageDraw.Draw(canvas)
    font = ImageFont.load_default()
    for index, (asset_id, image) in enumerate(cards):
        top = index * 190 + 15
        canvas.paste(image, (20, top + 22))
        draw.text((20, top), asset_id, fill="black", font=font)
    destination = project_dir / ".build" / "direct_asset_montage.png"
    destination.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(destination)
    return destination


def extract_direct_assets(generator_path: str | Path, project_dir: str | Path) -> dict:
    project_dir = Path(project_dir)
    schema_version = generator_schema_version(generator_path)
    smooth_v58 = schema_version in {"5.8", "5.9"}
    brief_path = project_dir / "project_brief.json"
    brief = (
        json.loads(brief_path.read_text(encoding="utf-8"))
        if brief_path.is_file()
        else {}
    )
    revision = str(brief.get("pipeline_revision", ""))
    strict_v594 = (
        schema_version == "5.9"
        and revision in {"5.9.4", "5.9.5", "5.9.6"}
    )
    strict_v596 = schema_version == "5.9" and revision == "5.9.6"
    slides, blueprints, crops = load_generator_contract(generator_path)
    inventory = [
        visual
        for slide in slides
        if isinstance(slide, dict)
        for visual in slide.get("visual_inventory", [])
        if isinstance(visual, dict)
    ]
    observed_visuals = len(inventory)
    crop_planned = sum(
        visual.get("treatment", visual.get("disposition")) == "crop"
        for visual in inventory
    )
    native_planned = sum(
        visual.get("treatment", visual.get("disposition")) == "native"
        for visual in inventory
    )
    omitted_planned = sum(
        visual.get("treatment", visual.get("disposition")) == "omit"
        for visual in inventory
    )
    mandatory_crop_kinds = {
        "icon",
        "pictogram",
        "logo",
        "map",
        "photo",
        "illustration",
        "device",
        "person",
        "product",
        "flag",
    }
    mandatory_crop_count = sum(
        visual.get("kind") in mandatory_crop_kinds
        for visual in inventory
    )
    review_errors = _validate_visual_review_contract(slides, blueprints)
    warnings: list[str] = []
    if review_errors and not smooth_v58:
        declared_count = sum(
            1
            for slide in slides
            if isinstance(slide, dict)
            for visual in slide.get("complex_visuals", [])
            if isinstance(visual, dict) and isinstance(visual.get("asset_id"), str)
        )
        report = {
            "schema_version": SCHEMA_VERSION,
            "ok": False,
            "errors": review_errors,
            "declared_assets": declared_count,
            "extracted_assets": 0,
            "complete_inventory": False,
            "assets": [],
        }
        report_path = project_dir / ".build" / "direct_asset_report.json"
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        raise ValueError("; ".join(review_errors))
    if review_errors:
        warnings.extend(review_errors)
    kinds = _visual_kinds(slides)
    try:
        declared = (
            _declared_v594_crops(slides)
            if strict_v594
            else _declared_visuals(slides)
        )
    except ValueError as exc:
        if not smooth_v58:
            raise
        warnings.append(str(exc))
        declared = {
            str(asset_id): str(spec.get("slide_id", "?"))
            for asset_id, spec in crops.items()
            if isinstance(spec, dict)
        }
    records: list[dict] = []
    errors: list[str] = []
    for asset_id in sorted(set(declared) - set(crops)):
        errors.append(f"{declared[asset_id]}/{asset_id}: declared complex visual is missing from ASSET_CROPS")
    for asset_id in sorted(set(crops) - set(declared)):
        errors.append(f"{asset_id}: ASSET_CROPS entry is not declared in complex_visuals")
    for asset_id, crop_spec in crops.items():
        slide_id = crop_spec.get("slide_id")
        blueprint_record = blueprints.get(slide_id, {})
        blueprint_path = project_dir / str(blueprint_record.get("path", ""))
        if not blueprint_path.is_file():
            errors.append(f"{asset_id}: blueprint is missing")
            continue
        composition_path = blueprint_path.with_suffix(".composition.json")
        if not composition_path.is_file():
            errors.append(f"{asset_id}: composition record is missing")
            continue
        try:
            composition = json.loads(composition_path.read_text(encoding="utf-8"))
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            errors.append(f"{asset_id}: composition record is unreadable: {exc}")
            continue
        try:
            with Image.open(blueprint_path) as blueprint:
                source_px = crop_spec.get("source_px")
                if not _valid_rect(source_px, blueprint.size):
                    errors.append(f"{asset_id}: invalid source_px")
                    continue
                if not _inside(source_px, composition.get("body_roi", [])):
                    errors.append(f"{asset_id}: source_px must stay inside body_roi")
                    continue
                raw = blueprint.crop(tuple(source_px)).convert("RGB")
            analysis = analyze_single_object_crop(raw, kind=kinds.get(asset_id, "pictogram"))
            if not analysis["valid"]:
                findings = [
                    f"{asset_id}: {error}"
                    for error in analysis["errors"]
                ]
                if strict_v594 and "empty_crop" not in analysis["errors"]:
                    warnings.extend(findings)
                else:
                    errors.extend(findings)
                    continue
            padding = int(crop_spec.get("padding_px", 4))
            trimmed = trim_object(raw, padding)
            output = project_dir / ".build" / "assets" / slide_id / f"{asset_id}.png"
            output.parent.mkdir(parents=True, exist_ok=True)
            trimmed.save(output)
            target_box = crop_spec.get("target_box_in")
            placement = contain_rect(trimmed.size, target_box)
        except (OSError, ValueError, TypeError, KeyError, AttributeError) as exc:
            errors.append(f"{asset_id}: crop extraction failed: {exc}")
            continue
        records.append({
            "asset_id": asset_id,
            "slide_id": slide_id,
            "kind": kinds.get(asset_id, "pictogram"),
            "path": output.relative_to(project_dir).as_posix(),
            "sha256": sha256_file(output),
            "pixel_size": list(trimmed.size),
            "aspect_ratio": round(trimmed.width / trimmed.height, 6),
            "target_box_in": target_box,
            "placement_in": [round(value, 6) for value in placement],
            "analysis": analysis,
        })
    extracted_ids = {record["asset_id"] for record in records}
    complete_inventory = not errors and extracted_ids == set(declared)
    if smooth_v58 and not strict_v594:
        warnings.extend(errors)
    requested_crop_ids = sorted(set(declared) if strict_v596 else set(crops))
    extracted_crop_ids = sorted(extracted_ids)
    expected_crop_ids = set(declared) if strict_v596 else set(crops)
    missing_crop_ids = sorted(expected_crop_ids - extracted_ids)
    unexpected_crop_ids = sorted(extracted_ids - expected_crop_ids)
    report = {
        "schema_version": schema_version,
        "ok": complete_inventory if strict_v594 else True if smooth_v58 else complete_inventory,
        "status": (
            "blocked"
            if strict_v594 and not complete_inventory
            else "pass_with_warnings"
            if warnings
            else "pass"
            if strict_v594 or smooth_v58
            else "pass"
            if complete_inventory
            else "blocked"
        ),
        "errors": errors if strict_v594 else [] if smooth_v58 else errors,
        "warnings": warnings,
        "declared_assets": len(declared),
        "extracted_assets": len(extracted_ids),
        "observed_visuals": observed_visuals,
        "crop_planned": crop_planned,
        "mandatory_crop_count": mandatory_crop_count,
        "native_planned": native_planned,
        "omitted_planned": omitted_planned,
        "complete_inventory": complete_inventory,
        "requested_crop_ids": requested_crop_ids,
        "extracted_crop_ids": extracted_crop_ids,
        "missing_crop_ids": missing_crop_ids,
        "unexpected_crop_ids": unexpected_crop_ids,
        "assets": records,
    }
    if smooth_v58:
        report["skill_version"] = (
            revision
    if revision in {"5.8.3", "5.8.4", "5.9.0", "5.9.1", "5.9.2", "5.9.4", "5.9.5", "5.9.6"}
            else "5.8.2"
        )
    report_path = project_dir / ".build" / "direct_asset_report.json"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if records:
        report["montage"] = _write_montage(records, project_dir).relative_to(project_dir).as_posix()
        report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if errors and (not smooth_v58 or strict_v594):
        raise ValueError("; ".join(errors))
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description="Extract the complete strict one-object inventory for a V5.6 blueprint project.")
    parser.add_argument("--project", required=True, type=Path)
    parser.add_argument("--generator", type=Path)
    args = parser.parse_args()
    generator = args.generator or args.project / "generate_deck.py"
    print(json.dumps(extract_direct_assets(generator, args.project), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
