from __future__ import annotations

from typing import Any


SUPPORTED_ELEMENT_TYPES = {
    "windows_com_v584": {
        "asset",
        "section_header",
        "text",
        "rect",
        "oval",
        "line",
        "arrow",
        "text_card",
        "metric_strip",
        "hbar_chart",
        "column_chart",
        "line_chart",
        "combo_chart",
        "donut_chart",
        "grouped_hbar_chart",
        "flow",
        "matrix",
    },
    "mac_python_pptx_v1": {
        "asset",
        "section_header",
        "text",
        "rect",
        "oval",
        "line",
        "arrow",
        "text_card",
        "metric_strip",
        "hbar_chart",
        "column_chart",
        "line_chart",
        "combo_chart",
        "donut_chart",
        "grouped_hbar_chart",
        "flow",
        "matrix",
    },
    "mac_python_pptx_v2": {
        "asset",
        "section_header",
        "text",
        "rect",
        "oval",
        "line",
        "arrow",
        "text_card",
        "metric_strip",
        "hbar_chart",
        "column_chart",
        "line_chart",
        "combo_chart",
        "donut_chart",
        "grouped_hbar_chart",
        "flow",
        "matrix",
    },
}

CHART_TYPES = {
    "hbar_chart",
    "column_chart",
    "line_chart",
    "combo_chart",
    "donut_chart",
    "grouped_hbar_chart",
}

ALLOWED_NATIVE_RECIPES = {
    "line_arrow",
    "basic_shape",
    "editable_chart",
    "editable_table",
    "editable_text",
}

ALLOWED_NATIVE_KINDS = {
    "arrow",
    "icon",
    "line",
    "logo",
    "rect",
    "oval",
    "node",
    "pictogram",
    "chart",
    "table",
    "text",
}

ALLOWED_OMIT_REASONS = {
    "non_evidence_decoration",
    "duplicate_subject",
    "unreliable_crop",
}

SEMANTIC_VISUAL_KINDS = {
    "map",
    "network_map",
    "world_flow_map",
    "timeline",
    "process",
    "diagram",
    "node_network",
}

