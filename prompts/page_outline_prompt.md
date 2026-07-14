# Canonical slide content prompt V5.6

Convert the supplied sources into ordered UTF-8 `.build/slides.json`. The compiler later embeds this content in the single delivery generator. Do not write visible labels directly into Python source.

## Inputs

- confirmed `project_brief.json`;
- user requirements and page mapping;
- extracted source material;
- `references/slide_spec_schema.md`;
- `references/layout_and_chart_rules.md`.

## Page-count rule

Return exactly the confirmed final page count. Do not add a cover or contents page unless the user requested it and counted it.

## Required fields per slide

- stable `slide_id` in final order;
- `chapter` and conclusion-led `title`;
- `core_points` with **one or two** audience-facing judgments totaling **80–160** non-whitespace characters;
- `source`;
- `page_type` and `layout_intent`;
- `density_profile: medium`;
- ordered semantic modules containing every final label, number, table value, process step, chart series, and map annotation.
- `primary_visual_module_id` pointing to the module that proves the page conclusion;
- `evidence_inventory` containing every source evidence item assigned to this page: unique `evidence_id`, exact `statement`, `priority: must_keep | supporting | optional`, and destination `module_id` or `null`;
- blueprint mode: required `visual_review` set to `extract_declared` or `reviewed_no_raster` after full-page inspection;
- blueprint mode: required `visual_inventory`, SHA-bound `visual_review_evidence`, and reviewed `complex_visuals` list.

## Content rules

- Derive claims only from supplied sources or label an assumption explicitly.
- Use the core judgment to state the conclusion, mechanism, and implication; avoid slogans and repeated wording.
- Do not include the visible `■` character in canonical points. The generator owns bullet rendering.
- Preserve exact figures, dates, units, qualifiers, and citations.
- Inventory evidence before grouping it into modules. Map every `must_keep` item and at least **80%** of all `must_keep + supporting` items to real module IDs. Optional evidence may be omitted when it would reduce clarity.
- The 80% rule measures source-evidence coverage, not the number of cards, modules, pictures, facts, or occupied pixels.
- Use the number of analytical regions that the conclusion needs. A full-width matrix may be one module; a chart plus interpretation may be two; a genuine three-path strategy may be three.
- Do not invent modules to satisfy a quota. Do not split every sentence into a card.
- Internal `slide_id`, `module_id`, and group IDs are implementation metadata and must never appear on the slide.
- Do not automatically number parallel evidence, cards, or modules. Visible numbering is permitted only for a real sequence, stage, rank, ordered path, or method; encode this as `ordered: true` or an explicit `display_order`.
- Keep medium density comparable to a conventional consulting page: a clear primary visual, readable supporting evidence, and intentional whitespace. Prefer visual evidence over avoidable prose when the source supports it, but do not set a fixed image or module count.
- If a reference page is information-rich, match its evidence capacity by preserving comparison dimensions, causal links, benchmark figures, and implications. Do not imitate its card count mechanically.

## Page composition intent

Choose the body family from content, not from page index:

- market size/trend → chart plus interpretation;
- comparable objects → symmetric two-column;
- ordered stages → timeline or process;
- market calculation → assumption-to-result chain;
- causal explanation → driver split;
- many objects and dimensions → matrix;
- spatial strategy → map with editable annotations;
- recommendations → checklist or problem/chance/solution.

The ImageGen blueprint decides final body geometry in blueprint mode. `layout_intent` is semantic guidance, not permission to use a fixed layout.
