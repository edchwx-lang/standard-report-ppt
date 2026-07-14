from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

from PIL import Image


def _inside(root: Path, candidate: Path) -> bool:
    try:
        candidate.resolve().relative_to(root.resolve())
        return True
    except ValueError:
        return False


def _valid_rect(size: tuple[int, int], rect: Any) -> bool:
    if not isinstance(rect, list) or len(rect) != 4:
        return False
    if not all(isinstance(value, int) for value in rect):
        return False
    left, top, right, bottom = rect
    return 0 <= left < right <= size[0] and 0 <= top < bottom <= size[1]


def extract_blueprint_assets(
    geometry_path: str | Path, project_dir: str | Path
) -> list[Path]:
    geometry_path = Path(geometry_path)
    project_dir = Path(project_dir)
    geometry = json.loads(geometry_path.read_text(encoding="utf-8"))
    outputs: list[Path] = []
    for slide in geometry.get("slides", []):
        blueprint_path = project_dir / slide["blueprint_file"]
        if not blueprint_path.is_file():
            raise FileNotFoundError(blueprint_path)
        with Image.open(blueprint_path) as blueprint:
            blueprint.load()
            for asset in slide.get("assets", []):
                if asset.get("source_type") != "blueprint_crop":
                    continue
                rect = asset.get("source_px")
                if not _valid_rect(blueprint.size, rect):
                    raise ValueError(f"invalid source_px for {asset.get('asset_id')}")
                left, top, right, bottom = rect
                if ((right - left) * (bottom - top)) / (blueprint.width * blueprint.height) > 0.35:
                    raise ValueError(f"blueprint crop is too large for {asset.get('asset_id')}")
                relative_path = Path(asset["path"])
                if relative_path.is_absolute() or relative_path.parts[:1] != ("blueprint_assets",):
                    raise ValueError(f"asset path must be under blueprint_assets for {asset.get('asset_id')}")
                output_path = project_dir / relative_path
                if not _inside(project_dir / "blueprint_assets", output_path):
                    raise ValueError(f"asset path escapes blueprint_assets for {asset.get('asset_id')}")
                output_path.parent.mkdir(parents=True, exist_ok=True)
                crop = blueprint.crop((left, top, right, bottom)).convert("RGB")
                crop.save(output_path, format="PNG")
                asset["pixel_size"] = [crop.width, crop.height]
                asset["sha256"] = hashlib.sha256(output_path.read_bytes()).hexdigest()
                outputs.append(output_path)
    geometry_path.write_text(
        json.dumps(geometry, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return outputs


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Crop declared complex visual assets from accepted ImageGen blueprints."
    )
    parser.add_argument("--geometry", required=True, type=Path)
    parser.add_argument("--project", required=True, type=Path)
    args = parser.parse_args()
    for path in extract_blueprint_assets(args.geometry, args.project):
        print(path)


if __name__ == "__main__":
    main()
