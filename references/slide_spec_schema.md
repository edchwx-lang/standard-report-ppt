# V6.0 compiled project contract

New V6 projects declare schema `6.0`, pipeline revision `6.0.0`, production mode
`blueprint`, and an explicit `construction_mode` of `deconstruct` or `bitmap`.
V6 `fast` is invalid. Deconstruction consumes `.build/page_specs.json`; bitmap
consumes `.build/bitmap_page_specs.json`, whose sole page element is
`type: body_asset`, `fit: contain`, `target: runtime_body_box`,
`outline: none`.

V6 `core_points` remain canonical content and may contain a legacy leading
bullet. Both runtime builders remove consecutive leading bullet glyphs and
render exactly one editable `■` per core paragraph. Standalone `--compile`
materializes the current post-lock contracts before compiler dispatch; it
never calls ImageGen, builds a PPTX, renders, or packages.

All V6 runtime elements have stable `element_id`; generated shapes are named
`EL_<element_id>_<n>`. Mac normalizes them into `.build/mac_page_specs.json`
without reinterpreting content. Runtime and delivery metadata record both
`construction_mode` and `builder_backend`.

## V5.9.2 compatibility

New projects declare:

```json
{
  "schema_version": "5.9",
  "pipeline_revision": "5.9.2",
  "platform_target": "auto",
  "builder_backend": "derived_in_runtime_report"
}
```

The `builder_backend` is not a user choice. It is recorded in
`.build/runtime_report.json` as `windows_com_v584` or
`mac_python_pptx_v1`. Page specifications remain platform-neutral.

All JSON and Python files use UTF-8. V5.8 accepts V5.6 and V5.7 projects through compatibility branches but applies the following fields only to new V5.8 projects.

## Brief and cached source

```json
{
  "schema_version": "5.8",
  "pipeline_revision": "5.8.4",
  "requested_page_count": 3,
  "production_mode": "blueprint",
  "blueprint_engine": "direct",
  "confirmation_source": "user_explicit",
  "source_files": ["C:/absolute/path/to/source.docx"]
}
```

It may also contain the non-blocking visual direction shared by ImageGen and Python:

```json
{
  "visual_brief": {
    "primary_expression": "annotated_structure",
    "visual_story": "Show the device core and annotate the three performance constraints",
    "supporting_visuals": ["device cutaway", "thermal cue"]
  }
}
```

`.build/source_extract.json` is the lossless structural parse of exact UTF-8 `source_files` paths. Embedded DOCX media is extracted under `.build/source_media/` and referenced by relative path. `.build/source_digest.json` records paths, sizes, hashes, `parsed_once: true`, and the reusable payload. `.build/source_ingest_report.json` records parser choice, cache state, and duration. A matching source-set hash prevents repeat material decomposition.

## Authoring bundle

`.build/authoring_bundle.json` is the single authoring input and contains `slides`, `page_specs`, and `visual_manifest`. `project_pipeline.py --materialize` atomically derives the four runtime manifests and refreshes `.build/blueprint_text_benchmark.json`. Project-specific materialization Python files are unnecessary.

## Canonical slide

Each ordered slide contains `chapter`, `title`, `core_points`, `source`, modules, `primary_visual_module_id`, `evidence_inventory`, and:

```json
{
  "density_profile": "adaptive",
  "visual_route": {
    "data_kind": "time_series",
    "data": [
      {"label": "2022", "value": 100},
      {"label": "2023", "value": 125},
      {"label": "2024", "value": 160}
    ]
  }
}
```

Valid `data_kind` values are `time_series`, `category_comparison`, `composition`, `multi_metric_comparison`, `lookup`, `process`, `mixed`, and `qualitative`.

Qualitative routes require `qualitative_form`: `parallel`, `narrative`, or `causal`. `parallel` and `narrative` use `text_card` as primary evidence. `causal` uses `flow` and is valid only when the source establishes a real non-stage cause-effect relationship. Ordered operational stages belong under `data_kind: process`, not qualitative.

## Page specifications

`.build/page_specs.json` contains literal editable elements. Supported chart-first types include `hbar_chart`, `column_chart`, `line_chart`, `combo_chart`, `donut_chart`, and `grouped_hbar_chart`; ordered or causal evidence uses editable `flow`. Each element requires a positive `box=[x,y,w,h]`. Color values are BGR integers or six-digit HEX strings and are normalized before COM.

## Design draft manifest

Blueprint mode uses one immutable design draft per page:

