---
name: standard-report-ppt
description: Use when Codex needs to create, revise, reconstruct, or automate a company fixed-template consulting PowerPoint deck from documents, notes, data, an existing PPTX, or visual references.
---

# Standard Report PPT V5.7

Create editable company-template research decks. V5.7 adds a reference-style analytical canvas, bounded supporting accents, and a single post-build delivery sequence that reuses current audit results instead of repeating them during packaging.

## Intake gates

### Gate 0 — final page count

Require a positive exact total or an explicit page map. The number is the final delivered slide count. Cover and contents pages are created only when explicitly requested and count toward the total.

If the request has no exact count:

1. Ask only: `这份材料最终需要做几页？`
2. Do not inspect the source, call ImageGen, create project files, or generate an artifact.
3. Stop and wait.

“适量”, “简要”, “几页左右”, “若干页”, and “as needed” are not exact counts.

### Gate 1 — production mode

Recognize an explicit user choice:

- `blueprint`: ImageGen, 蓝图还原, 高保真蓝图, or choice `1` after the menu.
- `fast`: 快速生成, 跳过蓝图, 无 ImageGen, or choice `2` after the menu.

If the mode is absent, show exactly these choices and wait for the user's explicit choice:

1. `ImageGen 蓝图还原（默认推荐）`
2. `快速生成`

“默认推荐” is a recommendation, not permission to begin. If ImageGen is unavailable, ask whether to switch to fast mode or stop. Never downgrade silently.

## Two-gate execution contract

After the user has explicitly confirmed the final page count and production mode, begin production immediately. These are the only routine user confirmations in this skill.

- Do not ask for design, layout, specification, plan, or implementation approval after both gates pass.
- Do not invoke generic brainstorming, design-spec approval, writing-plan, branch-finishing, or worktree workflows for normal deck production. This skill owns the complete production workflow.
- Do not create or request a Git branch or worktree unless the user explicitly asks for repository integration.
- Resolve page conclusions, evidence selection, layout, and visual treatment from the supplied sources and this skill's visual contract. Report material assumptions in the final handoff instead of pausing production.
- Pause only for a missing gate, an inaccessible required source, unavailable ImageGen in blueprint mode, two catastrophic ImageGen failures on the same page, or a genuine external blocker that prevents safe completion.

After both gates pass, write `project_brief.json`, initialize the project workspace, and start parsing the source and producing the deck. Do not insert a standalone preflight stage or announce that production is waiting for a toolchain precheck.

## Project brief

After both gates pass, create `project_brief.json`:

```json
{
  "schema_version": "5.7",
  "requested_page_count": 3,
  "page_mapping": [],
  "production_mode": "blueprint",
  "blueprint_engine": "direct",
  "confirmation_source": "user_selected"
}
```

Use `user_explicit` when the request stated the mode; otherwise use `user_selected`. Geometry/audit compatibility is used only when explicitly requested.

Immediately run `project_pipeline.py <project> --init` after writing the brief, then start source parsing and content production. Both modes create the same manifest workspace. Do not create `direct_blueprint_state.json` for V5.7 projects and do not manually advance or rebind page status. The final `generate_deck.py` is a deterministic compiler output; never hand-edit or construct it through shell redirection, PowerShell here-strings, or inline terminal scripts.

## Required resources

- `prompts/page_outline_prompt.md`
- `prompts/imagegen_blueprint_prompt.md`
- `prompts/python_reconstruction_prompt.md`
- `references/company_visual_system.md`
- `references/layout_and_chart_rules.md`
- `references/slide_spec_schema.md`
- `references/python_reconstruction_rules.md`
- `references/ppt_quality_check_rules.md`
- `scripts/direct_project.py` (V5.5 compatibility only)
- `scripts/project_pipeline.py`
- `scripts/project_compiler.py`
- `scripts/fast_page_specs.py`
- `scripts/v56_contracts.py`
- `scripts/v56_page_cache.py`
- `scripts/ppt_text_audit.py`
- `scripts/compose_blueprint.py`
- `scripts/extract_direct_assets.py`
- `scripts/ppt_skeleton_audit.py`
- `scripts/ppt_asset_audit.py`
- `scripts/blueprint_fidelity.py`
- `scripts/render_slides.py`
- `scripts/pack_delivery.py`
- `assets/direct_blueprint_generator_template.py`
- `assets/company_template.pptx`

