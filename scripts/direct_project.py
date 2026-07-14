from __future__ import annotations

import argparse
import ast
import hashlib
import importlib.util
import json
import math
import re
from pathlib import Path
from typing import Any, Iterable


SCHEMA_VERSION = "5.5"
PROJECT_SCHEMA_VERSION = SCHEMA_VERSION
PENDING_PAGE_STATUS = "pending"
FINAL_PAGE_STATUS = "accepted"
PAGE_STATUS_ORDER = (
    "blueprint_saved",
    "builder_written",
    "assets_extracted",
    "rendered",
    "visually_compared",
    FINAL_PAGE_STATUS,
)
FORBIDDEN_BLUEPRINT_TOKENS = (
    "fast_geometry",
    "runtime_archetype",
    "layout_archetype_selector",
)
SLIDE_ID_RE = re.compile(r"S\d{2,3}$")
BUILDER_NAME_RE = re.compile(r"build_slide_(S\d{2,3})$")


def sha256_file(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def validate_v55_brief(brief: Any) -> list[str]:
    """Validate the project-level V5.5 contract without guessing legacy fields."""

    if not isinstance(brief, dict):
        return ["project_brief.json must contain a JSON object"]
    errors: list[str] = []
    if "page_count" in brief:
        errors.append("legacy field page_count is forbidden; use requested_page_count")
    if "mode" in brief:
        errors.append("legacy field mode is forbidden; use production_mode")
    if brief.get("schema_version") != PROJECT_SCHEMA_VERSION:
        errors.append(f"project brief schema_version must be {PROJECT_SCHEMA_VERSION}")
    page_count = brief.get("requested_page_count")
    if not isinstance(page_count, int) or page_count <= 0:
        errors.append("requested_page_count must be a positive integer")
    if not isinstance(brief.get("page_mapping"), list):
        errors.append("page_mapping must be a list")
    if brief.get("production_mode") not in {"blueprint", "fast"}:
        errors.append("production_mode must be blueprint or fast")
    if brief.get("production_mode") == "blueprint" and brief.get("blueprint_engine") != "direct":
        errors.append("blueprint mode requires blueprint_engine: direct")
    if brief.get("confirmation_source") not in {"user_explicit", "user_selected"}:
        errors.append("confirmation_source must be user_explicit or user_selected")
    return errors


# Compatibility name retained for older integrations; it validates the live schema.
validate_v54_brief = validate_v55_brief


def template_contract(template_path: str | Path) -> dict[str, str]:
    """Return the resolved company-template path and its live SHA-256."""

    resolved = Path(template_path).expanduser().resolve()
    if not resolved.is_file():
        raise FileNotFoundError(resolved)
    return {"path": resolved.as_posix(), "sha256": sha256_file(resolved)}


def materialize_generator(
    project_dir: str | Path,
    template_path: str | Path,
    generator_template: str | Path,
    *,
    production_mode: str = "blueprint",
    page_count: int = 0,
) -> Path:
    """Create a project generator bound to the current company master."""

    project_dir = Path(project_dir).resolve()
    destination = project_dir / "generate_deck.py"
    if destination.exists():
        raise FileExistsError(f"refusing to overwrite existing project generator: {destination}")
    source = Path(generator_template).read_text(encoding="utf-8")
    contract = template_contract(template_path)
    required = (
        "__COMPANY_TEMPLATE_PATH__",
        "__COMPANY_TEMPLATE_SHA256__",
        "__PROJECT_SCHEMA_VERSION__",
        "__PRODUCTION_MODE__",
        "__PAGE_COUNT__",
    )
    missing = [token for token in required if token not in source]
    if missing:
        raise ValueError("generator template is missing materialization tokens: " + ", ".join(missing))
    materialized = (
        source.replace(required[0], contract["path"])
        .replace(required[1], contract["sha256"])
        .replace(required[2], SCHEMA_VERSION)
        .replace(required[3], production_mode)
        .replace('0,  # __PAGE_COUNT__', f'{page_count},  # materialized page count')
    )
    if any(token in materialized for token in required):
        raise ValueError("generator template materialization left unresolved tokens")
    destination.write_text(materialized, encoding="utf-8")
    return destination


def bootstrap_project(
    project_dir: str | Path,
    *,
    batch_size: int = 5,
    template_path: str | Path | None = None,
    generator_template: str | Path | None = None,
) -> Path:
    """Initialize a V5.5 fast or Direct Blueprint project deterministically."""

    project_dir = Path(project_dir).resolve()
    brief_path = project_dir / "project_brief.json"
    if not brief_path.is_file():
        raise FileNotFoundError(brief_path)
    brief = _read_json(brief_path)
    errors = validate_v55_brief(brief)
    if errors:
        raise ValueError("invalid V5.5 project brief:\n- " + "\n- ".join(errors))
    skill_dir = Path(__file__).resolve().parents[1]
    resolved_template = Path(template_path) if template_path else skill_dir / "assets" / "company_template.pptx"
    resolved_generator_template = (
        Path(generator_template)
        if generator_template
        else skill_dir / "assets" / "direct_blueprint_generator_template.py"
    )
    common_directories = (".build", ".build/rendered/current", "output")
    blueprint_directories = ("blueprints",) if brief["production_mode"] == "blueprint" else ()
    for relative in common_directories + blueprint_directories:
        (project_dir / relative).mkdir(parents=True, exist_ok=True)
    generator = materialize_generator(
        project_dir,
        resolved_template,
        resolved_generator_template,
        production_mode=brief["production_mode"],
        page_count=brief["requested_page_count"],
    )
    if brief["production_mode"] == "blueprint":
        create_direct_state(project_dir, brief["requested_page_count"], batch_size=batch_size)
    return generator


def bootstrap_direct_project(
    project_dir: str | Path,
    *,
    batch_size: int = 5,
    template_path: str | Path | None = None,
    generator_template: str | Path | None = None,
) -> Path:
    """Compatibility wrapper for callers that used the V5.4 bootstrap name."""

    return bootstrap_project(
        project_dir,
        batch_size=batch_size,
        template_path=template_path,
        generator_template=generator_template,
    )


def validate_blueprint_composition(blueprint_path: Path) -> tuple[list[str], str | None]:
    sidecar = blueprint_path.with_suffix(".composition.json")
    if not sidecar.is_file():
        return [f"{blueprint_path.name}: deterministic composition.json is missing"], None
    try:
        record = _read_json(sidecar)
    except (OSError, json.JSONDecodeError) as exc:
        return [f"{blueprint_path.name}: composition.json is invalid: {exc}"], None
    errors: list[str] = []
    if record.get("schema_version") != SCHEMA_VERSION:
        errors.append(f"{blueprint_path.name}: composition schema_version must be {SCHEMA_VERSION}")
    if record.get("output_sha256") != sha256_file(blueprint_path):
        errors.append(f"{blueprint_path.name}: composition record does not bind the current blueprint")
    anchors = record.get("anchors")
    if not isinstance(anchors, dict) or len({anchors.get("chapter_left"), anchors.get("title_left"), anchors.get("core_left")}) != 1:
        errors.append(f"{blueprint_path.name}: composed top layers do not share one left anchor")
    if record.get("tops_px") != {"chapter": 19, "title": 71, "core": 128}:
        errors.append(f"{blueprint_path.name}: composed top positions must be 19/71/128 px")
    if record.get("complete_slide_reference") is not True:
        errors.append(f"{blueprint_path.name}: accepted blueprint must be a complete-slide visual reference")
    if record.get("raw_input_role") != "complete_slide_draft":
        errors.append(f"{blueprint_path.name}: raw ImageGen input must be recorded as complete_slide_draft")
    if record.get("forbidden_top_rule") is not False:
        errors.append(f"{blueprint_path.name}: composed blueprint contains a forbidden top rule")
    return errors, sha256_file(sidecar)


def _visible_character_count(value: str) -> int:
    return len(re.sub(r"\s+", "", value or ""))


def validate_core_points(points: Any) -> list[str]:
    errors: list[str] = []
    if not isinstance(points, list):
        return ["core_points must be a list"]
    if not 1 <= len(points) <= 2:
        errors.append("core_points must contain one or two points")
    if any(not isinstance(point, str) or not point.strip() for point in points):
        errors.append("every core point must be a non-empty string")
    total = sum(_visible_character_count(point) for point in points if isinstance(point, str))
    if not 80 <= total <= 160:
        errors.append(f"core_points must total 80–160 non-whitespace characters; got {total}")
    return errors


def validate_evidence_inventory(slide: Any) -> list[str]:
    """Validate source-evidence mapping without imposing a card or module quota."""

    if not isinstance(slide, dict):
        return ["slide evidence contract must be a dictionary"]
    slide_id = slide.get("slide_id", "?")
    modules = slide.get("modules")
    if not isinstance(modules, list) or not modules:
        return [f"{slide_id}: modules must exist before evidence mapping"]
    module_ids = {
        module.get("module_id")
        for module in modules
        if isinstance(module, dict) and isinstance(module.get("module_id"), str)
    }
    errors: list[str] = []
    primary = slide.get("primary_visual_module_id")
    if primary not in module_ids:
        errors.append(f"{slide_id}: primary_visual_module_id must reference a real module")
    inventory = slide.get("evidence_inventory")
    if not isinstance(inventory, list) or not inventory:
        errors.append(f"{slide_id}: evidence_inventory must be a non-empty source-evidence list")
        return errors
    seen: set[str] = set()
    high_priority = 0
    mapped_high_priority = 0
    for item in inventory:
        if not isinstance(item, dict):
            errors.append(f"{slide_id}: every evidence_inventory item must be a dictionary")
            continue
        evidence_id = item.get("evidence_id")
        if not isinstance(evidence_id, str) or not evidence_id.strip():
            errors.append(f"{slide_id}: every evidence item requires evidence_id")
        elif evidence_id in seen:
            errors.append(f"{slide_id}: duplicate evidence_id {evidence_id}")
        else:
            seen.add(evidence_id)
        if not isinstance(item.get("statement"), str) or not item["statement"].strip():
            errors.append(f"{slide_id}/{evidence_id or '?'}: evidence statement is required")
        priority = item.get("priority")
        if priority not in {"must_keep", "supporting", "optional"}:
            errors.append(f"{slide_id}/{evidence_id or '?'}: priority must be must_keep, supporting, or optional")
            continue
        module_id = item.get("module_id")
        if module_id is not None and module_id not in module_ids:
            errors.append(f"{slide_id}/{evidence_id or '?'}: module_id does not reference a real module")
        if priority in {"must_keep", "supporting"}:
            high_priority += 1
            if module_id in module_ids:
                mapped_high_priority += 1
        if priority == "must_keep" and module_id not in module_ids:
            errors.append(f"{slide_id}/{evidence_id or '?'}: must_keep evidence must map to a real module")
    if high_priority and mapped_high_priority / high_priority < 0.80:
        errors.append(
            f"{slide_id}: mapped must_keep/supporting evidence coverage must be at least 80%; "
            f"got {mapped_high_priority}/{high_priority}"
        )
    return errors


def validate_visual_inventory(
    slides: Any,
    *,
    production_mode: str,
    blueprints: dict[str, dict[str, str]] | None = None,
) -> list[str]:
    """Require an explicit visual review decision on every blueprint slide."""

    if production_mode != "blueprint":
        return []
    if not isinstance(slides, list):
        return ["SLIDES must be a list for visual inventory validation"]
    errors: list[str] = []
    for slide in slides:
        if not isinstance(slide, dict):
            continue
        slide_id = slide.get("slide_id", "?")
        review = slide.get("visual_review")
        visuals = slide.get("complex_visuals")
        inventory = slide.get("visual_inventory")
        review_evidence = slide.get("visual_review_evidence")
        if review not in {"extract_declared", "reviewed_no_raster"}:
            errors.append(f"{slide_id}: visual_review must be extract_declared or reviewed_no_raster")
            continue
        if not isinstance(visuals, list):
            errors.append(f"{slide_id}: complex_visuals must be a list after visual review")
            continue
        if not isinstance(inventory, list):
            errors.append(f"{slide_id}: visual_inventory must be a reviewed list")
            inventory = []
        required_classes = {"photo", "logo", "map", "pictogram", "decorative_motif"}
        if not isinstance(review_evidence, dict):
            errors.append(f"{slide_id}: visual_review_evidence is required after full-page review")
        else:
            blueprint_sha = review_evidence.get("blueprint_sha256")
            if not isinstance(blueprint_sha, str) or re.fullmatch(r"[0-9a-f]{64}", blueprint_sha) is None:
                errors.append(f"{slide_id}: visual_review_evidence requires a blueprint_sha256")
            elif blueprints is not None and slide_id in blueprints and blueprint_sha != blueprints[slide_id].get("sha256"):
                errors.append(f"{slide_id}: visual_review_evidence blueprint_sha256 does not match BLUEPRINTS")
            if review_evidence.get("full_page_reviewed") is not True:
                errors.append(f"{slide_id}: visual_review_evidence must record full_page_reviewed=true")
            checked = review_evidence.get("checked_classes")
            if not isinstance(checked, list) or not required_classes.issubset(set(checked)):
                errors.append(f"{slide_id}: visual_review_evidence must check all non-native subject classes")
            if not isinstance(review_evidence.get("decision_reason"), str) or not review_evidence["decision_reason"].strip():
                errors.append(f"{slide_id}: visual_review_evidence requires decision_reason")

        crop_ids: set[str] = set()
        visual_ids: set[str] = set()
        for item in inventory:
            if not isinstance(item, dict):
                errors.append(f"{slide_id}: every visual_inventory item must be a dictionary")
                continue
            visual_id = item.get("visual_id")
            if not isinstance(visual_id, str) or not visual_id.strip():
                errors.append(f"{slide_id}: every visual_inventory item requires visual_id")
            elif visual_id in visual_ids:
                errors.append(f"{slide_id}: duplicate visual_id {visual_id}")
            else:
                visual_ids.add(visual_id)
            if not all(isinstance(item.get(field), str) and item[field].strip() for field in ("kind", "description")):
                errors.append(f"{slide_id}/{visual_id or '?'}: kind and description are required")
            disposition = item.get("disposition")
            if disposition not in {"crop", "native_rebuild"}:
                errors.append(f"{slide_id}/{visual_id or '?'}: disposition must be crop or native_rebuild")
            if disposition == "crop":
                asset_id = item.get("asset_id")
                if not isinstance(asset_id, str) or not asset_id.strip():
                    errors.append(f"{slide_id}/{visual_id or '?'}: crop disposition requires asset_id")
                else:
                    crop_ids.add(asset_id)
            elif item.get("asset_id"):
                errors.append(f"{slide_id}/{visual_id or '?'}: native_rebuild must not carry asset_id")

        declared_ids = {
            visual.get("asset_id")
            for visual in visuals
            if isinstance(visual, dict) and isinstance(visual.get("asset_id"), str)
        }
        if crop_ids != declared_ids:
            errors.append(
                f"{slide_id}: crop dispositions and complex_visuals must match exactly; "
                f"crop={sorted(crop_ids)}, complex_visuals={sorted(declared_ids)}"
            )
        if review == "extract_declared" and not visuals:
            errors.append(f"{slide_id}: extract_declared requires at least one complex visual")
        if review == "reviewed_no_raster" and visuals:
            errors.append(f"{slide_id}: complex_visuals must be empty when visual_review is reviewed_no_raster")
        if review == "reviewed_no_raster" and crop_ids:
            errors.append(f"{slide_id}: reviewed_no_raster cannot retain crop dispositions")
        for visual in visuals:
            if not isinstance(visual, dict):
                errors.append(f"{slide_id}: every complex visual must be a dictionary")
                continue
            if not all(isinstance(visual.get(field), str) and visual[field].strip() for field in ("asset_id", "kind", "description")):
                errors.append(f"{slide_id}: every complex visual requires asset_id, kind, and description")
    return errors


def validate_complex_visual_assets(
    slides: Any,
    asset_crops: Any,
    project_dir: Path,
    *,
    require_files: bool,
) -> list[str]:
    """Require every declared non-native visual to have one bounded crop."""

    errors: list[str] = []
    if not isinstance(slides, list) or not isinstance(asset_crops, dict):
        return ["SLIDES and ASSET_CROPS must be literal collections for complex-visual validation"]
    declared: dict[str, str] = {}
    for slide in slides:
        if not isinstance(slide, dict):
            continue
        slide_id = slide.get("slide_id")
        visuals = slide.get("complex_visuals", [])
        if not isinstance(visuals, list):
            errors.append(f"{slide_id}: complex_visuals must be a list")
            continue
        for visual in visuals:
            if not isinstance(visual, dict) or not isinstance(visual.get("asset_id"), str):
                errors.append(f"{slide_id}: every complex visual requires an asset_id")
                continue
            asset_id = visual["asset_id"]
            if asset_id in declared:
                errors.append(f"{asset_id}: complex visual asset_id must be unique")
            declared[asset_id] = slide_id
    for asset_id, slide_id in declared.items():
        crop = asset_crops.get(asset_id)
        if not isinstance(crop, dict):
            errors.append(f"{slide_id}/{asset_id}: declared complex visual is missing from ASSET_CROPS")
            continue
        if crop.get("slide_id") != slide_id:
            errors.append(f"{slide_id}/{asset_id}: ASSET_CROPS slide_id mismatch")
        source_px = crop.get("source_px")
        target_box_in = crop.get("target_box_in")
        if not isinstance(source_px, list) or len(source_px) != 4:
            errors.append(f"{slide_id}/{asset_id}: source_px must contain four coordinates")
        elif not (source_px[0] < source_px[2] and source_px[1] < source_px[3]):
            errors.append(f"{slide_id}/{asset_id}: source_px must define a positive bounded rectangle")
        if not isinstance(target_box_in, list) or len(target_box_in) != 4:
            errors.append(f"{slide_id}/{asset_id}: target_box_in must contain four values")
        elif target_box_in[2] <= 0 or target_box_in[3] <= 0:
            errors.append(f"{slide_id}/{asset_id}: target_box_in width and height must be positive")
        elif target_box_in[0] < 0 or target_box_in[1] < 0 or target_box_in[0] + target_box_in[2] > 13.333334 or target_box_in[1] + target_box_in[3] > 7.5:
            errors.append(f"{slide_id}/{asset_id}: target_box_in must stay inside the slide")
        if crop.get("fit_mode") != "contain":
            errors.append(f"{slide_id}/{asset_id}: fit_mode must be contain")
        if not isinstance(crop.get("padding_px"), int) or not 0 <= crop["padding_px"] <= 24:
            errors.append(f"{slide_id}/{asset_id}: padding_px must be an integer from 0 to 24")
        if require_files:
            path = project_dir / ".build" / "assets" / slide_id / f"{asset_id}.png"
            if not path.is_file():
                errors.append(f"{slide_id}/{asset_id}: extracted crop file is missing")
    undeclared = sorted(set(asset_crops) - set(declared))
    for asset_id in undeclared:
        errors.append(f"{asset_id}: ASSET_CROPS entry is not declared in SLIDES complex_visuals")
    return errors


def validate_complex_visual_builder_usage(source: str, slides: Any) -> list[str]:
    """Require page builders to insert every declared complex visual explicitly."""

    errors: list[str] = []
    try:
        tree = ast.parse(source)
    except SyntaxError as exc:
        return [f"generator syntax error prevents asset-usage validation: {exc}"]
    builders = _builder_nodes(tree)
    for slide in slides if isinstance(slides, list) else []:
        if not isinstance(slide, dict):
            continue
        slide_id = slide.get("slide_id")
        node = builders.get(slide_id)
        visuals = slide.get("complex_visuals", [])
        if node is None or not isinstance(visuals, list):
            continue
        inserted: set[str] = set()
        for call in (item for item in ast.walk(node) if isinstance(item, ast.Call)):
            function_name = call.func.id if isinstance(call.func, ast.Name) else None
            if function_name != "add_blueprint_asset":
                continue
            inserted.update(
                argument.value
                for argument in call.args
                if isinstance(argument, ast.Constant) and isinstance(argument.value, str)
            )
        for visual in visuals:
            asset_id = visual.get("asset_id") if isinstance(visual, dict) else None
            if isinstance(asset_id, str) and asset_id not in inserted:
                errors.append(f"{slide_id}/{asset_id}: page builder must call add_blueprint_asset with this asset_id")
    return errors


def core_skeleton_metrics(
    points: Iterable[str],
    *,
    core_top: float = 2.7 / 2.54,
    core_width: float = 12.43,
    font_size_pt: float = 12.0,
    body_gap: float = 0.12,
) -> dict[str, float]:
    """Return an adaptive core box and body origin in slide inches.

    The estimate is deterministic and intentionally conservative. A generated
    deck should refine the estimate with PowerPoint TextRange.BoundHeight after
    inserting the real text, then move the body to the measured bottom edge.
    """

    normalized = [str(point).strip() for point in points if str(point).strip()]
    if not normalized:
        normalized = [""]
    usable_width_pt = max(1.0, core_width * 72.0 - 14.0)
    chars_per_line = max(18, int(usable_width_pt / (font_size_pt * 1.05)))
    line_count = sum(max(1, math.ceil(_visible_character_count(point) / chars_per_line)) for point in normalized)
    line_height = font_size_pt * 1.20 / 72.0
    paragraph_after = 6.0 / 72.0
    padding = 0.18
    measured_height = padding + line_count * line_height + max(0, len(normalized) - 1) * paragraph_after
    core_height = max(0.62, measured_height)
    core_bottom = core_top + core_height
    return {
        "core_top": round(core_top, 4),
        "core_height": round(core_height, 4),
        "core_bottom": round(core_bottom, 4),
        "body_top": round(core_bottom + body_gap, 4),
        "body_gap": round(body_gap, 4),
    }


def batch_slide_ids(page_count: int, batch_size: int = 5) -> list[list[str]]:
    if page_count <= 0:
        raise ValueError("page_count must be positive")
    if not 3 <= batch_size <= 5:
        raise ValueError("Direct Blueprint batch_size must be between 3 and 5")
    slide_ids = [f"S{index:02d}" for index in range(1, page_count + 1)]
    return [slide_ids[index : index + batch_size] for index in range(0, page_count, batch_size)]


def _literal_assignment(tree: ast.AST, name: str) -> Any | None:
    for node in getattr(tree, "body", []):
        if not isinstance(node, (ast.Assign, ast.AnnAssign)):
            continue
        targets = node.targets if isinstance(node, ast.Assign) else [node.target]
        if any(isinstance(target, ast.Name) and target.id == name for target in targets):
            try:
                return ast.literal_eval(node.value)
            except (TypeError, ValueError):
                return None
    return None


def _builder_mapping(tree: ast.AST) -> dict[str, str] | None:
    for node in getattr(tree, "body", []):
        if not isinstance(node, ast.Assign):
            continue
        if not any(isinstance(target, ast.Name) and target.id == "PAGE_BUILDERS" for target in node.targets):
            continue
        if not isinstance(node.value, ast.Dict):
            return None
        mapping: dict[str, str] = {}
        for key, value in zip(node.value.keys, node.value.values):
            if not isinstance(key, ast.Constant) or not isinstance(key.value, str):
                return None
            if not isinstance(value, ast.Name):
                return None
            mapping[key.value] = value.id
        return mapping
    return None


def _builder_nodes(tree: ast.AST) -> dict[str, ast.FunctionDef | ast.AsyncFunctionDef]:
    builders: dict[str, ast.FunctionDef | ast.AsyncFunctionDef] = {}
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        match = BUILDER_NAME_RE.fullmatch(node.name)
        if match:
            builders[match.group(1)] = node
    return builders


def _builder_has_work(node: ast.FunctionDef | ast.AsyncFunctionDef) -> bool:
    body = list(node.body)
    if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant):
        if isinstance(body[0].value.value, str):
            body = body[1:]
    return any(not isinstance(statement, ast.Pass) for statement in body)


