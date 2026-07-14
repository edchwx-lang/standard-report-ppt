# PPT quality gates V5.6

A deck is complete only when every applicable gate passes.

## Gate 0 — intake and manifests

- Final page count and production mode are explicit.
- `project_brief.json` uses schema 5.6.
- `slides.json` and `page_specs.json` have exact page coverage.
- Blueprint mode also has `visual_manifest.json` and one composed blueprint per page.
- No V5.6 project depends on manual `direct_blueprint_state.json` progression.

## Gate 1 — content and encoding

- Required text, figures, dates, units, qualifiers, and sources are preserved.
- Core judgment has one or two points totaling 80–160 non-whitespace characters.
- Every `must_keep` and at least 80% of `must_keep + supporting` evidence maps to modules.
- Source manifests and compiled Python pass the UTF-8 text audit.
- No `???`, U+FFFD, C1 control, or recognized mojibake sequence exists.

## Gate 2 — blueprint visuals

Blueprint mode only:

- Every page has a real accepted composed blueprint and matching SHA-256.
- Chapter, title, core judgment, body, source, and page number are visible in the blueprint.
- Each non-native subject is recorded as `crop`; native rebuild is allowlisted.
- `candidate_count > 0` requires at least one crop.
- Each independent subject has exactly one crop record, extracted PNG, and insertion.
- Crops contain no neighboring subject, text, rule, or card border.
- Declared, extracted, reviewed, and inserted counts agree.

## Gate 3 — compiled generator

- The project has one deterministic `generate_deck.py` compiled from manifests.
- It has one thin `build_slide_SNN` wrapper per page and exact `PAGE_BUILDERS` coverage.
- User-visible strings come from manifests, not runtime helper literals.
- Blueprint source contains no fast geometry, runtime archetype, layout cycle, or modulo selector.

## Gate 4 — skeleton and appearance

- PPTX page count equals the brief.
- Chapter/title/core use 20/16/12 pt Microsoft YaHei and share a left edge.
- Their top positions are 0.4 cm, 1.5 cm, and 2.7 cm within 0.02 inches.
- Title and core have at least 0.06 inches of clear space.
- No line appears above the chapter or above the footer.
- No off-slide palette/RGB reference blocks exist.
- Core box is white with a black 1 pt short-dash border; body starts below its measured height.
- No shadow, reflection, glow, soft edge, or 3D survives anywhere.

## Gate 5 — rendering and fidelity

- Rendering produces the exact expected page set.
- Blueprint pages are compared to their own blueprints in the body ROI.
- Every page passes structure, region distribution, and ink-mass thresholds.
- A failed page blocks delivery; deck average cannot hide it.

## Gate 6 — automatic audits

- Run `ppt_text_audit.py` for both modes.
- Run `ppt_skeleton_audit.py` for both modes.
- Run `ppt_asset_audit.py` and `blueprint_fidelity.py` in blueprint mode.
- All audit JSON files report `ok: true` and matching page/crop counts.

## Delivery

Default delivery is one desktop ZIP containing the final PPTX, `blueprints.zip`, and `py.zip`. If the user explicitly requests loose PPTX files on the desktop, that request overrides packaging format; audits still must pass before copying the PPTX.
