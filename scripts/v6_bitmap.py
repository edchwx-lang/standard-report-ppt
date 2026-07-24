from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from PIL import Image


SCHEMA_VERSION = "6.0"
PIPELINE_REVISION = "6.0.0"
REVIEW_PATH = ".build/bitmap_review.json"
ALIGNMENT_PATH = ".build/bitmap_alignment.json"
CONTRACT_PATH = ".build/bitmap_contract.json"
PAGE_SPECS_PATH = ".build/bitmap_page_specs.json"
EXCLUDED_SKELETON_REGIONS = (
    "chapter",
    "page_title",
    "core_judgment",
    "source",
    "page_number",
)

ERROR_REVIEW_RECORD = "V6_BITMAP_REVIEW_RECORD_MISSING"
ERROR_REVIEW_STALE = "V6_BITMAP_REVIEW_RECORD_STALE"
ERROR_ALIGNMENT_SCHEMA_VERSION = "V6_BITMAP_ALIGNMENT_SCHEMA_VERSION_INVALID"
ERROR_ALIGNMENT_PIPELINE_REVISION = "V6_BITMAP_ALIGNMENT_PIPELINE_REVISION_INVALID"
ERROR_ALIGNMENT_CONSTRUCTION_MODE = "V6_BITMAP_ALIGNMENT_CONSTRUCTION_MODE_INVALID"
ERROR_ALIGNMENT_PAGES = "V6_BITMAP_ALIGNMENT_PAGES_INVALID"
ERROR_ALIGNMENT_PAGE_SET = "V6_BITMAP_ALIGNMENT_PAGE_SET_INVALID"
ERROR_REVIEW_REQUIRED = "V6_BITMAP_FULL_PAGE_REVIEW_REQUIRED"
ERROR_BLUEPRINT_HASH = "V6_BITMAP_BLUEPRINT_HASH_MISMATCH"
ERROR_CROP_BOUNDS = "V6_BITMAP_BODY_CROP_BOUNDS_INVALID"
ERROR_FULL_IMAGE_CROP = "V6_BITMAP_FULL_IMAGE_CROP_FORBIDDEN"
ERROR_EXCLUDED_REGIONS = "V6_BITMAP_EXCLUDED_SKELETON_REGIONS_INVALID"