def builder_source_hashes(source: str) -> dict[str, str]:
    tree = ast.parse(source)
    hashes: dict[str, str] = {}
    for slide_id, node in _builder_nodes(tree).items():
        segment = ast.get_source_segment(source, node)
        if segment is None:
            continue
        hashes[slide_id] = hashlib.sha256(segment.encode("utf-8")).hexdigest()
    return hashes


def shared_source_hash(source: str) -> str:
    """Hash imports, shared helpers, and build_deck while ignoring page data/builders."""

    tree = ast.parse(source)
    data_names = {"DECK_META", "SLIDES", "BLUEPRINTS", "ASSET_CROPS", "PAGE_BUILDERS"}
    retained: list[ast.stmt] = []
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and BUILDER_NAME_RE.fullmatch(node.name):
            continue
        if isinstance(node, ast.Assign):
            assigned = {
                target.id
                for target in node.targets
                if isinstance(target, ast.Name)
            }
            if assigned & data_names:
                continue
        if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name) and node.target.id in data_names:
            continue
        retained.append(node)
    normalized = ast.dump(ast.Module(body=retained, type_ignores=[]), include_attributes=False)
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def _safe_relative_path(value: Any, required_prefix: str) -> bool:
    if not isinstance(value, str) or not value.strip():
        return False
    normalized = value.replace("\\", "/")
    path = Path(normalized)
    return not path.is_absolute() and ".." not in path.parts and path.parts and path.parts[0] == required_prefix