Read the visual system and layout rules completely before generating a blueprint or writing PowerPoint code.

## Canonical content stage shared by both modes

1. Parse all supplied sources only after both gates pass.
   - For DOCX, parse paragraphs, tables, relationships, and embedded media structurally first.
   - Use Word COM or PDF rendering only when page-level layout, floating objects, or unsupported visual evidence is required.
   - If Word COM hangs or times out once, terminate that attempt and switch immediately to structural parsing; never repeat the same blocking export.
2. Build exactly the confirmed number of slide specs.
3. Preserve figures, dates, units, qualifiers, and citations.
4. Give each slide one conclusion and `core_points` containing **one or two** square-bullet judgments totaling **80–160** non-whitespace characters.
5. Before module design, create `evidence_inventory` from the source evidence assigned to the page. Each item records `evidence_id`, exact `statement`, `priority: must_keep | supporting | optional`, and the destination `module_id` or `null`.
6. Map every `must_keep` item and at least 80% of all `must_keep + supporting` items to real modules. Set `primary_visual_module_id` to the module that proves the conclusion. This is an evidence-coverage gate, not a fixed module, card, picture, fact-count, or occupied-area quota.
7. Use **medium, evidence-rich density**. Prefer fewer meaningful analytical regions over many tiny numbered cards. Do not automatically number modules. Number only a genuine sequence, stage, rank, or ordered method.
8. Save canonical content as UTF-8 `.build/slides.json`; save literal page geometry as `.build/page_specs.json`. `project_compiler.py` embeds both into the final single `generate_deck.py`.

## Blueprint mode — Direct Blueprint

Execute this path without omission or substitution:

1. Parse source into canonical slide content and a visual brief.
2. Generate one complete-slide visual draft per final page. It must visibly include the approximate chapter title, page title, core judgment, body, source, and page number. Run `compose_blueprint.py` to replace the top skeleton and footer deterministically. Only the composed full page is the accepted blueprint and receives a SHA-256; never show the raw ImageGen draft as the blueprint.
3. The composed blueprint must use one left anchor for chapter text, page-title text, and the first core bullet. It must contain no decorative rule above the chapter title and no separator above the footer.
4. Record each accepted page as literal, page-specific elements and coordinates in `.build/page_specs.json`. The compiler emits one thin `build_slide_SNN` wrapper per page; a shared runtime renders the literal geometry but never selects or cycles layouts.
5. Before ImageGen, build an **analytical canvas**: two or three aligned evidence regions using editable charts, tables, matrices, flows, metric strips, and concise cards. Keep charts, tables, matrices, and flows as the primary evidence-bearing body. Use small pictograms, supplied logos, flags, or bounded schematic accents as supporting accents rather than large hero images. When present, their combined footprint is **6-12% of the body area** and each sits in a **reserved icon lane** beside a module heading, regional label, or metric block. The icon lane never overlays body copy, chart labels, or card borders. A standard analytical page does not require a photo, map, logo, device, or product image. Use one semantic accent for a genuine concept, not one decorative image per card. Use a large photo, map, device, or product only when that visual is primary evidence, such as product anatomy or geographic strategy. Never fabricate an official logo. After composition, write `.build/visual_manifest.json` bound to each blueprint SHA-256. Photos, logos, maps, pictograms, compound marks, decorative motifs, chemical structures, devices, products, and characters always use `disposition: crop`, including small accents. Native rebuild is limited to text, rectangles, lines, arrows, ovals, charts, tables, and primitives with an allowlisted `rebuild_recipe`.
6. Record `candidate_count`. A page with `candidate_count > 0` cannot pass with zero crops. The compiler derives `visual_review`, `visual_inventory`, `complex_visuals`, `BLUEPRINTS`, and `ASSET_CROPS`; agents do not self-author those duplicate structures.
7. One independent object equals one `asset_id`, one crop, one PNG, and one literal `add_blueprint_asset` call. Follow the artificial-feed case pattern: define explicit per-object rectangles, batch-extract once, trim each background independently, verify each crop or the labeled montage, and insert independently with contain fit. Never crop neighboring icons, labels, rules, or a card border together.
8. Run `extract_direct_assets.py` before building. It must reject missing/undeclared crops, multi-object crops, title/rule contamination, crops outside the composed body, non-contain placement, and inventory/declaration mismatch; inspect the montage and confirm reviewed crop count = declared count = extracted count.
9. Render each page, compare it with its blueprint, and fix the builder until hierarchy, area, order, alignment, and every declared visual are faithful.
10. Run `project_pipeline.py <project> --run`. It compiles, extracts, builds, renders, and audits in dependency order with stage timing. A changed page invalidates only its own cached outputs; template or runtime changes invalidate all pages.
11. Run text, skeleton, asset, and blueprint-fidelity audits. Package only when all four gates pass and crop counts agree.