```json
{
  "schema_version": "5.8",
  "pages": {
    "S01": {
      "design_draft_path": ".build/design_drafts/S01.png",
      "design_draft_sha256": "<64 lowercase hex>",
      "imagegen_attempt_count": 1,
      "transport_attempt_count": 1,
      "visual_plan": [],
      "visual_reviewed": true,
      "observed_candidate_count": 0,
      "candidate_count": 0,
      "visuals": []
    }
  }
}
```

The immutable design draft is copied byte-for-byte as the formal blueprint benchmark. Canonical manifests remain the text authority. `transport_attempt_count` may be 2 only when the first transport produced no artifact. `visual_plan`, `visual_reviewed`, `observed_candidate_count`, and `candidate_count` are optional diagnostics; count differences never block V5.8.2.

## Blueprint text benchmark

`.build/blueprint_text_benchmark.json` binds each page to the selected runtime slide/page-spec hash and design-draft hash. V5.8.4 records `canonical`, blueprint `observed`, PPT `selected`, and `resolution: blueprint | fact_guard | uncertain_fallback`. Differences remain warnings.

## Post-blueprint alignment

V5.8.4 blueprint projects add `.build/blueprint_alignment.json` after the original ImageGen page is locked:

```json
{
  "schema_version": "5.8",
  "skill_version": "5.8.4",
  "pages": {
    "S01": {
      "design_draft_sha256": "<locked draft hash>",
      "authoring_bundle_sha256": "<base bundle hash>",
      "reviewed": true,
      "review_method": "visual_agent",
      "display_text_policy": "blueprint_first_fact_guard",
      "slide_text": {
        "chapter": "章节",
        "title": "蓝图展示标题",
        "core_points": ["蓝图展示判断"],
        "source": "资料来源：..."
      },
      "text_decisions": [],
      "resolved_page_spec": {"elements": []},
      "structure_modules": [],
      "visuals": []
    }
  }
}
```

The original blueprint remains byte-identical. Runtime manifests follow its display text and structure, except recorded factual corrections for numbers, dates, units, names, and sources.

Each visual uses `treatment: crop | native | omit`. Through V5.9.5, only `crop`
requires `source_px` and `target_box_in`; count differences and omissions follow the
revision's existing policy. V5.9.6 requires every visual to record `source_px`,
`target_box_in`, and `review_tile_ids`, plus a hash-bound Q1-Q4 `visual_review_tiles`
record. In V5.9.6, icon, pictogram, logo, map, photo, illustration, device, person,
product, and flag subjects must use `crop`.

V5.9.1 additionally requires:

```json
{
  "reconstruction_contract": {
    "module_bindings": [
      {"module_id": "career_window", "element_ids": ["S03_E01", "S03_E02"]}
    ],
    "visual_subject_count": 1,
    "supported_backends": ["windows_com_v584", "mac_python_pptx_v1"]
  }
}
```

Every executable element has a stable `element_id`; evidence-bearing elements
also have `module_id`. A true zero-subject page records
`visual_census_result: "no_independent_subjects"`.

`grouped_hbar_chart` may use `layout: "paired_columns"`, `series`, `show_legend`, `show_data_labels`, `data_label_format`, and `row_annotations` to preserve aligned bar columns from the blueprint.

## Formal blueprint manifest

Copy each original ImageGen draft to `blueprints/SNN.png` and write `.build/formal_blueprint_manifest.json` with `design_draft_sha256`, `formal_blueprint_sha256`, `render_sha256`, and `pptx_sha256`. Design-draft and formal-blueprint hashes must match exactly; render hash remains separate.

## Generator

`project_compiler.py` produces the only root `generate_deck.py`, embedding `DECK_META`, `SLIDES`, `DESIGN_DRAFTS`, `ASSET_CROPS`, `PAGE_SPECS`, page wrappers, `PAGE_BUILDERS`, and `build_deck()`.

## Unified quality report

`.build/quality_report.json` uses `pass`, `pass_with_warnings`, or `blocked`. Every issue includes `code`, `severity`, `stage`, `slide_id`, `message`, and `metrics`. `.build/pipeline_result.json` mirrors `quality_status`, `warning_count`, and `blocker_count`; `ok=true` whenever blocker count is zero.

`.build/layout_precheck.json` contains non-blocking pre-COM overlap and text-capacity diagnostics. `.build/pipeline_timing.json` preserves front-stage and build-stage records, including `blueprint_alignment`, with a stable `run_id`, cache and attempt metadata, and wall-clock/active totals.