def _blueprint_records(tree: ast.AST) -> dict[str, dict[str, str]] | None:
    value = _literal_assignment(tree, "BLUEPRINTS")
    if not isinstance(value, dict):
        return None
    records: dict[str, dict[str, str]] = {}
    for slide_id, record in value.items():
        if not isinstance(slide_id, str) or not isinstance(record, dict):
            return None
        path = record.get("path")
        sha256 = record.get("sha256")
        if not isinstance(path, str) or not isinstance(sha256, str):
            return None
        records[slide_id] = {"path": path, "sha256": sha256}
    return records


def _asset_crop_records(tree: ast.AST) -> dict[str, dict[str, Any]] | None:
    value = _literal_assignment(tree, "ASSET_CROPS")
    if not isinstance(value, dict):
        return None
    records: dict[str, dict[str, Any]] = {}
    for asset_id, record in value.items():
        if not isinstance(asset_id, str) or not isinstance(record, dict):
            return None
        records[asset_id] = record
    return records


def _slide_asset_evidence_errors(
    project_dir: Path,
    slide_id: str,
    page: dict[str, Any],
    asset_crops: dict[str, dict[str, Any]],
) -> list[str]:
    errors: list[str] = []
    declared_ids = sorted(
        asset_id
        for asset_id, record in asset_crops.items()
        if record.get("slide_id") == slide_id
    )
    recorded = page.get("assets")
    if not isinstance(recorded, list):
        return [f"{slide_id}: asset evidence list is missing"]
    recorded_by_id = {
        item.get("asset_id"): item
        for item in recorded
        if isinstance(item, dict) and isinstance(item.get("asset_id"), str)
    }
    if sorted(recorded_by_id) != declared_ids or page.get("asset_count") != len(declared_ids):
        errors.append(f"{slide_id}: asset evidence does not match declared ASSET_CROPS")
        return errors
    for asset_id in declared_ids:
        expected_relative = f".build/assets/{slide_id}/{asset_id}.png"
        item = recorded_by_id[asset_id]
        if item.get("path") != expected_relative:
            errors.append(f"{slide_id}/{asset_id}: asset evidence path mismatch")
            continue
        asset_path = project_dir / expected_relative
        if not asset_path.is_file():
            errors.append(f"{slide_id}/{asset_id}: extracted asset file is missing")
            continue
        if item.get("sha256") != sha256_file(asset_path):
            errors.append(f"{slide_id}/{asset_id}: extracted asset SHA-256 mismatch")
    return errors


