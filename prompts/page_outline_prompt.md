# Canonical slide content prompt V5.8.3

Use the lossless `.build/source_extract.json` produced from exact `project_brief.json.source_files` paths. Do not reopen or retype the DOCX when its source digest matches. Convert the evidence into exactly the confirmed number of UTF-8 slide records inside `.build/authoring_bundle.json`; the shared materializer derives the runtime manifests.

## Required fields

- ordered `slide_id`, `chapter`, conclusion-led `title`, and `source`;
- preferably one or two `core_points` totaling roughly 80-160 non-whitespace characters; deviations are warnings;
- semantic `modules` containing every final visible label, number, chart series, process step, and table value;
- `primary_visual_module_id`;
- `evidence_inventory` with exact statement, `must_keep | supporting | optional`, and destination module;
- `visual_route.data_kind`: `time_series | category_comparison | composition | multi_metric_comparison | lookup | process | mixed | qualitative`;
- qualitative routes also require `visual_route.qualitative_form`: `parallel | narrative | causal`;
- `density_profile: adaptive` is recommended for V5.8;
- a non-blocking `visual_brief` with `primary_expression`, `visual_story`, and `supporting_visuals`;
- blueprint mode visual inventory fields after the single design draft is inspected.

Aim to map every `must_keep` item and at least 80% of `must_keep + supporting` evidence to real modules. Preserve figures, dates, units, qualifiers, and citations. Coverage shortfalls are warnings. Internal IDs are never visible.

## Visual-first, chart-first routing

- Three or more ordered periods: `time_series`.
- Three or more comparable categories with the same unit: `category_comparison`.
- Shares that form a whole: `composition`.
- Comparable objects across multiple numeric metrics: `multi_metric_comparison`.
- Exact lookup across many dimensions: `lookup`.
- Ordered operational stages: `process`.
- Technical structure, material composition, or equipment principle: annotated structure diagram or subject illustration.
- Industry chain or upstream/downstream relation: chain with visual nodes.
- Object differences: image-text comparison.
- Mixed numeric and narrative evidence: `mixed`.
- Pure prose, judgments, or point-like evidence: `qualitative`; do not force a chart. Use `parallel` for independent peer points, `narrative` for prose, and `causal` only for a real non-stage cause-effect relationship.

For one numeric series across ordered periods, default to a line chart for continuity and a column chart for a few discrete snapshots. Use a combo chart only when a second comparable series or metric is present. Never invent a growth-rate series; label any derived calculation explicitly.

Matrices, cards, and flow boxes are not layout defaults. Use matrices for exact lookup, and flows only for real sequences or causality. Python ease must not influence the primary expression.

## Adaptive density

Target roughly 70% of the approved dense reference without copying its structure. Chartable pages normally occupy 60-96% of the body; qualitative pages 48-90%. Preserve evidence capacity and whitespace balance, not a fixed number of charts, cards, rows, or modules.

The design draft guides visual direction in blueprint mode. Final text and literal geometry live only in `slides.json` and `page_specs.json`.