def sha256_file(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _write_json_atomic(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def _blueprints(project: Path) -> list[Path]:
    paths = sorted((project / "blueprints").glob("S[0-9][0-9].png"))
    if not paths:
        raise FileNotFoundError(
            "V6_BITMAP_BLUEPRINTS_MISSING: no immutable blueprints/SNN.png files"
        )
    return paths


def prepare_bitmap_review(project_dir: str | Path) -> dict[str, Any]:
    """Write the single, full-page hash-bound review manifest for bitmap mode."""
    project = Path(project_dir).resolve()
    pages: dict[str, Any] = {}
    for blueprint in _blueprints(project):
        with Image.open(blueprint) as image:
            width, height = image.size
        slide_id = blueprint.stem
        pages[slide_id] = {
            "blueprint_path": blueprint.relative_to(project).as_posix(),
            "blueprint_sha256": sha256_file(blueprint),
            "pixel_size": [width, height],
        }
    payload = {
        "schema_version": SCHEMA_VERSION,
        "pipeline_revision": PIPELINE_REVISION,
        "construction_mode": "bitmap",
        "review_scope": "full_page_only",
        "pages": pages,
    }
    _write_json_atomic(project / REVIEW_PATH, payload)
    return payload


def _read_review(project: Path) -> tuple[dict[str, Any] | None, list[str]]:
    path = project / REVIEW_PATH
    if not path.is_file():
        return None, [ERROR_REVIEW_RECORD]
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, json.JSONDecodeError):
        return None, [ERROR_REVIEW_RECORD]
    if not isinstance(payload, dict) or not isinstance(payload.get("pages"), dict):
        return None, [ERROR_REVIEW_RECORD]
    return payload, []


def _review_errors(project: Path, review: dict[str, Any]) -> tuple[dict[str, Any], list[str]]:
    errors: list[str] = []
    pages = review.get("pages")
    if (
        review.get("schema_version") != SCHEMA_VERSION
        or review.get("pipeline_revision") != PIPELINE_REVISION
        or review.get("construction_mode") != "bitmap"
        or review.get("review_scope") != "full_page_only"
        or not isinstance(pages, dict)
    ):
        return {}, [ERROR_REVIEW_RECORD]
    records: dict[str, Any] = {}
    try:
        blueprints = _blueprints(project)
    except FileNotFoundError:
        return {}, [ERROR_REVIEW_RECORD]
    for blueprint in blueprints:
        slide_id = blueprint.stem
        record = pages.get(slide_id)
        if not isinstance(record, dict):
            errors.append(ERROR_REVIEW_RECORD)
            continue
        current_hash = sha256_file(blueprint)
        if (
            record.get("blueprint_path")
            != blueprint.relative_to(project).as_posix()
            or record.get("blueprint_sha256") != current_hash
        ):
            errors.append(ERROR_REVIEW_STALE)
            continue
        try:
            with Image.open(blueprint) as image:
                size = list(image.size)
        except OSError:
            errors.append(ERROR_REVIEW_STALE)
            continue
        if (
            record.get("pixel_size") != size
        ):
            errors.append(ERROR_REVIEW_STALE)
            continue
        records[slide_id] = record
    if set(pages) != {path.stem for path in blueprints}:
        errors.append(ERROR_REVIEW_RECORD)
    return records, _dedupe(errors)


def _dedupe(errors: list[str]) -> list[str]:
    return list(dict.fromkeys(errors))


def _valid_crop(value: Any, width: int, height: int) -> tuple[bool, bool]:
    if (
        not isinstance(value, list)
        or len(value) != 4
        or any(not isinstance(item, int) or isinstance(item, bool) for item in value)
    ):
        return False, False
    left, top, right, bottom = value
    if not (0 <= left < right <= width and 0 <= top < bottom <= height):
        return False, False
    return True, value == [0, 0, width, height]


def validate_bitmap_alignment(
    project_dir: str | Path,
    payload: dict[str, Any],
) -> list[str]:
    """Validate that bitmap alignment is reviewed and bound to current pages."""
    project = Path(project_dir).resolve()
    errors: list[str] = []
    if not isinstance(payload, dict):
        return [
            ERROR_ALIGNMENT_SCHEMA_VERSION,
            ERROR_ALIGNMENT_PIPELINE_REVISION,
            ERROR_ALIGNMENT_CONSTRUCTION_MODE,
            ERROR_ALIGNMENT_PAGES,
        ]
    if payload.get("schema_version") != SCHEMA_VERSION:
        errors.append(ERROR_ALIGNMENT_SCHEMA_VERSION)
    if payload.get("pipeline_revision") != PIPELINE_REVISION:
        errors.append(ERROR_ALIGNMENT_PIPELINE_REVISION)
    if payload.get("construction_mode") != "bitmap":
        errors.append(ERROR_ALIGNMENT_CONSTRUCTION_MODE)
    review, review_errors = _read_review(project)
    errors.extend(review_errors)
    if review is None:
        return _dedupe(errors)
    records, review_errors = _review_errors(project, review)
    errors.extend(review_errors)
    pages = payload.get("pages") if isinstance(payload, dict) else None
    if not isinstance(pages, dict):
        return _dedupe(errors + [ERROR_ALIGNMENT_PAGES])
    if set(pages) != set(records):
        errors.append(ERROR_ALIGNMENT_PAGE_SET)
    for slide_id, review_record in records.items():
        alignment = pages.get(slide_id)
        if not isinstance(alignment, dict):
            continue
        if alignment.get("reviewed_full_page") is not True:
            errors.append(ERROR_REVIEW_REQUIRED)
        if alignment.get("blueprint_sha256") != review_record["blueprint_sha256"]:
            errors.append(ERROR_BLUEPRINT_HASH)
        width, height = review_record["pixel_size"]
        valid_crop, full_image = _valid_crop(
            alignment.get("source_px"), width, height
        )
        if not valid_crop:
            errors.append(ERROR_CROP_BOUNDS)
        elif full_image:
            errors.append(ERROR_FULL_IMAGE_CROP)
        if alignment.get("excluded_skeleton_regions") != list(
            EXCLUDED_SKELETON_REGIONS
        ):
            errors.append(ERROR_EXCLUDED_REGIONS)
    return _dedupe(errors)


def _read_alignment(project: Path) -> dict[str, Any]:
    path = project / ALIGNMENT_PATH
    if not path.is_file():
        raise ValueError("V6_BITMAP_ALIGNMENT_RECORD_MISSING")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        raise ValueError("V6_BITMAP_ALIGNMENT_RECORD_INVALID") from exc
    if not isinstance(payload, dict):
        raise ValueError("V6_BITMAP_ALIGNMENT_RECORD_INVALID")
    return payload


def materialize_bitmap_assets(
    project_dir: str | Path,
    *,
    reuse_slide_ids: set[str] | None = None,
) -> dict[str, Any]:
    """Crop one reviewed bitmap body asset and runtime element per page."""
    project = Path(project_dir).resolve()
    alignment = _read_alignment(project)
    errors = validate_bitmap_alignment(project, alignment)
    if errors:
        raise ValueError("\n".join(errors))
    review, review_errors = _read_review(project)
    if review is None or review_errors:
        raise ValueError(ERROR_REVIEW_RECORD)
    records, errors = _review_errors(project, review)
    if errors:
        raise ValueError("\n".join(errors))

    contract_pages: dict[str, Any] = {}
    page_specs: dict[str, Any] = {}
    reused = reuse_slide_ids or set()
    for slide_id, review_record in records.items():
        blueprint = project / review_record["blueprint_path"]
        source_px = alignment["pages"][slide_id]["source_px"]
        asset_id = f"{slide_id}_BODY_BITMAP"
        asset = project / ".build" / "assets" / slide_id / f"{asset_id}.png"
        asset.parent.mkdir(parents=True, exist_ok=True)
        with Image.open(blueprint) as image:
            expected = image.crop(tuple(source_px)).convert("RGBA")
            if slide_id in reused and asset.is_file():
                with Image.open(asset) as existing:
                    actual = existing.convert("RGBA")
                    if (
                        expected.size != actual.size
                        or expected.tobytes() != actual.tobytes()
                    ):
                        expected.save(asset)
            else:
                expected.save(asset)
        asset_path = asset.relative_to(project).as_posix()
        contract_pages[slide_id] = {
            "asset_id": asset_id,
            "source_blueprint": review_record["blueprint_path"],
            "source_blueprint_sha256": review_record["blueprint_sha256"],
            "source_px": source_px,
            "asset_path": asset_path,
            "asset_sha256": sha256_file(asset),
            "fit": "contain",
            "target": "runtime_body_box",
        }
        page_specs[slide_id] = {
            "elements": [
                {
                    "type": "body_asset",
                    "element_id": asset_id,
                    "asset_id": asset_id,
                    "asset_path": asset_path,
                    "fit": "contain",
                    "target": "runtime_body_box",
                }
            ]
        }
    contract = {
        "schema_version": SCHEMA_VERSION,
        "pipeline_revision": PIPELINE_REVISION,
        "construction_mode": "bitmap",
        "pages": contract_pages,
    }
    _write_json_atomic(project / CONTRACT_PATH, contract)
    _write_json_atomic(project / PAGE_SPECS_PATH, page_specs)
    return contract


def materialize_bitmap_batch_assets(
    project_dir: str | Path, slide_ids: list[str]
) -> None:
    """Materialize only one recovery batch; whole-deck contracts are written later."""

    project = Path(project_dir).resolve()
    alignment = _read_alignment(project)
    errors = validate_bitmap_alignment(project, alignment)
    if errors:
        raise ValueError("\n".join(errors))
    review, review_errors = _read_review(project)
    if review is None or review_errors:
        raise ValueError(ERROR_REVIEW_RECORD)
    records, errors = _review_errors(project, review)
    if errors:
        raise ValueError("\n".join(errors))
    requested = set(slide_ids)
    if not requested or not requested.issubset(records):
        raise ValueError("V6_BITMAP_BATCH_PAGE_SET_INVALID")
    for slide_id in slide_ids:
        review_record = records[slide_id]
        blueprint = project / review_record["blueprint_path"]
        source_px = alignment["pages"][slide_id]["source_px"]
        asset_id = f"{slide_id}_BODY_BITMAP"
        asset = project / ".build" / "assets" / slide_id / f"{asset_id}.png"
        asset.parent.mkdir(parents=True, exist_ok=True)
        with Image.open(blueprint) as image:
            image.crop(tuple(source_px)).convert("RGBA").save(asset)