def validate_generator_source(
    source: str,
    *,
    expected_page_count: int,
    mode: str,
) -> list[str]:
    errors: list[str] = []
    try:
        tree = ast.parse(source)
    except SyntaxError as exc:
        return [f"generator syntax error: {exc}"]

    lowered = source.lower()
    if mode == "blueprint":
        for token in FORBIDDEN_BLUEPRINT_TOKENS:
            if token in lowered:
                errors.append(f"blueprint generator contains forbidden fast-mode token: {token}")

    has_modulo = any(isinstance(node, ast.BinOp) and isinstance(node.op, ast.Mod) for node in ast.walk(tree))
    layout_names = {
        node.id.lower()
        for node in ast.walk(tree)
        if isinstance(node, ast.Name) and "layout" in node.id.lower()
    }
    if mode == "blueprint" and has_modulo and layout_names:
        errors.append("fixed-layout cycling is forbidden; blueprint mode requires page-specific builders")

    generic_builders = [
        node.name
        for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == "build_slide"
    ]
    builder_nodes = _builder_nodes(tree)
    builder_ids = set(builder_nodes)
    expected_ids = {f"S{index:02d}" for index in range(1, expected_page_count + 1)}
    if generic_builders:
        errors.append("generic build_slide is not sufficient; use page-specific build_slide_SNN functions")
    if builder_ids != expected_ids:
        missing = sorted(expected_ids - builder_ids)
        extra = sorted(builder_ids - expected_ids)
        errors.append(f"page-specific builder mismatch; missing={missing}, extra={extra}")
    for slide_id, node in sorted(builder_nodes.items()):
        if not _builder_has_work(node):
            errors.append(f"page-specific builder {slide_id} is empty")
        positional = list(node.args.posonlyargs) + list(node.args.args)
        if len(positional) != 5 or node.args.vararg or node.args.kwarg or node.args.kwonlyargs:
            errors.append(
                f"page-specific builder {slide_id} signature must have exactly five positional arguments"
            )

    mapping = _builder_mapping(tree)
    mapping_keys = set(mapping or {})
    if mapping_keys != expected_ids:
        errors.append(
            f"PAGE_BUILDERS must map every final slide exactly once; expected={sorted(expected_ids)}, got={sorted(mapping_keys or set())}"
        )
    if mapping:
        for slide_id, function_name in sorted(mapping.items()):
            expected_name = f"build_slide_{slide_id}"
            if function_name != expected_name:
                errors.append(
                    f"PAGE_BUILDERS mapping value for {slide_id} must be {expected_name}; got {function_name}"
                )

    meta = _literal_assignment(tree, "DECK_META")
    if not isinstance(meta, dict):
        errors.append("DECK_META must be a literal dictionary")
    else:
        if meta.get("schema_version") != PROJECT_SCHEMA_VERSION:
            errors.append(f"DECK_META schema_version must be {PROJECT_SCHEMA_VERSION}")
        if meta.get("production_mode") != mode:
            errors.append("DECK_META production_mode does not match project brief")
        if meta.get("page_count") != expected_page_count:
            errors.append("DECK_META page_count does not match project brief")
        if not isinstance(meta.get("template_path"), str) or not meta.get("template_path"):
            errors.append("DECK_META template_path is required")
        if not re.fullmatch(r"[0-9a-f]{64}", str(meta.get("template_sha256", ""))):
            errors.append("DECK_META template_sha256 must be 64 lowercase hex characters")

    slides = _literal_assignment(tree, "SLIDES")
    if not isinstance(slides, list) or len(slides) != expected_page_count:
        errors.append("SLIDES must be a literal list matching the final page count")
    else:
        slide_ids = [slide.get("slide_id") for slide in slides if isinstance(slide, dict)]
        expected_order = [f"S{index:02d}" for index in range(1, expected_page_count + 1)]
        if slide_ids != expected_order:
            errors.append("SLIDES must contain ordered SNN slide IDs exactly once")
        for slide in slides:
            if not isinstance(slide, dict):
                errors.append("every SLIDES entry must be a dictionary")
                continue
            slide_id = slide.get("slide_id", "?")
            for field in (
                "chapter",
                "title",
                "core_points",
                "source",
                "page_type",
                "layout_intent",
                "density_profile",
                "modules",
                "primary_visual_module_id",
                "evidence_inventory",
            ):
                if field not in slide:
                    errors.append(f"{slide_id}: required field {field} is missing")
            for error in validate_core_points(slide.get("core_points")):
                errors.append(f"{slide_id}: {error}")
            if slide.get("density_profile") != "medium":
                errors.append(f"{slide_id}: density_profile must be medium")
            modules = slide.get("modules")
            if not isinstance(modules, list) or not modules:
                errors.append(f"{slide_id}: modules must be a non-empty list")
            else:
                module_ids = [module.get("module_id") for module in modules if isinstance(module, dict)]
                if len(module_ids) != len(modules) or any(not isinstance(module_id, str) or not module_id for module_id in module_ids):
                    errors.append(f"{slide_id}: every module requires a non-empty internal module_id")
                elif len(set(module_ids)) != len(module_ids):
                    errors.append(f"{slide_id}: module_id values must be unique")
                for module in modules:
                    if not isinstance(module, dict):
                        continue
                    if ("display_order" in module or "display_number" in module) and not module.get("ordered"):
                        errors.append(
                            f"{slide_id}/{module.get('module_id', '?')}: visible numbering requires ordered: true"
                        )
            errors.extend(validate_evidence_inventory(slide))

    blueprints = _blueprint_records(tree)
    if mode == "blueprint":
        if not isinstance(blueprints, dict) or set(blueprints) != expected_ids:
            errors.append("BLUEPRINTS must be a literal SNN-to-record mapping for every final slide")
        else:
            for slide_id, record in blueprints.items():
                if not _safe_relative_path(record.get("path"), "blueprints"):
                    errors.append(f"{slide_id}: BLUEPRINTS path must stay inside blueprints/")
                if not re.fullmatch(r"[0-9a-f]{64}", record.get("sha256", "")):
                    errors.append(f"{slide_id}: BLUEPRINTS sha256 must be 64 lowercase hex characters")

    asset_crops = _asset_crop_records(tree)
    if not isinstance(asset_crops, dict):
        errors.append("ASSET_CROPS must be a literal dictionary")
    else:
        for asset_id, record in asset_crops.items():
            slide_id = record.get("slide_id")
            source_px = record.get("source_px")
            target_box_in = record.get("target_box_in")
            if slide_id not in expected_ids:
                errors.append(f"{asset_id}: asset slide_id must reference a final slide")
            if not isinstance(source_px, list) or len(source_px) != 4 or not all(isinstance(value, (int, float)) for value in source_px):
                errors.append(f"{asset_id}: source_px must contain four numeric coordinates")
            if not isinstance(target_box_in, list) or len(target_box_in) != 4 or not all(isinstance(value, (int, float)) for value in target_box_in):
                errors.append(f"{asset_id}: target_box_in must contain four numeric values")
    if isinstance(slides, list) and isinstance(asset_crops, dict):
        errors.extend(validate_visual_inventory(slides, production_mode=mode, blueprints=blueprints))
        errors.extend(validate_complex_visual_assets(slides, asset_crops, Path("."), require_files=False))
        errors.extend(validate_complex_visual_builder_usage(source, slides))

    function_names = {
        node.name
        for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }
    if "build_deck" not in function_names:
        errors.append("generator must define build_deck()")

    return errors


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _load_fidelity_module():
    module_path = Path(__file__).resolve().with_name("blueprint_fidelity.py")
    spec = importlib.util.spec_from_file_location("standard_report_ppt_blueprint_fidelity_runtime", module_path)
    if spec is None or spec.loader is None:
        raise RuntimeError("could not load blueprint fidelity validator")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _status_at_least(status: str, required: str) -> bool:
    return status in PAGE_STATUS_ORDER and PAGE_STATUS_ORDER.index(status) >= PAGE_STATUS_ORDER.index(required)


