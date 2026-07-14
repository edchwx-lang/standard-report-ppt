from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any


LEFT_CHART_ARCHETYPES = {
    "industry_overview_trend",
    "chart_with_commentary",
    "driver_split",
    "financial_operations",
    "left_chart_right_text",
    "left_chart_right_driver_stack",
}
DUAL_COLUMN_ARCHETYPES = {"dual_column_comparison", "left_right_comparison"}
THREE_COLUMN_ARCHETYPES = {
    "three_path_cards",
    "problem_chance_solution",
    "three_columns",
}
PROCESS_ARCHETYPES = {
    "stage_evolution",
    "market_sizing",
    "value_chain",
    "process_matrix",
    "top_process_bottom_asymmetric_cards",
}
MATRIX_ARCHETYPES = {"comparison_matrix", "technology_matrix", "full_width_matrix"}
MAP_ARCHETYPES = {"map_region", "regional_layout"}
CHECKLIST_ARCHETYPES = {"checklist_conclusion", "horizontal_checklist"}


def _stack(count: int, *, x0: float, x1: float, gap: float = 0.05) -> list[list[float]]:
    if count <= 0:
        return []
    height = (1.0 - gap * (count - 1)) / count
    return [
        [x0, index * (height + gap), x1, index * (height + gap) + height]
        for index in range(count)
    ]


def _columns(count: int, *, y0: float = 0.0, y1: float = 1.0, gap: float = 0.04) -> list[list[float]]:
    if count <= 0:
        return []
    width = (1.0 - gap * (count - 1)) / count
    return [
        [index * (width + gap), y0, index * (width + gap) + width, y1]
        for index in range(count)
    ]


def _grid(count: int) -> list[list[float]]:
    if count <= 1:
        return [[0.0, 0.0, 1.0, 1.0]][:count]
    if count == 2:
        return _columns(2)
    if count == 3:
        return _columns(3)
    first = _columns(2, y0=0.0, y1=0.46, gap=0.05)
    second = _columns(2, y0=0.54, y1=1.0, gap=0.05)
    return (first + second)[:count]


def _zones(archetype: str, modules: list[dict[str, Any]]) -> list[list[float]]:
    count = len(modules)
    if not count:
        return []
    if count == 1:
        return [[0.0, 0.0, 1.0, 1.0]]
    if archetype == "four_quadrants":
        return _grid(count)
    if archetype in LEFT_CHART_ARCHETYPES:
        return [[0.0, 0.0, 0.58, 1.0]] + _stack(count - 1, x0=0.62, x1=1.0)
    if archetype in DUAL_COLUMN_ARCHETYPES:
        return _columns(count)
    if archetype in THREE_COLUMN_ARCHETYPES:
        return _columns(count)
    if archetype in PROCESS_ARCHETYPES:
        if count == 1:
            return [[0.0, 0.0, 1.0, 1.0]]
        return [[0.0, 0.0, 1.0, 0.28]] + _columns(count - 1, y0=0.36, y1=1.0)
    if archetype in MATRIX_ARCHETYPES:
        if count == 1:
            return [[0.0, 0.0, 1.0, 1.0]]
        return [[0.0, 0.0, 0.74, 1.0]] + _stack(count - 1, x0=0.78, x1=1.0)
    if archetype in MAP_ARCHETYPES:
        return [[0.0, 0.0, 0.62, 1.0]] + _stack(count - 1, x0=0.66, x1=1.0)
    if archetype in CHECKLIST_ARCHETYPES:
        return _stack(count, x0=0.0, x1=1.0, gap=0.035)
    return _grid(count)


def _infer_archetype(slide: dict[str, Any]) -> str:
    explicit = str(slide.get("layout_archetype", "")).strip()
    if explicit:
        return explicit
    roles = [str(module.get("role", "")) for module in slide.get("modules", [])]
    if any(role in {"bar_chart", "line_chart", "combo_chart", "stacked_chart", "scatter_chart", "bubble_chart"} for role in roles):
        return "chart_with_commentary"
    if any(role == "map" for role in roles):
        return "map_region"
    if any(role in {"matrix", "table"} for role in roles):
        return "comparison_matrix"
    if any(role == "process" for role in roles):
        return "value_chain"
    if len(roles) == 2:
        return "dual_column_comparison"
    if len(roles) == 3:
        return "three_path_cards"
    return "four_quadrants"