Direct Blueprint does not create or require `blueprint_geometry.json`. It must not call `fast_geometry.py`, use `runtime_archetype`, cycle a small set of layouts, or select geometry with modulo arithmetic. A blueprint file that is never consumed by its page builder is a failed run.

### Long-deck stability

For more than five pages:

- Keep one project and manifest set. Use consecutive render batches of three to five pages.
- Complete blueprint → builder → crops → render → comparison → acceptance for one batch before the next.
- Resume from `.build/pipeline_state.json`; cache records are derived from each page's content, geometry, blueprint, visual manifest, assets, template, and runtime hashes.
- Never manually reset or rebind state. A text-only or geometry-only correction re-runs only the changed page.
- Stop before packaging if any page is incomplete; never insert a convenient fixed layout.
- ImageGen failure retries only the affected page once for generation failure, unreadable output, multi-page output, missing required content, or unusable body composition. After that, ask the user whether to switch modes or stop.

## One compiled Python for the whole presentation

Every final project has exactly one root Python file: `generate_deck.py`, compiled from UTF-8 manifests. It contains `DECK_META`, ordered `SLIDES`, `BLUEPRINTS`, `ASSET_CROPS`, literal `PAGE_SPECS`, one `build_slide_SNN` wrapper per page, `PAGE_BUILDERS`, and `build_deck()`.

Do not create per-page Python files or write visible page labels inside runtime helpers. Shared components render the literal page elements; all user-visible text comes from `.build/slides.json` or `.build/page_specs.json`. Open PowerPoint once, build every page in order, save one PPTX, and close the application once.

## Incremental working loop

During construction, rebuild and render only cache misses. Reuse blueprints and extracted crops when their hashes are unchanged. A text-only layout correction must not trigger ImageGen or asset extraction again. Record every stage, including ImageGen start/end, in `.build/pipeline_timing.json`; no silent stage may exceed 120 seconds.

After Python production, use one terminal sequence: `project_pipeline.py --run` builds, renders, and writes all required audits; immediately inspect `.build/rendered/current`; then call `pack_delivery.py` once. V5.7 packaging reuses the current audit files, validates the package, and writes `delivery_record.json` without repeating skeleton or asset audits. Any change after visual inspection invalidates the audit set and requires one new `--run` before packaging.

## Fast mode

Fast mode skips ImageGen and may select deterministic body grids. It starts through `project_pipeline.py --init`, writes UTF-8 content/page manifests, and uses the same compiled COM runtime, skeleton, components, effects cleanup, evidence contract, editability, rendering, text audit, and QA. Reject `?{3,}`, `�`, C1 controls, and common mojibake before PowerPoint opens and again by scanning final PPTX XML.

## Adaptive fixed skeleton

Every page uses five layers:

1. Chapter title: 20 pt, Microsoft YaHei, navy or black.
2. Page title: 16 pt, Microsoft YaHei, white on navy, left-aligned.
3. Core judgment: 12 pt, one or two `■` points in a white box with a black 1 pt short-dash border.
4. Body: 8–12 pt charts, tables, cards, flows, comparisons, or maps.
5. Source and page number: 7–8 pt, with no separator line above the source.

Chapter text, page-title text, and the core bullet symbols share one left edge. Core paragraphs are left-aligned; the final paragraph has no paragraph-after space. The core box must measure its real wrapped text, resize to fit it without a blank row, and move the body origin down by the same amount. In PowerPoint COM, prefer `TextFrame2.TextRange.BoundHeight`; use the deterministic estimate in `direct_project.core_skeleton_metrics` only as a fallback.