def _expected_mode_lock(brief_path: Path, brief: dict[str, Any], batch_size: int) -> dict[str, Any]:
    return {
        "production_mode": brief.get("production_mode"),
        "blueprint_engine": brief.get("blueprint_engine"),
        "brief_sha256": sha256_file(brief_path),
        "page_count": brief.get("requested_page_count"),
        "batch_size": batch_size,
    }


def validate_direct_project(
    project_dir: str | Path,
    *,
    require_accepted: bool = True,
) -> list[str]:
    project_dir = Path(project_dir)
    errors: list[str] = []
    brief_path = project_dir / "project_brief.json"
    if not brief_path.is_file():
        return ["project_brief.json is required"]
    try:
        brief = _read_json(brief_path)
    except (OSError, json.JSONDecodeError) as exc:
        return [f"project_brief.json is invalid: {exc}"]

    page_count = brief.get("requested_page_count")
    mode = brief.get("production_mode")
    errors.extend(validate_v55_brief(brief))
    if not isinstance(page_count, int) or page_count <= 0:
        errors.append("project brief requires a positive requested_page_count")
        return errors
    if mode not in {"blueprint", "fast"}:
        errors.append("project brief production_mode must be blueprint or fast")
        return errors
    if brief.get("confirmation_source") not in {"user_explicit", "user_selected"}:
        errors.append("production mode must be explicitly confirmed by the user")
    if mode == "blueprint" and brief.get("blueprint_engine") != "direct":
        errors.append("V5 blueprint projects must lock blueprint_engine to direct")

    python_files = sorted(path for path in project_dir.rglob("*.py") if path.is_file())
    generator = project_dir / "generate_deck.py"
    if python_files != [generator]:
        errors.append(
            "project must contain exactly one Python file named generate_deck.py; "
            f"found={[path.relative_to(project_dir).as_posix() for path in python_files]}"
        )
    generator_source = generator.read_text(encoding="utf-8") if generator.is_file() else ""
    generator_hash = sha256_file(generator) if generator.is_file() else None
    try:
        generator_tree = ast.parse(generator_source) if generator_source else None
        shared_hash = shared_source_hash(generator_source) if generator_source else None
    except SyntaxError:
        generator_tree = None
        shared_hash = None
    generator_blueprints = _blueprint_records(generator_tree) if generator_tree is not None else None
    generator_asset_crops = _asset_crop_records(generator_tree) if generator_tree is not None else None
    generator_slides = _literal_assignment(generator_tree, "SLIDES") if generator_tree is not None else None
    generator_meta = _literal_assignment(generator_tree, "DECK_META") if generator_tree is not None else None
    builder_hashes = builder_source_hashes(generator_source) if generator_source else {}
    if generator_source:
        errors.extend(
            validate_generator_source(
                generator_source,
                expected_page_count=page_count,
                mode=mode,
            )
        )
    if isinstance(generator_meta, dict):
        template_value = generator_meta.get("template_path")
        template_path = Path(template_value).expanduser() if isinstance(template_value, str) else None
        if template_path is not None and not template_path.is_absolute():
            template_path = project_dir / template_path
        if template_path is None or not template_path.is_file():
            errors.append("DECK_META template_path does not resolve to a file")
        elif generator_meta.get("template_sha256") != sha256_file(template_path):
            errors.append("DECK_META template_sha256 does not match the company template")
    if mode == "blueprint" and isinstance(generator_slides, list) and isinstance(generator_asset_crops, dict):
        errors.extend(
            validate_visual_inventory(
                generator_slides,
                production_mode=mode,
                blueprints=generator_blueprints,
            )
        )
        errors.extend(
            validate_complex_visual_assets(
                generator_slides,
                generator_asset_crops,
                project_dir,
                require_files=require_accepted,
            )
        )

    if mode == "blueprint":
        state_path = project_dir / "direct_blueprint_state.json"
        if not state_path.is_file():
            errors.append("direct_blueprint_state.json is required in blueprint mode")
            return errors
        try:
            state = _read_json(state_path)
        except (OSError, json.JSONDecodeError) as exc:
            errors.append(f"direct_blueprint_state.json is invalid: {exc}")
            return errors
        pages = state.get("pages")
        if not isinstance(pages, list):
            errors.append("direct_blueprint_state pages must be a list")
            return errors
        expected_ids = [f"S{index:02d}" for index in range(1, page_count + 1)]
        mode_lock = state.get("mode_lock")
        if not isinstance(mode_lock, dict):
            errors.append("direct_blueprint_state requires a mode_lock")
        else:
            batch_size = mode_lock.get("batch_size")
            if not isinstance(batch_size, int) or not 3 <= batch_size <= 5:
                errors.append("mode_lock batch_size must be between 3 and 5")
            else:
                expected_lock = _expected_mode_lock(brief_path, brief, batch_size)
                if mode_lock != expected_lock:
                    errors.append("mode_lock does not match the current brief; resume is forbidden after mode/page changes")
        actual_ids = [page.get("slide_id") for page in pages if isinstance(page, dict)]
        if actual_ids != expected_ids:
            errors.append(f"state page order/count mismatch; expected={expected_ids}, got={actual_ids}")
        by_id = {page.get("slide_id"): page for page in pages if isinstance(page, dict)}
        for slide_id in expected_ids:
            page = by_id.get(slide_id)
            if not page:
                errors.append(f"{slide_id}: state entry missing")
                continue
            status = page.get("status")
            if status not in PAGE_STATUS_ORDER:
                errors.append(f"{slide_id}: invalid page status {status!r}")
            elif require_accepted and status != FINAL_PAGE_STATUS:
                errors.append(f"{slide_id}: status must be accepted before final validation or packaging")
            elif not require_accepted and PAGE_STATUS_ORDER.index(status) < PAGE_STATUS_ORDER.index("assets_extracted"):
                errors.append(f"{slide_id}: status must reach assets_extracted before building the whole deck")
            relative = page.get("blueprint_path")
            if not _safe_relative_path(relative, "blueprints"):
                errors.append(f"{slide_id}: blueprint path must stay inside blueprints/")
                blueprint_path = None
            else:
                blueprint_path = project_dir / relative
            if blueprint_path is None or not blueprint_path.is_file():
                errors.append(f"{slide_id}: blueprint file is missing")
                continue
            expected_hash = page.get("blueprint_sha256")
            actual_hash = sha256_file(blueprint_path)
            if expected_hash != actual_hash:
                errors.append(f"{slide_id}: blueprint SHA-256 mismatch")
            composition_errors, composition_hash = validate_blueprint_composition(blueprint_path)
            errors.extend(f"{slide_id}: {error}" for error in composition_errors)
            if composition_hash is not None and page.get("composition_sha256") != composition_hash:
                errors.append(f"{slide_id}: composition evidence SHA-256 mismatch")
            generator_record = (generator_blueprints or {}).get(slide_id)
            if not generator_record:
                errors.append(f"{slide_id}: generator BLUEPRINTS record is missing")
            elif generator_record.get("path") != relative or generator_record.get("sha256") != actual_hash:
                errors.append(f"{slide_id}: generator BLUEPRINTS record does not match the locked blueprint")

            if _status_at_least(status, "builder_written"):
                expected_builder_name = f"build_slide_{slide_id}"
                if page.get("builder_name") != expected_builder_name:
                    errors.append(f"{slide_id}: builder_name must be {expected_builder_name}")
                actual_builder_hash = builder_hashes.get(slide_id)
                if not actual_builder_hash or page.get("builder_sha256") != actual_builder_hash:
                    errors.append(f"{slide_id}: builder SHA-256 mismatch or missing builder evidence")

            if _status_at_least(status, "assets_extracted"):
                if page.get("shared_sha256") != shared_hash:
                    errors.append(f"{slide_id}: shared generator helper SHA-256 mismatch")
                if require_accepted and page.get("generator_sha256") != generator_hash:
                    errors.append(f"{slide_id}: final generator SHA-256 mismatch")
                if isinstance(generator_asset_crops, dict):
                    errors.extend(
                        _slide_asset_evidence_errors(project_dir, slide_id, page, generator_asset_crops)
                    )
                else:
                    errors.append(f"{slide_id}: ASSET_CROPS cannot be validated")

            render_path: Path | None = None
            render_hash: str | None = None
            if _status_at_least(status, "rendered"):
                render_relative = page.get("render_path")
                normalized_render = render_relative.replace("\\", "/") if isinstance(render_relative, str) else ""
                if not normalized_render.startswith(".build/rendered/current/") or not _safe_relative_path(
                    render_relative, ".build"
                ):
                    errors.append(f"{slide_id}: render path must stay inside .build/rendered/current/")
                else:
                    render_path = project_dir / render_relative
                    if not render_path.is_file():
                        errors.append(f"{slide_id}: render file is missing")
                    else:
                        render_hash = sha256_file(render_path)
                        if page.get("render_sha256") != render_hash:
                            errors.append(f"{slide_id}: render SHA-256 mismatch")

            if _status_at_least(status, "visually_compared"):
                comparison = page.get("comparison")
                if not isinstance(comparison, dict):
                    errors.append(f"{slide_id}: comparison evidence is missing")
                elif render_path is None or render_hash is None:
                    errors.append(f"{slide_id}: comparison cannot be validated without a render")
                else:
                    if comparison.get("blueprint_sha256") != actual_hash or comparison.get("render_sha256") != render_hash:
                        errors.append(f"{slide_id}: comparison hashes do not bind the current blueprint and render")
                    try:
                        fidelity = _load_fidelity_module().compare_slide(blueprint_path, render_path)
                    except Exception as exc:
                        errors.append(f"{slide_id}: fidelity comparison failed: {exc}")
                    else:
                        if not fidelity.get("passed"):
                            errors.append(f"{slide_id}: fidelity comparison did not pass")
                        if comparison.get("passed") is not True:
                            errors.append(f"{slide_id}: comparison evidence must record passed=true")
                        recorded_score = comparison.get("score")
                        if not isinstance(recorded_score, (int, float)) or abs(recorded_score - fidelity["score"]) > 0.0002:
                            errors.append(f"{slide_id}: comparison score does not match the recomputed fidelity score")

    if require_accepted:
        audit_path = project_dir / ".build" / "ppt_skeleton_audit.json"
        if not audit_path.is_file():
            errors.append("final skeleton audit is missing: .build/ppt_skeleton_audit.json")
        else:
            try:
                audit = _read_json(audit_path)
            except (OSError, json.JSONDecodeError) as exc:
                errors.append(f"final skeleton audit is invalid: {exc}")
            else:
                if audit.get("schema_version") != SCHEMA_VERSION:
                    errors.append(f"final skeleton audit schema_version must be {SCHEMA_VERSION}")
                if audit.get("ok") is not True:
                    errors.append("final skeleton audit did not pass")
                if audit.get("pages") != page_count:
                    errors.append("final skeleton audit page count mismatch")
        asset_audit_path = project_dir / ".build" / "ppt_asset_audit.json"
        if mode == "blueprint" and not asset_audit_path.is_file():
            errors.append("final asset audit is missing: .build/ppt_asset_audit.json")
        elif mode == "blueprint":
            try:
                asset_audit = _read_json(asset_audit_path)
            except (OSError, json.JSONDecodeError) as exc:
                errors.append(f"final asset audit is invalid: {exc}")
            else:
                if asset_audit.get("schema_version") != SCHEMA_VERSION:
                    errors.append(f"final asset audit schema_version must be {SCHEMA_VERSION}")
                if asset_audit.get("ok") is not True:
                    errors.append("final asset audit did not pass")
                if asset_audit.get("complete_inventory") is not True:
                    errors.append("final asset audit did not confirm a complete visual inventory")
                if asset_audit.get("declared_assets") != asset_audit.get("inserted_assets"):
                    errors.append("final asset audit declared/inserted counts do not match")

    return errors


