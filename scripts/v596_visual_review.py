from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

from PIL import Image


SCHEMA_VERSION = "5.9"
SKILL_VERSION = "5.9.6"


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


def _quadrants(width: int, height: int) -> list[tuple[str, list[int]]]:
    if width < 2 or height < 2:
        raise ValueError("blueprint must be at least 2x2 pixels")
    middle_x = width // 2
    middle_y = height // 2
    return [
        ("Q1", [0, 0, middle_x, middle_y]),
        ("Q2", [middle_x, 0, width, middle_y]),
        ("Q3", [0, middle_y, middle_x, height]),
        ("Q4", [middle_x, middle_y, width, height]),
    ]


def generate_review_tiles(project_dir: str | Path) -> dict[str, Any]:
    project = Path(project_dir).resolve()
    blueprint_dir = project / "blueprints"
    blueprints = sorted(blueprint_dir.glob("S[0-9][0-9].png"))
    if not blueprints:
        raise FileNotFoundError(f"no formal blueprints found under {blueprint_dir}")

    pages: dict[str, Any] = {}
    for blueprint_path in blueprints:
        slide_id = blueprint_path.stem
        with Image.open(blueprint_path) as image:
            source = image.convert("RGB")
            width, height = source.size
            tiles = []
            for tile_id, source_px in _quadrants(width, height):
                output = (
                    project
                    / ".build"
                    / "visual_review_tiles"
                    / slide_id
                    / f"{tile_id}.png"
                )
                output.parent.mkdir(parents=True, exist_ok=True)
                source.crop(tuple(source_px)).save(output)
                tiles.append(
                    {
                        "tile_id": tile_id,
                        "path": output.relative_to(project).as_posix(),
                        "source_px": source_px,
                        "pixel_size": [
                            source_px[2] - source_px[0],
                            source_px[3] - source_px[1],
                        ],
                        "sha256": sha256_file(output),
                    }
                )
        pages[slide_id] = {
            "blueprint_path": blueprint_path.relative_to(project).as_posix(),
            "blueprint_sha256": sha256_file(blueprint_path),
            "pixel_size": [width, height],
            "tiles": tiles,
        }

    manifest = {
        "schema_version": SCHEMA_VERSION,
        "skill_version": SKILL_VERSION,
        "pages": pages,
    }
    _write_json_atomic(project / ".build" / "visual_review_tiles.json", manifest)
    return manifest


def validate_review_tiles(
    project_dir: str | Path,
    alignment: dict[str, Any],
) -> list[str]:
    project = Path(project_dir).resolve()
    manifest_path = project / ".build" / "visual_review_tiles.json"
    if not manifest_path.is_file():
        return ["visual_review_tiles.json is missing"]
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        return [f"visual_review_tiles.json is unreadable: {exc}"]
    manifest_hash = sha256_file(manifest_path)
    errors: list[str] = []
    alignment_pages = alignment.get("pages", {})
    manifest_pages = manifest.get("pages", {})
    if not isinstance(alignment_pages, dict) or not isinstance(manifest_pages, dict):
        return ["visual review alignment or tile manifest pages are invalid"]

    for slide_id, page in alignment_pages.items():
        if not isinstance(page, dict):
            errors.append(f"{slide_id}: alignment page is invalid")
            continue
        record = manifest_pages.get(slide_id)
        if not isinstance(record, dict):
            errors.append(f"{slide_id}: review tile manifest page is missing")
            continue
        blueprint = project / str(record.get("blueprint_path", ""))
        if not blueprint.is_file():
            errors.append(f"{slide_id}: locked blueprint is missing")
            continue
        blueprint_hash = sha256_file(blueprint)
        if (
            record.get("blueprint_sha256") != blueprint_hash
            or page.get("design_draft_sha256") != blueprint_hash
        ):
            errors.append(f"{slide_id}: review tiles are stale for the locked blueprint")
        review = page.get("visual_review_tiles")
        if not isinstance(review, dict):
            errors.append(f"{slide_id}: visual_review_tiles review record is missing")
            continue
        if (
            review.get("tile_manifest_sha256") != manifest_hash
            or review.get("blueprint_sha256") != blueprint_hash
        ):
            errors.append(f"{slide_id}: visual review is not bound to the tile manifest")
        tiles = record.get("tiles")
        tile_ids: set[str] = set()
        if not isinstance(tiles, list):
            errors.append(f"{slide_id}: tile list is invalid")
            continue
        for tile in tiles:
            if not isinstance(tile, dict):
                errors.append(f"{slide_id}: tile record is invalid")
                continue
            tile_id = str(tile.get("tile_id", ""))
            tile_path = project / str(tile.get("path", ""))
            tile_ids.add(tile_id)
            if not tile_path.is_file() or tile.get("sha256") != sha256_file(tile_path):
                errors.append(f"{slide_id}/{tile_id}: review tile is missing or stale")
        if tile_ids != {"Q1", "Q2", "Q3", "Q4"}:
            errors.append(f"{slide_id}: review tile set must be Q1-Q4")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Create hash-bound quadrant tiles from locked formal blueprints."
    )
    parser.add_argument("--project", required=True)
    args = parser.parse_args()
    manifest = generate_review_tiles(args.project)
    print(json.dumps(manifest, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
