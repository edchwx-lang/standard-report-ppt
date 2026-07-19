# Post-blueprint alignment prompt V5.9.5

This retains the V5.8.4 post-blueprint alignment path, the V5.9.2
critical-text review, and the V5.9.4 executable crop contract. V5.9.5 adds
evidence-backed visual grading before Python reconstruction.

Run this once after every successful ImageGen page is locked. It is an internal
review step, not a new user confirmation and not a second ImageGen request.

Read the original `.build/design_drafts/SNN.png` at full resolution together
with the base canonical slide, planned page spec, evidence inventory, and
visual manifest. Write one UTF-8 `.build/blueprint_alignment.json`.

## Display text

1. Transcribe the wording visibly presented in the original blueprint.
2. Prefer that wording for the PPT, including module titles, explanatory copy,
   legends, data labels, and annotations.
3. Compare numbers, dates, units, proper nouns, and sources with canonical
   evidence. Correct factual conflicts in the selected PPT text and record
   `resolution: "fact_guard"`.
4. If a blueprint string cannot be read confidently, keep the canonical string
   and record `resolution: "uncertain_fallback"`.
5. Use `resolution: "blueprint"` when selected and observed wording match.
6. Never regenerate or repaint the blueprint because of a text difference.

Complete critical text review during this same full-page pass. Record one
explicit decision for the chapter, page title, every core point, every
`section_header.text`, and every `text_card.title` and `text_card.body`.
Missing critical text decisions block V5.9.2 before construction. Detail
differences in sources, chart labels, legends, values, and annotations remain
one aggregated warning per page.

## Structure

Record the visible module topology before considering Python convenience:

- module count and boxes;
- chart kind and panel/column arrangement;
- series names and colors;
- legend position;
- every visible data label;
- row-level annotations and callouts;
- comparison, table, flow, or narrative relationships.

Write the complete editable `resolved_page_spec`. A blueprint with two aligned
bar columns must remain two aligned columns; do not collapse it into a generic
grouped bar merely because that is easier to build.

Every executable element receives a stable `element_id` and its owning
`module_id`. Write `reconstruction_contract.module_bindings` so every visible
module lists all of its element IDs. Record both supported local backends when
all selected element types are portable.

Maps, timelines, labeled networks, and directional arrows carry meaning. Do
not replace them with generic text cards merely because Python reconstruction
is easier. Prefer a clean bounded crop when editable labels are unnecessary;
otherwise rebuild the essential nodes, arrows, and labels natively. If a
semantic visual must be omitted, keep its explanatory text editable and record
the omission so the page can continue with a warning. Preserve the number and
relationship of primary modules. Minor spacing and wording differences are
allowed.

## Visual subjects

### V5.9.6 strict visual census and crop contract

After the formal blueprint is locked, generate `.build/visual_review_tiles.json` and
inspect the full page plus Q1, Q2, Q3, and Q4. Record `visual_review_tiles` with:

- `full_page_reviewed: true`;
- the locked `blueprint_sha256`;
- the exact `tile_manifest_sha256`;
- `reviewed_tile_ids: [Q1, Q2, Q3, Q4]`;
- `tile_subjects`, keyed by Q1-Q4, listing every visual ID visible in each tile.

Every visual records a valid `source_px`, `target_box_in`, and exact
`review_tile_ids`. The union of `tile_subjects` equals the visual inventory. Scan all
four quadrants before classification; do not stop after finding the first icon lane.

Classify the inner subject, not its container. A circle containing a person, house,
globe, aircraft, crop, device, or other symbol is an `icon` or `pictogram`, not an
`oval` or `basic_shape`.

The kinds `icon`, `pictogram`, `logo`, `map`, `photo`, `illustration`, `device`,
`person`, `product`, and `flag` always use `treatment: crop`. Do not use `native` or
`omit` for these kinds. Native reconstruction is limited to lines, arrows, rectangles,
ovals, basic nodes, editable charts, editable tables, and editable text.

Each crop records a unique `asset_id`, `source_px`, and `target_box_in`, and binds to
one `type: asset` page element. If any mandatory-crop subject exists on G1-G3,
`crop_count=0` is a blocker.

First assign one page-level graphics grade:

- `G0`: text, editable charts/tables, and basic geometry only;
- `G1`: one or more supporting icons, pictograms, logos, or simple subjects;
- `G2`: one or more meaningful maps, devices, products, people, photos, or
  illustrations that materially shape the page;
- `G3`: a dominant composite illustration or several interdependent visual
  subjects whose omission would substantially change the blueprint.

For every inventoried subject assign one retention grade:

- `A`: essential to meaning or dominant blueprint identity; it cannot be
  omitted;
- `B`: materially supporting; omission is allowed only with a recorded warning;
- `C`: decorative or redundant; it may be omitted with an explicit reason.

Inventory each meaningful non-native subject and choose exactly one treatment:
the treatment vocabulary is `crop | native | omit`.

- `crop`: bounded map, pictogram, flag, device, person, product, or distinctive
  illustration that should be reused from the original blueprint;
- `native`: simple arrow, line, circle, basic node, or other truthful editable
  reconstruction;
- `omit`: low-value decoration whose removal does not damage comprehension.

For `crop`, record one `asset_id`, one `source_px`, and one `target_box_in`.
Do not crop text, charts, tables, data labels, or basic geometry. There is no
visual-count quota and no minimum crop count.

Set `visual_review: reviewed_inventory`. The census includes crop, native, and
omitted subjects; it is not a crop counter. Native subjects require a supported
kind, `rebuild_recipe`, and `element_id`. Omitted subjects require
`omit_reason`. `native_analytical_element is forbidden`. If there are genuinely
no independent subjects, set `page_graphics_grade: G0`,
`visual_review: reviewed_no_raster`, and
`visual_census_result: no_independent_subjects`. Then complete the separate
zero-subject challenge defined in `zero_crop_challenge_prompt.md`. Bind that
challenge to the locked `design_draft_sha256` and explicitly mark all ten
presence flags false. G1, G2, and G3 can never use an empty inventory.

## Flow boundary

- Do not call ImageGen.
- Do not write `.build/design_drafts/SNN.png` or `blueprints/SNN.png`.
- Do not ask the user to approve the alignment.
- Missing, unreadable, stale, or unreviewed alignment is a workflow blocker.
- Ordinary text differences, factual corrections, native substitutions, crop
  failures, omissions, and fidelity differences are warnings.
- Semantic visual omissions are warnings and do not trigger a second build.
- There is no fidelity-driven rebuild.