def _write_json_atomic(path: Path, payload: Any) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def _accepted_page_evidence_errors(
    project_dir: Path,
    pages: list[dict[str, Any]],
) -> list[str]:
    if not pages:
        return []
    errors: list[str] = []
    generator = project_dir / "generate_deck.py"
    if not generator.is_file():
        return ["accepted-page evidence requires generate_deck.py"]
    source = generator.read_text(encoding="utf-8")
    shared_hash = shared_source_hash(source)
    builder_hashes = builder_source_hashes(source)
    try:
        asset_crops = _asset_crop_records(ast.parse(source))
    except SyntaxError as exc:
        return [f"accepted-page generator syntax is invalid: {exc}"]
    if not isinstance(asset_crops, dict):
        return ["accepted-page evidence requires a literal ASSET_CROPS dictionary"]
    fidelity = _load_fidelity_module()
    for page in pages:
        slide_id = page.get("slide_id", "?")
        if page.get("status") != FINAL_PAGE_STATUS:
            errors.append(f"{slide_id}: previous page is not accepted")
            continue
        required = (
            "blueprint_path",
            "blueprint_sha256",
            "composition_sha256",
            "builder_name",
            "builder_sha256",
            "generator_sha256",
            "shared_sha256",
            "asset_count",
            "assets",
            "render_path",
            "render_sha256",
            "comparison",
        )
        missing = [field for field in required if field not in page]
        if missing:
            errors.append(f"{slide_id}: accepted-page evidence is missing {missing}")
            continue
        blueprint = project_dir / page["blueprint_path"]
        render = project_dir / page["render_path"]
        if not blueprint.is_file() or not render.is_file():
            errors.append(f"{slide_id}: accepted-page evidence file is missing")
            continue
        blueprint_hash = sha256_file(blueprint)
        render_hash = sha256_file(render)
        if page["blueprint_sha256"] != blueprint_hash or page["render_sha256"] != render_hash:
            errors.append(f"{slide_id}: accepted-page evidence hash mismatch")
        composition_errors, composition_hash = validate_blueprint_composition(blueprint)
        errors.extend(f"{slide_id}: {error}" for error in composition_errors)
        if composition_hash is not None and page.get("composition_sha256") != composition_hash:
            errors.append(f"{slide_id}: accepted-page composition evidence is stale")
        if page["shared_sha256"] != shared_hash:
            errors.append(f"{slide_id}: accepted-page shared-helper evidence is stale")
        if page["builder_name"] != f"build_slide_{slide_id}" or page["builder_sha256"] != builder_hashes.get(slide_id):
            errors.append(f"{slide_id}: accepted-page builder evidence is stale")
        errors.extend(_slide_asset_evidence_errors(project_dir, slide_id, page, asset_crops))
        comparison = page.get("comparison")
        if not isinstance(comparison, dict) or comparison.get("passed") is not True:
            errors.append(f"{slide_id}: accepted-page comparison evidence is missing")
            continue
        if comparison.get("blueprint_sha256") != blueprint_hash or comparison.get("render_sha256") != render_hash:
            errors.append(f"{slide_id}: accepted-page comparison evidence is not bound to current files")
            continue
        try:
            result = fidelity.compare_slide(blueprint, render)
        except Exception as exc:
            errors.append(f"{slide_id}: accepted-page fidelity evidence failed: {exc}")
        else:
            if not result.get("passed"):
                errors.append(f"{slide_id}: accepted-page fidelity evidence did not pass")
    return errors


