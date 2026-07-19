# Manifest-compiled reconstruction prompt V5.9.1

Before compilation, consume the reviewed `reconstruction_contract`. Every
evidence-bearing page element has a stable `element_id` and `module_id`.
`reconstruction_contract.module_bindings` maps every visible blueprint module
to its complete executable element set. Do not open either local builder until
the reconstruction precheck has no blockers.

`page_specs` are platform-neutral and must not contain COM objects,
`python-pptx` objects, or backend-specific callable values. After the immutable
formal blueprint/design draft and alignment gates pass, Windows compiles through
`windows_com_v584`; macOS compiles through `mac_python_pptx_v1`. Both consume
the same selected wording, evidence, geometry, design-draft hashes, and crop
declarations. The macOS path constructs locally with `python-pptx`; PowerPoint
for Mac or LibreOffice may render but must not construct the deck.

Treat the V5.8.4-aligned `.build/slides.json` and `.build/page_specs.json` as the runtime source of final display text and layout. The immutable ImageGen result remains the formal blueprint benchmark and crop source; the rendered PPT is structurally compared with it.

## Compiled project

Create one root `generate_deck.py` through `project_compiler.py`. It embeds `DECK_META`, ordered `SLIDES`, `DESIGN_DRAFTS`, `ASSET_CROPS`, literal `PAGE_SPECS`, one thin `build_slide_SNN` wrapper per page, `PAGE_BUILDERS`, and one `build_deck()` using the shared runtime. Do not create per-page generators or hand-edit the compiled generator. Other project helper Python files do not block delivery.

## Reconstruction

1. Enumerate visible modules and give every module a stable `module_id`.
2. Give every executable element a stable `element_id`, `module_id`, supported type, and positive body-relative box.
3. Preserve chart series, legends, data labels, row annotations, panel count, and column arrangement in literal page elements.
4. Inventory every independent non-native subject before choosing Python implementation.
5. Resolve each subject as `crop`, `native`, or `omit`; never use a generic native visual label.
6. Validate module bindings, visual bindings, backend support, and geometry through `v591_reconstruction_contract.py`.
7. Build once using the selected local backend and keep analytical content editable.
8. Extract one bounded PNG per crop subject and insert it once with contain fit.
9. Render and record visual deviations as warnings. Do not rebuild only to improve fidelity.
10. Bind the authoring, alignment, page-spec, manifest, generator, and PPTX evidence through delivery.

Compatibility vocabulary: process crop subjects 逐对象 with
`extract_direct_assets.py`, then place each accepted crop through the shared
runtime `add_blueprint_asset` helper using its literal `target_box_in`.

## Quality boundary

Canonical text must be present in the final PPT XML. Blueprint text differences are diagnostic because the blueprint is a visual benchmark while Python owns canonical text and final formatting.

Run `project_pipeline.py <project> --run`; package when `.build/quality_report.json` has `blocker_count: 0`. Skeleton, asset, fidelity, palette, density, and routing deviations may produce `pass_with_warnings`.
