from __future__ import annotations

import argparse
from pathlib import Path

from ppt_runtime import build_deck


def main() -> None:
    parser = argparse.ArgumentParser(description="Render an editable PPTX from confirmed V4.1 project contracts.")
    parser.add_argument("--spec", required=True, type=Path)
    parser.add_argument("--geometry", required=True, type=Path)
    parser.add_argument("--brief", required=True, type=Path)
    parser.add_argument("--blueprint-manifest", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--template", type=Path)
    args = parser.parse_args()
    skill_dir = Path(__file__).resolve().parents[1]
    template = args.template or skill_dir / "assets" / "company_template.pptx"
    result = build_deck(
        args.spec,
        args.geometry,
        args.output,
        template,
        brief_path=args.brief,
        blueprint_manifest_path=args.blueprint_manifest,
    )
    print(result)


if __name__ == "__main__":
    main()