def create_direct_state(project_dir: str | Path, page_count: int, *, batch_size: int = 5) -> Path:
    if page_count <= 0:
        raise ValueError("page_count must be positive")
    if not 3 <= batch_size <= 5:
        raise ValueError("Direct Blueprint batch_size must be between 3 and 5")
    project_dir = Path(project_dir)
    state_path = project_dir / "direct_blueprint_state.json"
    if state_path.exists():
        raise FileExistsError(state_path)
    project_dir.mkdir(parents=True, exist_ok=True)
    brief_path = project_dir / "project_brief.json"
    if not brief_path.is_file():
        raise FileNotFoundError("project_brief.json must exist before state initialization")
    brief = _read_json(brief_path)
    if brief.get("requested_page_count") != page_count:
        raise ValueError("state page_count must match project_brief.json")
    brief_errors = validate_v55_brief(brief)
    if brief_errors or brief.get("production_mode") != "blueprint":
        raise ValueError("state initialization requires a valid V5.5 blueprint brief")
    if brief.get("blueprint_engine") != "direct":
        raise ValueError("state initialization requires blueprint_engine: direct")
    payload = {
        "schema_version": PROJECT_SCHEMA_VERSION,
        "page_count": page_count,
        "mode_lock": _expected_mode_lock(brief_path, brief, batch_size),
        "pages": [
            {"slide_id": f"S{index:02d}", "status": PENDING_PAGE_STATUS}
            for index in range(1, page_count + 1)
        ],
    }
    _write_json_atomic(state_path, payload)
    return state_path


