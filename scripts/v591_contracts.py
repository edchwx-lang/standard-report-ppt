from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any


MODERN_BLUEPRINT_REVISIONS = {
    ("5.8", "5.8.4"),
    ("5.9", "5.9.0"),
    ("5.9", "5.9.1"),
    ("5.9", "5.9.2"),
    ("5.9", "5.9.4"),
    ("5.9", "5.9.5"),
    ("5.9", "5.9.6"),
}

CONTRACT_FILES = {
    "authoring_bundle": ".build/authoring_bundle.json",
    "blueprint_alignment": ".build/blueprint_alignment.json",
    "slides": ".build/slides.json",
    "page_specs": ".build/page_specs.json",
    "visual_manifest": ".build/visual_manifest.json",
    "visual_review_tiles": ".build/visual_review_tiles.json",
}


def is_v591(brief: dict[str, Any]) -> bool:
    return (
        brief.get("schema_version") == "5.9"
        and brief.get("pipeline_revision") == "5.9.1"
    )


def is_v592(brief: dict[str, Any]) -> bool:
    return (
        brief.get("schema_version") == "5.9"
        and brief.get("pipeline_revision") == "5.9.2"
    )


def is_v594(brief: dict[str, Any]) -> bool:
    return (
        brief.get("schema_version") == "5.9"
        and brief.get("pipeline_revision") == "5.9.4"
    )


def is_v595(brief: dict[str, Any]) -> bool:
    return (
        brief.get("schema_version") == "5.9"
        and brief.get("pipeline_revision") == "5.9.5"
    )


def is_v596(brief: dict[str, Any]) -> bool:
    return (
        brief.get("schema_version") == "5.9"
        and brief.get("pipeline_revision") == "5.9.6"
    )


def uses_modern_blueprint_contract(brief: dict[str, Any]) -> bool:
    version = (
        str(brief.get("schema_version", "")),
        str(brief.get("pipeline_revision", "")),
    )
    return (
        version in MODERN_BLUEPRINT_REVISIONS
        and brief.get("production_mode") == "blueprint"
    )


def audit_policy(brief: dict[str, Any], audit_name: str) -> str:
    if audit_name == "ppt_asset_audit" and is_v594(brief):
        return "blocker"
    if audit_name == "ppt_asset_audit" and (is_v595(brief) or is_v596(brief)):
        return "blocker"
    if audit_name in {
        "blueprint_fidelity",
        "ppt_asset_audit",
        "ppt_skeleton_audit",
    }:
        if brief.get("schema_version") in {"5.8", "5.9"}:
            return "warning"
    if audit_name == "reconstruction_contract":
        return (
            "blocker"
            if (
                is_v591(brief)
                or is_v592(brief)
                or is_v594(brief)
                or is_v595(brief)
                or is_v596(brief)
            )
            else "warning"
        )
    return "blocker"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def contract_hashes(project_dir: str | Path) -> dict[str, str]:
    project = Path(project_dir).resolve()
    hashes: dict[str, str] = {}
    for name, relative in CONTRACT_FILES.items():
        path = project / relative
        if path.is_file():
            hashes[f"{name}_sha256"] = _sha256(path)
    return hashes