V595_PAGE_GRAPHICS_GRADES = {"G0", "G1", "G2", "G3"}
V595_RETENTION_GRADES = {"A", "B", "C"}
V596_TILE_IDS = {"Q1", "Q2", "Q3", "Q4"}
V596_MANDATORY_CROP_KINDS = {
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
V596_NATIVE_KINDS = {
    "arrow",
    "line",
    "rect",
    "oval",
    "node",
    "chart",
    "table",
    "text",
}
V595_PRESENCE_FLAGS = {
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
V595_ZERO_SUBJECT_REASONS = {
    "text_chart_table_basic_geometry_only",
}

def _issue(code: str, severity: str, message: str, slide_id: str = "") -> dict:
    return {
        "code": code,
        "severity": severity,
        "stage": "reconstruction_precheck",
        "slide_id": slide_id,
        "message": message,
        "metrics": {},
    }


def _valid_box(value: Any) -> bool:
    return (
        isinstance(value, list)
        and len(value) == 4
        and all(isinstance(item, (int, float)) for item in value)
        and value[0] >= 0
        and value[1] >= 0
        and value[2] > 0
        and value[3] > 0
        and value[0] + value[2] <= 12.25
        and value[1] + value[3] <= 4.65
    )


def _valid_source_px(value: Any) -> bool:
    return (
        isinstance(value, list)
        and len(value) == 4
        and all(isinstance(item, int) for item in value)
        and value[0] >= 0
        and value[1] >= 0
        and value[0] < value[2]
        and value[1] < value[3]
    )


def validate_visual_page(slide_id: str, page: dict[str, Any]) -> dict[str, Any]:
    blockers: list[dict] = []
    warnings: list[dict] = []
    revision = str(page.get("pipeline_revision", ""))
    is_v595 = revision in {"5.9.5", "5.9.6"}
    is_v596 = revision == "5.9.6"
    if page.get("visual_reviewed") is not True:
        blockers.append(
            _issue(
                "VISUAL_CENSUS_UNREVIEWED",
                "blocker",
                "visual census must be reviewed",
                slide_id,
            )
        )
    visuals = page.get("visuals")
    if not isinstance(visuals, list):
        visuals = []
        blockers.append(
            _issue(
                "VISUAL_CENSUS_REQUIRED",
                "blocker",
                "visuals must be a complete reviewed list",
                slide_id,
            )
        )
    observed = page.get("observed_candidate_count")
    candidates = page.get("candidate_count")
    if observed != len(visuals) or candidates != len(visuals):
        blockers.append(
            _issue(
                "VISUAL_CENSUS_COUNT_MISMATCH",
                "blocker",
                "candidate counts must equal the reviewed visuals list",
                slide_id,
            )
        )
    if (
        not visuals
        and page.get("visual_census_result") != "no_independent_subjects"
    ):
        blockers.append(
            _issue(
                "VISUAL_ZERO_CENSUS_UNPROVEN",
                "blocker",
                "zero subjects require visual_census_result=no_independent_subjects",
                slide_id,
            )
        )
    if is_v595:
        page_grade = page.get("page_graphics_grade")
        review = page.get("visual_review")
        if page_grade not in V595_PAGE_GRAPHICS_GRADES:
            blockers.append(
                _issue(
                    "VISUAL_PAGE_GRADE_REQUIRED",
                    "blocker",
                    f"V{revision} requires page_graphics_grade G0, G1, G2, or G3",
                    slide_id,
                )
            )
        if is_v596:
            review_tiles = page.get("visual_review_tiles")
            expected_hash = page.get("design_draft_sha256")
            if not isinstance(review_tiles, dict):
                blockers.append(
                    _issue(
                        "VISUAL_REVIEW_TILES_REQUIRED",
                        "blocker",
                        "V5.9.6 requires a hash-bound full-page and quadrant review",
                        slide_id,
                    )
                )
                review_tiles = {}
            reviewed_tile_ids = review_tiles.get("reviewed_tile_ids")
            tile_subjects = review_tiles.get("tile_subjects")
            if (
                review_tiles.get("full_page_reviewed") is not True
                or review_tiles.get("blueprint_sha256") != expected_hash
                or not isinstance(review_tiles.get("tile_manifest_sha256"), str)
                or len(str(review_tiles.get("tile_manifest_sha256", ""))) != 64
                or not isinstance(reviewed_tile_ids, list)
                or set(reviewed_tile_ids) != V596_TILE_IDS
            ):
                blockers.append(
                    _issue(
                        "VISUAL_REVIEW_TILES_INCOMPLETE",
                        "blocker",
                        "V5.9.6 requires full-page review and Q1-Q4 bound to the locked blueprint",
                        slide_id,
                    )
                )
            indexed_ids: set[str] = set()
            valid_tile_subjects = (
                isinstance(tile_subjects, dict)
                and set(tile_subjects) == V596_TILE_IDS
            )
            if valid_tile_subjects:
                for values in tile_subjects.values():
                    if not isinstance(values, list) or not all(
                        isinstance(value, str) and value for value in values
                    ):
                        valid_tile_subjects = False
                        break
                    indexed_ids.update(values)
            visual_ids = {
                str(item.get("visual_id"))
                for item in visuals
                if isinstance(item, dict) and item.get("visual_id")
            }
            if not valid_tile_subjects or indexed_ids != visual_ids:
                blockers.append(
                    _issue(
                        "VISUAL_TILE_SUBJECT_MISMATCH",
                        "blocker",
                        "quadrant subject index must equal the reviewed visual inventory",
                        slide_id,
                    )
                )
        if page_grade == "G0":
            if review != "reviewed_no_raster":
                blockers.append(
                    _issue(
                        "VISUAL_REVIEW_STATE_INVALID",
                        "blocker",
                        "G0 pages require visual_review=reviewed_no_raster",
                        slide_id,
                    )
                )
            if visuals:
                blockers.append(
                    _issue(
                        "VISUAL_G0_INVENTORY_CONTRADICTION",
                        "blocker",
                        "G0 pages cannot contain independent visual subjects",
                        slide_id,
                    )
                )
            challenge = page.get("zero_subject_challenge")
            if not isinstance(challenge, dict):
                blockers.append(
                    _issue(
                        "VISUAL_ZERO_CHALLENGE_REQUIRED",
                        "blocker",
                        "G0 pages require a hash-bound zero-subject challenge",
                        slide_id,
                    )
                )
            else:
                flags = challenge.get("presence_flags")
                expected_hash = page.get("design_draft_sha256")
                valid_flags = (
                    isinstance(flags, dict)
                    and set(flags) == V595_PRESENCE_FLAGS
                    and all(isinstance(value, bool) for value in flags.values())
                )
                if (
                    challenge.get("review_result") != "reviewed_no_raster"
                    or challenge.get("zero_subject_reason")
                    not in V595_ZERO_SUBJECT_REASONS
                    or not isinstance(expected_hash, str)
                    or challenge.get("blueprint_sha256") != expected_hash
                    or not valid_flags
                ):
                    blockers.append(
                        _issue(
                            "VISUAL_ZERO_CHALLENGE_REQUIRED",
                            "blocker",
                            "zero-subject challenge is incomplete or not bound to the locked blueprint",
                            slide_id,
                        )
                    )
                elif any(flags.values()):
                    blockers.append(
                        _issue(
                            "VISUAL_ZERO_CHALLENGE_CONTRADICTED",
                            "blocker",
                            "G0 is invalid because the review found an independent graphical subject",
                            slide_id,
                        )
                    )
        elif page_grade in {"G1", "G2", "G3"}:
            if review != "reviewed_inventory":
                blockers.append(
                    _issue(
                        "VISUAL_REVIEW_STATE_INVALID",
                        "blocker",
                        "G1-G3 pages require visual_review=reviewed_inventory",
                        slide_id,
                    )
                )
            if not visuals:
                blockers.append(
                    _issue(
                        "VISUAL_GRADE_REQUIRES_SUBJECTS",
                        "blocker",
                        f"{page_grade} pages require at least one reviewed visual subject",
                        slide_id,
                    )
                )
    seen: set[str] = set()
    seen_asset_ids: set[str] = set()
    crop_count = 0
    mandatory_crop_count = 0
    review_tiles = page.get("visual_review_tiles", {})
    tile_subjects = (
        review_tiles.get("tile_subjects", {})
        if isinstance(review_tiles, dict)
        else {}
    )
    for index, visual in enumerate(visuals):
        if not isinstance(visual, dict):
            blockers.append(
                _issue(
                    "VISUAL_SUBJECT_INVALID",
                    "blocker",
                    f"visual[{index}] must be a mapping",
                    slide_id,
                )
            )
            continue
        visual_id = visual.get("visual_id")
        if not isinstance(visual_id, str) or not visual_id or visual_id in seen:
            blockers.append(
                _issue(
                    "VISUAL_ID_INVALID",
                    "blocker",
                    f"visual[{index}] requires a unique visual_id",
                    slide_id,
                )
            )
        else:
            seen.add(visual_id)
        if not isinstance(visual.get("description"), str) or not visual.get(
            "description"
        ):
            blockers.append(
                _issue(
                    "VISUAL_DESCRIPTION_REQUIRED",
                    "blocker",
                    f"{visual_id or index} requires a description",
                    slide_id,
                )
            )
        treatment = visual.get("treatment")
        kind = visual.get("kind")
        retention_grade = visual.get("retention_grade")
        if is_v595 and retention_grade not in V595_RETENTION_GRADES:
            blockers.append(
                _issue(
                    "VISUAL_RETENTION_GRADE_REQUIRED",
                    "blocker",
                    f"{visual_id or index} requires retention_grade A, B, or C",
                    slide_id,
                )
            )
        if is_v596:
            if not _valid_source_px(visual.get("source_px")):
                blockers.append(
                    _issue(
                        "VISUAL_SOURCE_LOCATION_REQUIRED",
                        "blocker",
                        f"{visual_id or index} requires a valid source_px location",
                        slide_id,
                    )
                )
            if not _valid_box(visual.get("target_box_in")):
                blockers.append(
                    _issue(
                        "VISUAL_TARGET_LOCATION_REQUIRED",
                        "blocker",
                        f"{visual_id or index} requires a valid target_box_in",
                        slide_id,
                    )
                )
            memberships = visual.get("review_tile_ids")
            expected_memberships = {
                tile_id
                for tile_id, subject_ids in tile_subjects.items()
                if isinstance(subject_ids, list) and visual_id in subject_ids
            }
            if (
                not isinstance(memberships, list)
                or not memberships
                or not set(memberships).issubset(V596_TILE_IDS)
                or set(memberships) != expected_memberships
            ):
                blockers.append(
                    _issue(
                        "VISUAL_TILE_MEMBERSHIP_REQUIRED",
                        "blocker",
                        f"{visual_id or index} requires exact quadrant membership",
                        slide_id,
                    )
                )
            if kind in V596_MANDATORY_CROP_KINDS:
                mandatory_crop_count += 1
                if treatment != "crop":
                    blockers.append(
                        _issue(
                            "VISUAL_MANDATORY_CROP_REQUIRED",
                            "blocker",
                            f"{visual_id or index} kind {kind!r} must use treatment=crop",
                            slide_id,
                        )
                    )
        if treatment == "crop":
            crop_count += 1
            asset_id = visual.get("asset_id")
            if (
                not isinstance(asset_id, str)
                or not asset_id
                or not _valid_source_px(visual.get("source_px"))
                or not _valid_box(visual.get("target_box_in"))
            ):
                blockers.append(
                    _issue(
                        "VISUAL_CROP_GEOMETRY_REQUIRED",
                        "blocker",
                        f"{visual_id or index} requires asset_id, source_px, and target_box_in",
                        slide_id,
                    )
                )
            elif asset_id in seen_asset_ids:
                blockers.append(
                    _issue(
                        "VISUAL_ASSET_ID_INVALID",
                        "blocker",
                        f"{visual_id or index} requires a unique crop asset_id",
                        slide_id,
                    )
                )
            else:
                seen_asset_ids.add(asset_id)
        elif treatment == "native":
            allowed_native_kinds = (
                V596_NATIVE_KINDS if is_v596 else ALLOWED_NATIVE_KINDS
            )
            if visual.get("kind") not in allowed_native_kinds:
                blockers.append(
                    _issue(
                        "VISUAL_KIND_UNSUPPORTED",
                        "blocker",
                        f"{visual_id or index} uses unsupported native kind {visual.get('kind')!r}",
                        slide_id,
                    )
                )
            if visual.get("rebuild_recipe") not in ALLOWED_NATIVE_RECIPES:
                blockers.append(
                    _issue(
                        "VISUAL_NATIVE_RECIPE_UNSUPPORTED",
                        "blocker",
                        f"{visual_id or index} requires a supported native recipe",
                        slide_id,
                    )
                )
            if not isinstance(visual.get("element_id"), str) or not visual.get(
                "element_id"
            ):
                blockers.append(
                    _issue(
                        "VISUAL_NATIVE_ELEMENT_REQUIRED",
                        "blocker",
                        f"{visual_id or index} requires an element_id",
                        slide_id,
                    )
                )
        elif treatment == "omit":
            if visual.get("omit_reason") not in ALLOWED_OMIT_REASONS:
                blockers.append(
                    _issue(
                        "VISUAL_OMIT_REASON_REQUIRED",
                        "blocker",
                        f"{visual_id or index} requires an allowed omit_reason",
                        slide_id,
                    )
                )
            if is_v595 and retention_grade == "A":
                blockers.append(
                    _issue(
                        "VISUAL_GRADE_A_OMITTED",
                        "blocker",
                        f"{visual_id or index} is grade A and cannot be omitted",
                        slide_id,
                    )
                )
            elif is_v595 and retention_grade == "B":
                warnings.append(
                    _issue(
                        "VISUAL_GRADE_B_OMITTED",
                        "warning",
                        f"{visual_id or index} is grade B and was omitted",
                        slide_id,
                    )
                )
        else:
            blockers.append(
                _issue(
                    "VISUAL_TREATMENT_REQUIRED",
                    "blocker",
                    f"{visual_id or index} requires crop, native, or omit",
                    slide_id,
                )
            )
    if (
        is_v596
        and page.get("page_graphics_grade") in {"G1", "G2", "G3"}
        and mandatory_crop_count > 0
        and crop_count == 0
    ):
        blockers.append(
            _issue(
                "VISUAL_REQUIRED_CROP_ZERO",
                "blocker",
                "G1-G3 page contains mandatory crop subjects but crop_count is zero",
                slide_id,
            )
        )
    return {
        "schema_version": "5.9",
        "skill_version": str(page.get("pipeline_revision", "5.9.1")),
        "status": "blocked" if blockers else "pass",
        "ok": not blockers,
        "warnings": warnings,
        "blockers": blockers,
        "warning_count": len(warnings),
        "blocker_count": len(blockers),
    }


def validate_reconstruction_contract(
    brief: dict[str, Any],
    slides: list[dict[str, Any]],
    page_specs: dict[str, Any],
    alignment: dict[str, Any],
    backend: str,
) -> dict[str, Any]:
    blockers: list[dict] = []
    warnings: list[dict] = []
    alignment_pages = alignment.get("pages", {})
    v6_strict_deconstruct = (
        brief.get("schema_version") == "6.0"
        and brief.get("pipeline_revision") == "6.0.0"
        and brief.get("construction_mode") == "deconstruct"
        and backend in {"windows_com_v584", "mac_python_pptx_v2"}
    )
    supported_types = SUPPORTED_ELEMENT_TYPES.get(backend)
    if supported_types is None:
        blockers.append(
            _issue(
                "RECONSTRUCTION_BACKEND_UNSUPPORTED",
                "blocker",
                f"unsupported local backend {backend!r}",
            )
        )
        supported_types = set()

    for slide in slides:
        slide_id = str(slide.get("slide_id", ""))
        page = alignment_pages.get(slide_id, {})
        contract = page.get("reconstruction_contract")
        if not isinstance(contract, dict):
            blockers.append(
                _issue(
                    "RECONSTRUCTION_CONTRACT_REQUIRED",
                    "blocker",
                    "V5.9.1 alignment requires reconstruction_contract",
                    slide_id,
                )
            )
            continue
        allowed_backends = contract.get("supported_backends")
        if (
            not isinstance(allowed_backends, list)
            or backend not in allowed_backends
        ):
            blockers.append(
                _issue(
                    "RECONSTRUCTION_BACKEND_UNSUPPORTED",
                    "blocker",
                    f"alignment does not support backend {backend}",
                    slide_id,
                )
            )

        spec = page_specs.get(slide_id, {})
        elements = spec.get("elements", []) if isinstance(spec, dict) else []
        element_by_id: dict[str, dict] = {}
        for index, element in enumerate(elements):
            if not isinstance(element, dict):
                blockers.append(
                    _issue(
                        "RECONSTRUCTION_ELEMENT_INVALID",
                        "blocker",
                        f"element[{index}] must be a mapping",
                        slide_id,
                    )
                )
                continue
            element_id = element.get("element_id")
            if not isinstance(element_id, str) or not element_id:
                blockers.append(
                    _issue(
                        "RECONSTRUCTION_ELEMENT_ID_REQUIRED",
                        "blocker",
                        f"element[{index}] requires element_id",
                        slide_id,
                    )
                )
            elif element_id in element_by_id:
                blockers.append(
                    _issue(
                        "RECONSTRUCTION_ELEMENT_ID_DUPLICATE",
                        "blocker",
                        f"duplicate element_id {element_id}",
                        slide_id,
                    )
                )
            else:
                element_by_id[element_id] = element
            if element.get("type") not in supported_types:
                blockers.append(
                    _issue(
                        "RECONSTRUCTION_ELEMENT_UNSUPPORTED",
                        "blocker",
                        f"unsupported element type {element.get('type')!r} for {backend}",
                        slide_id,
                    )
                )
            if not _valid_box(element.get("box")):
                blockers.append(
                    _issue(
                        "RECONSTRUCTION_BOX_INVALID",
                        "blocker",
                        f"element[{index}] requires a positive in-body box",
                        slide_id,
                    )
                )
            if element.get("type") in CHART_TYPES and not isinstance(
                element.get("data"), list
            ):
                blockers.append(
                    _issue(
                        "RECONSTRUCTION_CHART_DATA_REQUIRED",
                        "blocker",
                        f"{element_id or index} requires chart data",
                        slide_id,
                    )
                )

        bindings = contract.get("module_bindings")
        if not isinstance(bindings, list):
            bindings = []
            blockers.append(
                _issue(
                    "RECONSTRUCTION_MODULE_BINDINGS_REQUIRED",
                    "blocker",
                    "reconstruction_contract.module_bindings must be a list",
                    slide_id,
                )
            )
        bound: dict[str, list[str]] = {}
        for binding in bindings:
            if not isinstance(binding, dict):
                continue
            module_id = binding.get("module_id")
            ids = binding.get("element_ids")
            if isinstance(module_id, str) and isinstance(ids, list):
                bound[module_id] = [str(item) for item in ids]
                for element_id in bound[module_id]:
                    if element_id not in element_by_id:
                        blockers.append(
                            _issue(
                                "RECONSTRUCTION_MODULE_UNBOUND",
                                "blocker",
                                f"module {module_id} references missing element {element_id}",
                                slide_id,
                            )
                        )
        module_ids = {
            str(item.get("module_id"))
            for item in page.get("structure_modules", [])
            if isinstance(item, dict) and item.get("module_id")
        }
        for module_id in sorted(module_ids):
            valid_bound_ids = [
                element_id
                for element_id in bound.get(module_id, [])
                if element_id in element_by_id
            ]
            if not valid_bound_ids:
                blockers.append(
                    _issue(
                        "RECONSTRUCTION_MODULE_UNBOUND",
                        "blocker",
                        f"visible module {module_id} has no executable element",
                        slide_id,
                    )
                )

        visuals = page.get("visuals", [])
        effective_visual_revision = (
            "5.9.6"
            if v6_strict_deconstruct
            else brief.get("pipeline_revision")
        )
        is_v595 = effective_visual_revision in {"5.9.5", "5.9.6"}
        census = validate_visual_page(slide_id, {
            "pipeline_revision": effective_visual_revision,
            "visual_reviewed": page.get("reviewed"),
            "visual_review": page.get("visual_review"),
            "visual_census_result": page.get("visual_census_result"),
            "page_graphics_grade": page.get("page_graphics_grade"),
            "design_draft_sha256": page.get("design_draft_sha256"),
            "zero_subject_challenge": page.get("zero_subject_challenge"),
            "visual_review_tiles": page.get("visual_review_tiles"),
            "observed_candidate_count": (
                page.get("observed_candidate_count")
                if is_v595
                else len(visuals)
            ),
            "candidate_count": (
                page.get("candidate_count")
                if is_v595
                else len(visuals)
            ),
            "visuals": visuals,
        })
        blockers.extend(census["blockers"])
        warnings.extend(census["warnings"])
        expected_subjects = contract.get("visual_subject_count")
        if expected_subjects != len(visuals):
            blockers.append(
                _issue(
                    "RECONSTRUCTION_VISUAL_CENSUS_MISMATCH",
                    "blocker",
                    "visual_subject_count must equal the reviewed visuals list",
                    slide_id,
                )
            )
        asset_elements = {
            str(item.get("asset_id")): item
            for item in elements
            if isinstance(item, dict)
            and item.get("type") == "asset"
            and item.get("asset_id")
        }
        for visual in visuals:
            if not isinstance(visual, dict):
                continue
            if visual.get("treatment") == "crop":
                asset_id = str(visual.get("asset_id", ""))
                if not asset_id or asset_id not in asset_elements:
                    blockers.append(
                        _issue(
                            "RECONSTRUCTION_CROP_ELEMENT_MISSING",
                            "blocker",
                            f"crop {asset_id or '<missing>'} has no page asset element",
                            slide_id,
                        )
                    )
            elif (
                visual.get("treatment") == "omit"
                and visual.get("kind") in SEMANTIC_VISUAL_KINDS
                and brief.get("schema_version") == "5.9"
        and brief.get("pipeline_revision") in {"5.9.2", "5.9.4", "5.9.5", "5.9.6"}
            ):
                warnings.append(
                    _issue(
                        "SEMANTIC_VISUAL_OMITTED",
                        "warning",
                        f"semantic visual {visual.get('visual_id', '')} was omitted",
                        slide_id,
                    )
                )
            elif visual.get("treatment") == "native":
                element_id = str(visual.get("element_id", ""))
                if not element_id or element_id not in element_by_id:
                    blockers.append(
                        _issue(
                            "RECONSTRUCTION_NATIVE_ELEMENT_MISSING",
                            "blocker",
                            f"native visual {visual.get('visual_id', '')} has no page element",
                            slide_id,
                        )
                    )

    status = "blocked" if blockers else ("pass_with_warnings" if warnings else "pass")
    return {
        "schema_version": "5.9",
        "skill_version": str(brief.get("pipeline_revision", "5.9.1")),
        "status": status,
        "ok": not blockers,
        "warnings": warnings,
        "blockers": blockers,
        "warning_count": len(warnings),
        "blocker_count": len(blockers),
    }