def _style_for(module: dict[str, Any]) -> dict[str, str]:
    primitive = str(module.get("primitive") or "generic")
    fill_role = str(module.get("fill_role") or "white")
    if primitive in {"chart", "map"}:
        return {"border_role": "none", "fill_role": fill_role, "header_role": "line_title"}
    if primitive == "line_group":
        return {"border_role": "bottom_line", "fill_role": fill_role, "header_role": "line_title"}
    if primitive == "flow_arrow":
        return {"border_role": "none", "fill_role": "none", "header_role": "line_title"}
    if primitive == "table_grid":
        return {"border_role": "outline", "fill_role": fill_role, "header_role": "light_header"}
    return {"border_role": "outline", "fill_role": fill_role, "header_role": "text_only"}


def _validate_fast_brief(spec: dict[str, Any], brief: dict[str, Any]) -> None:
    if brief.get("schema_version") != "1.0":
        raise ValueError("project_brief schema_version must be 1.0")
    if brief.get("production_mode") != "fast":
        raise ValueError("fast geometry requires production_mode: fast")
    if brief.get("confirmation_source") not in {"user_explicit", "user_selected"}:
        raise ValueError("fast geometry requires explicit user mode confirmation")
    count = brief.get("requested_page_count")
    if not isinstance(count, int) or isinstance(count, bool) or count <= 0:
        raise ValueError("requested_page_count must be a positive integer")
    if count != len(spec.get("slides", [])):
        raise ValueError("requested_page_count does not match slide_specs")


def generate_fast_geometry(spec: dict[str, Any], brief: dict[str, Any]) -> dict[str, Any]:
    _validate_fast_brief(spec, brief)
    slides: list[dict[str, Any]] = []
    for slide in spec.get("slides", []):
        modules = slide.get("modules", [])
        archetype = _infer_archetype(slide)
        zones = _zones(archetype, modules)
        signature = "|".join([archetype, *[module["module_id"] for module in modules]])
        geometry_modules = []
        assets = []
        for module, zone in zip(modules, zones):
            geometry_modules.append(
                {
                    "module_id": module["module_id"],
                    "zone_norm": [round(value, 6) for value in zone],
                    "primitive": module.get("primitive", "generic"),
                    **_style_for(module),
                }
            )
            if module.get("role") == "map" or module.get("primitive") == "map":
                background_path = module.get("map", {}).get("background_path")
                if isinstance(background_path, str) and background_path.strip():
                    assets.append(
                        {
                            "asset_id": f"{module['module_id']}_MAP_BG",
                            "module_id": module["module_id"],
                            "path": background_path,
                            "zone_norm": [round(value, 6) for value in zone],
                            "layer": "background",
                            "required": True,
                        }
                    )
        slides.append(
            {
                "slide_id": slide["slide_id"],
                "blueprint_file": f"runtime_archetype/{archetype}",
                "blueprint_sha256": hashlib.sha256(signature.encode("utf-8")).hexdigest(),
                "blueprint_size_px": [1600, 900],
                "body_source_px": [0, 0, 1600, 900],
                "modules": geometry_modules,
                "assets": assets,
            }
        )
    schema_version = "4.1" if spec.get("schema_version") == "4.1" else "4.0"
    return {"schema_version": schema_version, "slides": slides}


def generate_fast_manifest(geometry: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema_version": "4.2" if geometry.get("schema_version") == "4.1" else "4.1",
        "production_mode": "fast",
        "imagegen_used": False,
        "slides": [
            {
                "slide_id": slide["slide_id"],
                "status": "runtime_archetype",
                "archetype": slide["blueprint_file"].split("/", 1)[1],
            }
            for slide in geometry.get("slides", [])
        ],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate deterministic fast-mode geometry.")
    parser.add_argument("--brief", required=True, type=Path)
    parser.add_argument("--spec", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--manifest", required=True, type=Path)
    args = parser.parse_args()
    spec = json.loads(args.spec.read_text(encoding="utf-8"))
    brief = json.loads(args.brief.read_text(encoding="utf-8"))
    geometry = generate_fast_geometry(spec, brief)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(geometry, ensure_ascii=False, indent=2), encoding="utf-8")
    args.manifest.parent.mkdir(parents=True, exist_ok=True)
    args.manifest.write_text(
        json.dumps(generate_fast_manifest(geometry), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(args.output)
    print(args.manifest)


if __name__ == "__main__":
    main()