def advance_page_status(
    project_dir: str | Path,
    slide_id: str,
    new_status: str,
    **updates: Any,
) -> dict[str, Any]:
    if new_status not in PAGE_STATUS_ORDER:
        raise ValueError(f"unknown page status: {new_status}")
    state_path = Path(project_dir) / "direct_blueprint_state.json"
    state = _read_json(state_path)
    pages = state.get("pages", [])
    page = next((entry for entry in pages if entry.get("slide_id") == slide_id), None)
    if page is None:
        raise KeyError(slide_id)
    current = page.get("status", PENDING_PAGE_STATUS)
    expected_index = 0 if current == PENDING_PAGE_STATUS else PAGE_STATUS_ORDER.index(current) + 1
    if expected_index >= len(PAGE_STATUS_ORDER) or PAGE_STATUS_ORDER[expected_index] != new_status:
        expected = None if expected_index >= len(PAGE_STATUS_ORDER) else PAGE_STATUS_ORDER[expected_index]
        raise ValueError(f"{slide_id}: invalid transition {current!r} → {new_status!r}; expected {expected!r}")

    mode_lock = state.get("mode_lock")
    if not isinstance(mode_lock, dict):
        raise ValueError("state mode_lock is missing")
    batch_size = mode_lock.get("batch_size")
    if not isinstance(batch_size, int) or not 3 <= batch_size <= 5:
        raise ValueError("state mode_lock batch_size is invalid")
    brief_path = Path(project_dir) / "project_brief.json"
    if not brief_path.is_file():
        raise FileNotFoundError(brief_path)
    brief = _read_json(brief_path)
    if mode_lock != _expected_mode_lock(brief_path, brief, batch_size):
        raise ValueError("mode_lock does not match the current brief; resume is forbidden")
    page_index = next(index for index, entry in enumerate(pages) if entry is page)
    batch_start = (page_index // batch_size) * batch_size
    if any(entry.get("status") != FINAL_PAGE_STATUS for entry in pages[:batch_start]):
        raise ValueError(f"{slide_id}: the preceding batch must be accepted before this batch can advance")
    batch_end = min(batch_start + batch_size, len(pages))
    batch_has_started = any(
        entry.get("status") != PENDING_PAGE_STATUS
        for entry in pages[batch_start:batch_end]
        if entry is not page
    )
    if batch_start and new_status == "blueprint_saved" and not batch_has_started:
        prefix_errors = _accepted_page_evidence_errors(Path(project_dir), pages[:batch_start])
        if prefix_errors:
            raise ValueError("preceding batch accepted-page evidence is invalid:\n- " + "\n- ".join(prefix_errors))

    project_dir = Path(project_dir)
    if new_status == "blueprint_saved":
        relative = updates.get("blueprint_path")
        if not _safe_relative_path(relative, "blueprints"):
            raise ValueError(f"{slide_id}: blueprint_path must stay inside blueprints/")
        blueprint = project_dir / relative
        if not blueprint.is_file():
            raise FileNotFoundError(blueprint)
        composition_errors, composition_hash = validate_blueprint_composition(blueprint)
        if composition_errors:
            raise ValueError(f"{slide_id}: invalid deterministic blueprint composition:\n- " + "\n- ".join(composition_errors))
        updates["blueprint_sha256"] = sha256_file(blueprint)
        updates["composition_sha256"] = composition_hash
    elif new_status == "builder_written":
        generator = project_dir / "generate_deck.py"
        if not generator.is_file():
            raise FileNotFoundError(generator)
        source = generator.read_text(encoding="utf-8")
        builder_hash = builder_source_hashes(source).get(slide_id)
        if not builder_hash:
            raise ValueError(f"{slide_id}: build_slide_{slide_id} is missing")
        updates["builder_name"] = f"build_slide_{slide_id}"
        updates["builder_sha256"] = builder_hash
    elif new_status == "assets_extracted":
        generator = project_dir / "generate_deck.py"
        if not generator.is_file():
            raise FileNotFoundError(generator)
        source = generator.read_text(encoding="utf-8")
        try:
            asset_crops = _asset_crop_records(ast.parse(source))
        except SyntaxError as exc:
            raise ValueError(f"generator syntax is invalid: {exc}") from exc
        if not isinstance(asset_crops, dict):
            raise ValueError("ASSET_CROPS must be a literal dictionary before assets_extracted")
        report_path = project_dir / ".build" / "direct_asset_report.json"
        if not report_path.is_file():
            raise FileNotFoundError("run extract_direct_assets.py before assets_extracted")
        report = _read_json(report_path)
        if (
            report.get("schema_version") != SCHEMA_VERSION
            or report.get("ok") is not True
            or report.get("complete_inventory") is not True
            or report.get("declared_assets") != report.get("extracted_assets")
        ):
                raise ValueError("direct asset extraction report must be a passing V5.5 complete-inventory report")
        declared_ids = sorted(
            asset_id
            for asset_id, record in asset_crops.items()
            if record.get("slide_id") == slide_id
        )
        asset_evidence: list[dict[str, str]] = []
        for asset_id in declared_ids:
            relative = f".build/assets/{slide_id}/{asset_id}.png"
            asset_path = project_dir / relative
            if not asset_path.is_file():
                raise FileNotFoundError(f"{slide_id}/{asset_id}: declared extracted asset is missing: {asset_path}")
            asset_evidence.append(
                {"asset_id": asset_id, "path": relative, "sha256": sha256_file(asset_path)}
            )
        updates["generator_sha256"] = sha256_file(generator)
        updates["shared_sha256"] = shared_source_hash(source)
        updates["asset_count"] = len(asset_evidence)
        updates["assets"] = asset_evidence
    elif new_status == "rendered":
        relative = updates.get("render_path")
        normalized = relative.replace("\\", "/") if isinstance(relative, str) else ""
        if not normalized.startswith(".build/rendered/current/") or not _safe_relative_path(relative, ".build"):
            raise ValueError(f"{slide_id}: render_path must stay inside .build/rendered/current/")
        render = project_dir / relative
        if not render.is_file():
            raise FileNotFoundError(render)
        updates["render_sha256"] = sha256_file(render)
    elif new_status == "visually_compared":
        blueprint = project_dir / page["blueprint_path"]
        render = project_dir / page["render_path"]
        result = _load_fidelity_module().compare_slide(blueprint, render)
        if not result.get("passed"):
            raise ValueError(f"{slide_id}: blueprint fidelity score {result['score']} did not pass")
        updates["comparison"] = {
            "blueprint_sha256": page["blueprint_sha256"],
            "render_sha256": page["render_sha256"],
            "score": result["score"],
            "threshold": result["threshold"],
            "passed": True,
        }
    elif new_status == FINAL_PAGE_STATUS:
        comparison = page.get("comparison")
        if not isinstance(comparison, dict) or comparison.get("passed") is not True:
            raise ValueError(f"{slide_id}: comparison must pass before acceptance")

    page.update(updates)
    page["status"] = new_status
    _write_json_atomic(state_path, state)
    return page


def next_incomplete_batch(project_dir: str | Path, batch_size: int | None = None) -> list[str]:
    project_dir = Path(project_dir)
    state = _read_json(project_dir / "direct_blueprint_state.json")
    locked_size = state.get("mode_lock", {}).get("batch_size")
    effective_size = batch_size or locked_size
    if not isinstance(effective_size, int) or not 3 <= effective_size <= 5:
        raise ValueError("Direct Blueprint batch_size must be between 3 and 5")
    pages = state.get("pages", [])
    first_incomplete = next(
        (index for index, page in enumerate(pages) if page.get("status") != FINAL_PAGE_STATUS),
        None,
    )
    if first_incomplete is None:
        return []
    batch_start = (first_incomplete // effective_size) * effective_size
    prefix_errors = _accepted_page_evidence_errors(project_dir, pages[:batch_start])
    if prefix_errors:
        raise ValueError("accepted-page evidence is invalid:\n- " + "\n- ".join(prefix_errors))
    return [
        page["slide_id"]
        for page in pages[batch_start : batch_start + effective_size]
        if page.get("status") != FINAL_PAGE_STATUS
    ]


def invalidate_page_from(project_dir: str | Path, slide_id: str, status: str) -> dict[str, Any]:
    if status not in PAGE_STATUS_ORDER:
        raise ValueError(status)
    state_path = Path(project_dir) / "direct_blueprint_state.json"
    state = _read_json(state_path)
    page = next((entry for entry in state.get("pages", []) if entry.get("slide_id") == slide_id), None)
    if page is None:
        raise KeyError(slide_id)
    keep = {"slide_id", "blueprint_path", "blueprint_sha256", "composition_sha256"}
    if PAGE_STATUS_ORDER.index(status) <= PAGE_STATUS_ORDER.index("blueprint_saved"):
        keep = {"slide_id"}
        page["status"] = PENDING_PAGE_STATUS
    else:
        previous = PAGE_STATUS_ORDER[PAGE_STATUS_ORDER.index(status) - 1]
        page["status"] = previous
    for key in list(page):
        if key not in keep and key != "status":
            page.pop(key, None)
    _write_json_atomic(state_path, state)
    return page


def refresh_final_render_evidence(project_dir: str | Path) -> dict[str, Any]:
    project_dir = Path(project_dir)
    state_path = project_dir / "direct_blueprint_state.json"
    state = _read_json(state_path)
    pages = state.get("pages", [])
    if not pages or any(page.get("status") != FINAL_PAGE_STATUS for page in pages):
        raise ValueError("all pages must already be accepted before final render evidence is refreshed")
    generator = project_dir / "generate_deck.py"
    if not generator.is_file():
        raise FileNotFoundError(generator)
    source = generator.read_text(encoding="utf-8")
    generator_hash = sha256_file(generator)
    shared_hash = shared_source_hash(source)
    builder_hashes = builder_source_hashes(source)
    try:
        asset_crops = _asset_crop_records(ast.parse(source))
    except SyntaxError as exc:
        raise ValueError(f"generator syntax is invalid: {exc}") from exc
    if not isinstance(asset_crops, dict):
        raise ValueError("ASSET_CROPS must be a literal dictionary before final evidence refresh")
    fidelity_module = _load_fidelity_module()
    pending_updates: list[tuple[dict[str, Any], dict[str, Any]]] = []
    for page in pages:
        slide_id = page["slide_id"]
        asset_errors = _slide_asset_evidence_errors(project_dir, slide_id, page, asset_crops)
        if asset_errors:
            raise ValueError("final extracted-asset evidence is invalid:\n- " + "\n- ".join(asset_errors))
        blueprint = project_dir / page["blueprint_path"]
        render_relative = f".build/rendered/current/{slide_id}.png"
        render = project_dir / render_relative
        if not blueprint.is_file() or not render.is_file():
            raise FileNotFoundError(f"{slide_id}: final blueprint or render is missing")
        result = fidelity_module.compare_slide(blueprint, render)
        if not result.get("passed"):
            raise ValueError(f"{slide_id}: final fidelity score {result['score']} did not pass")
        builder_hash = builder_hashes.get(slide_id)
        if not builder_hash:
            raise ValueError(f"{slide_id}: page-specific builder is missing")
        render_hash = sha256_file(render)
        pending_updates.append(
            (
                page,
                {
                    "builder_name": f"build_slide_{slide_id}",
                    "builder_sha256": builder_hash,
                    "generator_sha256": generator_hash,
                    "shared_sha256": shared_hash,
                    "render_path": render_relative,
                    "render_sha256": render_hash,
                    "comparison": {
                        "blueprint_sha256": sha256_file(blueprint),
                        "render_sha256": render_hash,
                        "score": result["score"],
                        "threshold": result["threshold"],
                        "passed": True,
                    },
                },
            )
        )
    for page, updates in pending_updates:
        page.update(updates)
    _write_json_atomic(state_path, state)
    return state


def assert_direct_project(project_dir: str | Path, *, require_accepted: bool = True) -> None:
    errors = validate_direct_project(project_dir, require_accepted=require_accepted)
    if errors:
        raise ValueError("Direct Blueprint project validation failed:\n- " + "\n- ".join(errors))


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate or initialize a V5.5 single-generator fast or Direct Blueprint project.")
    parser.add_argument("project", type=Path)
    actions = parser.add_mutually_exclusive_group()
    actions.add_argument("--init", action="store_true", help="Initialize the common project; blueprint mode also creates locked state")
    actions.add_argument("--next-batch", action="store_true", help="Print the next incomplete locked batch")
    actions.add_argument("--advance", metavar="SNN", help="Advance one page to the adjacent --status")
    actions.add_argument(
        "--refresh-final-render",
        action="store_true",
        help="Rebind accepted pages to the complete final render and recompute fidelity",
    )
    parser.add_argument(
        "--phase",
        choices=("prebuild", "final"),
        default="final",
        help="prebuild requires blueprints/builders/assets; final additionally requires every page accepted",
    )
    parser.add_argument("--status", choices=PAGE_STATUS_ORDER)
    parser.add_argument("--artifact", help="Relative blueprint_path or render_path for the matching transition")
    parser.add_argument("--batch-size", type=int, default=5)
    args = parser.parse_args()
    if args.init:
        generator = bootstrap_project(args.project, batch_size=args.batch_size)
        payload = {"generator": str(generator)}
        state = args.project / "direct_blueprint_state.json"
        if state.is_file():
            payload["state"] = str(state)
        print(json.dumps(payload, ensure_ascii=False))
        return
    if args.next_batch:
        print(json.dumps(next_incomplete_batch(args.project), ensure_ascii=False))
        return
    if args.advance:
        if not args.status:
            parser.error("--advance requires --status")
        updates: dict[str, Any] = {}
        if args.status == "blueprint_saved":
            if not args.artifact:
                parser.error("blueprint_saved requires --artifact blueprints/SNN.png")
            updates["blueprint_path"] = args.artifact
        elif args.status == "rendered":
            if not args.artifact:
                parser.error("rendered requires --artifact .build/rendered/current/slide-N.png")
            updates["render_path"] = args.artifact
        print(json.dumps(advance_page_status(args.project, args.advance, args.status, **updates), ensure_ascii=False, indent=2))
        return
    if args.refresh_final_render:
        print(json.dumps(refresh_final_render_evidence(args.project), ensure_ascii=False, indent=2))
        return
    errors = validate_direct_project(args.project, require_accepted=args.phase == "final")
    payload = {"ok": not errors, "errors": errors}
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    raise SystemExit(0 if not errors else 2)


if __name__ == "__main__":
    main()
