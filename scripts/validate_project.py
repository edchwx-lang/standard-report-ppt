from __future__ import annotations

import argparse
import json
from pathlib import Path

from ppt_runtime import load_json, load_project, validate_contracts, validate_pptx


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate V4.1 brief, mode, content, geometry, and generated PPTX.")
    parser.add_argument("--spec", required=True, type=Path)
    parser.add_argument("--geometry", required=True, type=Path)
    parser.add_argument("--brief", required=True, type=Path)
    parser.add_argument("--blueprint-manifest", required=True, type=Path)
    parser.add_argument("--pptx", type=Path)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    spec, geometry = load_project(args.spec, args.geometry)
    brief = load_json(args.brief)
    blueprint_manifest = load_json(args.blueprint_manifest)
    errors = (
        validate_pptx(
            args.pptx,
            args.spec,
            args.geometry,
            args.brief,
            args.blueprint_manifest,
        )
        if args.pptx
        else validate_contracts(
            spec,
            geometry,
            brief,
            blueprint_manifest,
            project_dir=args.spec.parent,
        )
    )
    payload = {"ok": not errors, "errors": errors}
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    elif errors:
        print("VALIDATION FAILED")
        for error in errors:
            print(f"- {error}")
    else:
        print("VALIDATION PASSED")
    raise SystemExit(1 if errors else 0)


if __name__ == "__main__":
    main()