The exact vertical top positions are chapter `0.4 cm`, page title `1.5 cm`, and core judgment `2.7 cm` in both modes.

The bottom of the page-title bar and the top of the core box must have at least `0.06 in` (`0.1524 cm`) clear space. Overlap or near-touching fails the skeleton audit.

There is no line, rule, band, or decorative stroke above the chapter title. Use the clean company master directly and do not add a white masking shape over it. Narrative bullets may use justified text and a 0.64 cm hanging indent; tables, labels, chart annotations, and narrow cards remain left-aligned.

Use `assets/company_template.pptx` as the only master authority. Do not create palette swatches, RGB reference cards, theme-color blocks, or any other pasteboard objects. Before and after page building, remove every shape wholly outside the slide canvas from slides, slide masters, and custom layouts.

Call `clear_shape_effects` for every generated object and `clear_presentation_effects` before the final save. Shadow, reflection, glow, soft edge, and 3D are forbidden on slides, masters, and custom layouts; theme-inherited effects count as forbidden.

## Validate, build, render, and package

```powershell
python scripts/project_pipeline.py <project> --init
python scripts/project_pipeline.py <project> --compile
python scripts/project_pipeline.py <project> --run --output <project>/output/report.pptx
python scripts/pack_delivery.py --project <project> --pptx <project>/output/report.pptx --generator <project>/generate_deck.py --output "$HOME/Desktop/<name>.zip"
```

Packaging is the default terminal gate. If the user explicitly requests loose PPTX files on the desktop, that request overrides the container format; copy only audit-passing final PPTX files and do not add unrequested ZIPs.

Do not advance page states. `project_pipeline.py` derives cache hits from real input and output hashes, updates `.build/pipeline_timing.json`, and writes the final audit records automatically.

`scripts/blueprint_fidelity.py` compares low-frequency body structure, region distribution, and visual ink mass. `ppt_asset_audit.py` separately proves every declared illustration was inserted, and `ppt_text_audit.py` proves the final XML contains no encoding-loss placeholders. A single failed page or audit blocks packaging.

Blueprint mode forbids:

- `fast_geometry.py`, `runtime_archetype`, or a deterministic layout selector;
- cycling a small layout list across pages;
- declaring a page accepted before its own rendered comparison passes;
- placing raw rendered folders or intermediate PPTX files on the desktop.

By default the desktop receives one ZIP. Its outer entries are:

- the final `.pptx`;
- `blueprints.zip` containing accepted page blueprints and any bounded crop sources;
- `py.zip` containing only `generate_deck.py`.

## Non-negotiable visual contract

- Microsoft YaHei throughout.
- Fixed 20/16/12 pt top hierarchy; body 8–12 pt; source 7–8 pt.
- Blue and gray dominate; dark red is limited to key numbers and very small data marks.
- No large red card, red section fill, red background region, or red header system.
- No blue “核心判断” label inside the core box.
- No separator rule above the source.
- No decorative line or long blue rule above the chapter title.
- Chapter title, page-title text, and first core bullet share one left anchor within 0.02 inches.
- Chapter, page title, and core judgment tops are 0.4 cm, 1.5 cm, and 2.7 cm within 0.02 inches.
- Page-title bottom and core-judgment top have at least 0.06 inches of clear space.
- No palette/RGB reference swatches or other off-slide objects on slides, masters, or custom layouts.
- Keep text, numbers, labels, sources, tables, and chart components editable; only complex non-native visuals may be bounded crops.
- Every accepted blueprint is a complete page with visible chapter, title, core judgment, body, source, and page number.
- Every independent raster subject is declared, extracted, and inserted separately with aspect-preserving contain fit; declared/extracted/inserted counts must match.
- The body is an analytical canvas. Optional supporting accents occupy 6-12% of the body area and stay inside a reserved icon lane; charts, tables, matrices, flows, metric strips, and concise cards remain dominant.
- Every source-assigned `must_keep` item and at least 80% of `must_keep + supporting` evidence are mapped to real modules.
- No shadow, reflection, glow, soft edge, or 3D effect survives on a slide, master, or custom layout.
- References contribute structure, text density, and chart placement only.
- Avoid poster/dashboard/magazine styling and gradient, 3D, glow, or heavy shadow.
