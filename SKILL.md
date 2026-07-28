---
name: standard-report-ppt
description: Use when Codex needs to create, revise, reconstruct, or automate a company fixed-template consulting PowerPoint deck from documents, notes, data, an existing PPTX, or visual references.
---

# Standard Report PPT V6.0.0-rc1

V6 新项目在页数门禁后必须显式选择一种生产方式；两种方式都必须完成内容解析、逐页 ImageGen 和正式蓝图锁定。单独说“蓝图模式”不是有效选择，ImageGen 不可调用时以 `IMAGEGEN_UNAVAILABLE` 停止。

1. `解构模式（较慢）：逐页拆解蓝图并重建为可编辑 PPT；复杂非原生视觉可保留为局部位图。`
2. `位图模式（较快）：章节、标题、核心判断、来源和页码可编辑；主体蓝图裁切后作为不可编辑图片放入。`

V6 项目合同：

```json
{
  "schema_version": "6.0",
  "pipeline_revision": "6.0.0",
  "requested_page_count": 9,
  "production_mode": "blueprint",
  "construction_mode": "deconstruct",
  "blueprint_engine": "builtin_imagegen",
  "platform_target": "auto",
  "source_files": ["C:/absolute/path/to/source.docx"]
}
```

`construction_mode` 必须显式为 `deconstruct` 或 `bitmap`，不设默认值。V6 禁止 `fast`，也禁止两个生产方式互相静默降级。蓝图锁定前的内容、证据、写作、提示词、每页一次成功蓝图和一次无产物传输重试保持不变；`construction_mode` 只进入蓝图锁定后的缓存键。

- Windows 两种方式均使用 `windows_com_v584`。
- Windows 解构模式完整继承 V5.9.6/V5.8.4 的锁定后蓝图处理，并继续保留 Windows 专属的蓝图对齐审计和渲染后保真报告。
- macOS 两种方式均使用 `mac_python_pptx_v2`。
- Windows 与 macOS 解构模式共同强制执行 G0–G3 视觉普查、全页及 Q1–Q4 审查和原子级局部裁切。每个裁切必须是紧边界、无可编辑文字和原生几何的单一独立主体；流程、线条、箭头、图表、表格和基础几何必须反向绑定到 `native` 视觉普查记录；所有解构图片强制无轮廓，裁切像素包含完整深色外围框线时阻断。Mac 继续使用完整解析、原生对象重建和 `DECONSTRUCTION_EDITABILITY_FAILED` 门禁。
- 位图模式只使用逐页全图审查，`source_px` 必须位于主体外围框线内侧；裁掉固定骨架后以 maximal centered contain 放置一个 `outline: none` 的主体图片，并保留五层骨架文字可编辑。裁切结果形成完整深色外围矩形时以 `V6_BITMAP_BODY_FRAME_INCLUDED` 阻断，只允许修订 `bitmap_alignment.json`。
- V6 构建器兼容 `core_points` 中历史遗留的前导项目符号，但最终每个核心判断段落必须只显示一个 `■`；重复符号或只有符号没有正文均阻断。
- V6 `--compile` 会先确定性生成当前模式所需的正式蓝图清单、裁切合同及运行时 page specs；它不调用 ImageGen、不构建、不渲染也不打包。
- V6 的 `--materialize`、两类 review、`--compile`、`--run` 和正式交付在进入后蓝图阶段前统一执行 `V6_IMAGEGEN_INVOCATION_REQUIRED` 门禁。每页必须在追加式 `imagegen_transport_report.json.history` 中有且仅有一个成功 ImageGen 事件，并与 design draft、formal blueprint、当前运输状态及视觉清单的 SHA-256 一致。手工放置图片、只填写当前页记录或自写生成脚本均不构成 ImageGen 调用证明；门禁失败时不得写任何后续产物。`--init`、内容解析和现有 ImageGen 生产/记录逻辑保持不变。
- V6 为 RC：Windows 与 OOXML 自动测试是发布门槛；真实 PowerPoint for Mac 的生成、打开、渲染和编辑冒烟测试通过后才标记正式 V6.0.0。

CLI：

```powershell
python scripts/project_pipeline.py <project> --prepare-visual-review
python scripts/project_pipeline.py <project> --prepare-bitmap-review
python scripts/project_pipeline.py <project> --compile
python scripts/project_pipeline.py <project> --run
```

V6 post-lock resources are mandatory: `prompts/deconstruction_alignment_prompt.md`,
`prompts/bitmap_alignment_prompt.md`, `scripts/v6_contracts.py`,
`scripts/v6_blueprint_gate.py`, `scripts/v6_bitmap.py`,
`scripts/v6_deconstruction.py`, `scripts/v6_mac_spec.py`,
`scripts/v6_editability_audit.py`, `scripts/project_compiler_mac_v2.py`, and
`assets/python_pptx_generator_template_v2.py`.

# Standard Report PPT V5.9.6 compatibility

Existing V5.9.6 projects use `pipeline_revision: "5.9.6"` while V5.9.0, V5.9.1, V5.9.2,
V5.9.4, and V5.9.5 projects remain readable with their existing behavior. The Windows
COM and macOS python-pptx backends are unchanged.

V5.9 keeps the shared source, authoring, ImageGen, immutable-blueprint, alignment,
evidence, and `page_specs` stages platform-neutral. Only after those gates pass,
runtime selection derives one local backend:

- Windows: `windows_com_v584`, preserving the V5.8.4 PowerPoint COM builder.
- macOS: `mac_python_pptx_v1`, constructing the deck locally with
  `python-pptx`; no PowerPoint COM and no Windows executor.

In blueprint mode, the real first slide is the capability probe. One readable,
locked, byte-identical draft/formal blueprint is required per final slide before
either builder starts. A missing artifact may receive one transport retry only;
an existing artifact is never regenerated automatically. ImageGen availability,
network transport, and account entitlement remain external boundaries.

macOS resolves fonts in the order Microsoft YaHei, PingFang SC, then Noto Sans
CJK SC. PowerPoint for Mac is the preferred local renderer and LibreOffice is
the fallback renderer; neither creates slide objects. If neither renderer is
available, the result is `structurally_valid_unrendered`: the local PPTX and
quality report may be handed off, but the verified three-entry ZIP is forbidden.

New V5.9 projects use:

```json
{
  "schema_version": "5.9",
  "pipeline_revision": "5.9.6",
  "requested_page_count": 3,
  "production_mode": "blueprint",
  "blueprint_engine": "builtin_imagegen",
  "platform_target": "auto",
  "source_files": ["C:/absolute/path/to/source.docx"]
}
```

V5.8.4 and earlier projects retain their existing compatibility behavior.
V5.9.0 projects retain their immutable blueprints and receive advisory
fidelity/asset audit handling.
V5.9.1 projects retain the mandatory one-pass reconstruction contract described
below.

## Standard Report PPT V5.9.6 post-blueprint visual crop enforcement

All requirements and actions through immutable formal blueprint locking remain unchanged.
Do not modify source intake, authoring, `visual_brief`, `visual_plan`, ImageGen prompt
wording or freedom, generation count, transport retry, artifact recording, formal
blueprint bytes, or blueprint locking.

Immediately after the formal blueprint is locked, run:

```powershell
python scripts/project_pipeline.py <project> --prepare-visual-review
```

This creates `.build/visual_review_tiles.json` and four hash-bound quadrant tiles per
page. Review the full page and Q1-Q4 before writing `blueprint_alignment.json`. Every
visual subject records `source_px`, `target_box_in`, and exact `review_tile_ids`; the
page records the reviewed tile IDs and a `tile_subjects` index whose union equals the
visual inventory.

Treat the subject inside a container as the visual kind. A circle containing a person,
building, globe, device, or other pictogram is an `icon` or `pictogram`, not an editable
`oval`. The kinds `icon`, `pictogram`, `logo`, `map`, `photo`, `illustration`, `device`,
`person`, `product`, and `flag` always use `treatment: crop`. They cannot use `native`
or `omit`. Native reconstruction is limited to lines, arrows, rectangles, ovals, basic
nodes, editable charts, editable tables, and editable text.

Each mandatory crop has a unique `asset_id`, valid `source_px`, valid `target_box_in`,
and one bound `type: asset` page element. For G1-G3, any mandatory-crop subject with
zero crops blocks before PowerPoint opens. Declared and extracted crop IDs must match.
The final PPTX must contain each declared crop exactly once inside its target box.
Missing, duplicate, stale, or out-of-contract assets block packaging. Crop whitespace,
minor contamination, and ordinary visual differences remain warnings and never
authorize an aesthetic rebuild.

V5.9.6 post-blueprint resources are `scripts/v596_visual_review.py`,
`prompts/blueprint_alignment_prompt.md`, `scripts/v591_reconstruction_contract.py`,
`scripts/extract_direct_assets.py`, and `scripts/ppt_asset_audit.py`.

## Standard Report PPT V5.9.5 first-build release and visual census patch

Existing V5.9.5 projects continue to use `"pipeline_revision": "5.9.5"`.

All requirements and actions through immutable formal-blueprint locking remain
unchanged. Do not modify source intake, authoring, `visual_brief`,
`visual_plan`, ImageGen prompt wording or freedom, generation count, transport
retry, artifact recording, or blueprint locking.

After the blueprint is locked, the alignment review assigns every page a
graphics grade `G0 | G1 | G2 | G3` and every visual subject a retention grade
`A | B | C`. Grade A subjects cannot be omitted. Grade B omissions are warnings.
G1-G3 require a non-empty visual inventory. G0 requires a separate hash-bound
zero-subject challenge that explicitly checks icon, pictogram, logo, map,
photo, illustration, device, person, product, and flag presence. An empty array
or zero crop count never proves G0.

Python reconstruction remains the single construction pass. Postbuild checks
classify only encoding/placeholder corruption, missing critical text, failed
declared asset contracts, blank output, and gross blueprint divergence as
catastrophic. Missing sources, labels, annotations, small geometry differences,
palette, spacing, ordinary fidelity differences, and other aesthetic findings
are advisory.

When no catastrophic error exists, write `.build/postbuild_release.json`, bind
it to the exact PPTX SHA-256, lock the first build, and package it immediately.
Ordinary warnings never authorize a rebuild. A locked build is reused by later
`--run` calls without reopening PowerPoint. One `--repair-catastrophic` build is
permitted after a failed catastrophic gate; a third automatic build is
forbidden. `--user-revision` exists only for a new revision explicitly requested
by the user. `--no-package` honors an explicit loose-PPTX request.

V5.9.5 post-blueprint resources are
`prompts/zero_crop_challenge_prompt.md` and `scripts/v595_release.py`.
V5.9.6 additionally requires `scripts/v596_visual_review.py`.

## Standard Report PPT V5.9.4 packaging and post-blueprint crop patch

All V5.9.2 requirements and actions through byte-identical formal-blueprint
locking are unchanged. Do not change source intake, authoring, `visual_brief`,
`visual_plan`, ImageGen prompt wording or visual freedom, generation count,
transport retry, artifact recording, or blueprint locking for this patch.

After the formal blueprint is locked and the existing full-page alignment
review explicitly selects `treatment: crop`, that crop becomes an executable
delivery contract. It must be extracted from the locked blueprint, bound to one
page asset element, inserted exactly once, and verified against the current
PPTX. A missing or invalid explicitly reviewed crop blocks delivery after
writing its evidence report; it never triggers another ImageGen call,
extraction retry, or PowerPoint rebuild. Crop-content quality findings remain
warnings.

There is no minimum crop count. `native`, `omit`, and reviewed zero-crop pages
remain valid. No visual class is forced into `crop`, and pre-ImageGen
`visual_plan` is never used to infer a crop requirement.

Project helper Python files may remain in the working directory. The verified
delivery still contains exactly the PPTX, `blueprints.zip`, and `py.zip`, and
`py.zip` still contains only `generate_deck.py`. V5.9.4 validates the modern
design-draft/formal-blueprint hashes and binds the crop audit to the exact PPTX.

## Standard Report PPT V5.9.2 lightweight alignment patch

Keep the V5.9.1 one-pass workflow. During the existing full-page alignment
review, record one explicit decision for every critical text string: chapter,
page title, core points, section headers, and text-card titles and bodies. A
missing critical decision blocks before either local builder opens.
`blueprint`, `fact_guard`, and `uncertain_fallback` decisions all satisfy this
coverage gate.

Detail differences in sources, chart labels, legends, values, and annotations
remain warnings. Semantic visual omissions such as a map or timeline also
remain warnings when the explanatory text and visible module binding survive.
There is no fidelity-driven rebuild, no OCR stage, no extra ImageGen call, and
no page-by-page approval.

After every failed ImageGen call that returns no artifact for the known timeout
class, immediately use `v59_blueprint_gate.py --record-failure
transport_timeout` with the current `transport_attempt_count`. The first event
is resumable and the second is not. Preserve both events in append-only
transport history. Once an artifact exists, lock it and never regenerate it
automatically.

## V5.9.1 one-pass reconstruction contract

After full-page blueprint review, each alignment page contains
`reconstruction_contract.module_bindings`, stable `element_id` values, and a
complete visual census. Each visible module binds to one or more executable
page elements. Each independent non-native subject records exactly one
`crop | native | omit` treatment. `crop` requires source and target geometry;
`native` requires a supported kind, recipe, and target element; `omit` requires
an explicit reason. `native_analytical_element` is forbidden.

The existing prebuild action validates this contract before Windows COM or Mac
python-pptx opens. Missing bindings, invalid geometry, unsupported elements, or
unbound crop/native subjects block before construction. Palette, density,
native substitution, crop fallback, omission, and fidelity remain advisory.
Fidelity deviations do not trigger a rebuild. A structurally valid deck is not
rebuilt merely to improve the low-frequency similarity score.

There is no minimum crop count. Zero crops are valid only when the reviewed
census explicitly reports `no_independent_subjects`, or when every inventoried
subject has a valid native/omit treatment. Compile-time hashes bind the
authoring bundle, alignment, slides, page specs, and visual manifest through
delivery; post-compile candidate-count edits are rejected.

## Standard Report PPT V5.8.4 compatibility

Create editable company-template research decks. V5.8.4 keeps V5.8.3 source intake and ImageGen generation unchanged, locks the original ImageGen artifact as the formal blueprint, then adds one internal post-blueprint alignment stage so its visible wording, module topology, labels, and reusable visual subjects reach the Python builder. Ordinary quality differences remain `pass_with_warnings`.

## Intake gates

### Gate 0 — final page count

Require a positive exact total or an explicit page map. The number is the final delivered slide count. Cover and contents pages are created only when explicitly requested and count toward the total.

If the request has no exact count:

1. Ask only: `这份材料最终需要做几页？`
2. Do not inspect the source, call ImageGen, create project files, or generate an artifact.
3. Stop and wait.

“适量”, “简要”, “几页左右”, “若干页”, and “as needed” are not exact counts.

### Gate 1 — construction mode

V6 new projects always use `production_mode: "blueprint"` and require an explicit
`construction_mode`. Recognize only these choices:

- `解构 / 可编辑 / 1` → `deconstruct`
- `位图 / 快速位图 / 2` → `bitmap`

If the mode is absent, show exactly these choices and wait for the user's explicit choice:

1. `解构模式（较慢）：逐页拆解蓝图并重建为可编辑 PPT；复杂非原生视觉可保留为局部位图。`
2. `位图模式（较快）：章节、标题、核心判断、来源和页码可编辑；主体蓝图裁切后作为不可编辑图片放入。`

“蓝图模式”单独出现不是有效选择，因为两个模式都必须生成蓝图。V6 不设默认
`construction_mode`。ImageGen 不可调用或无权限时立即以
`IMAGEGEN_UNAVAILABLE` 停止；不得询问或切换到跳过蓝图的生产方式。

## Two-gate execution contract

After the user has explicitly confirmed the final page count and construction mode, begin production immediately. These are the only routine user confirmations in this skill.

- Do not ask for design, layout, specification, plan, or implementation approval after both gates pass.
- Do not invoke generic brainstorming, design-spec approval, writing-plan, branch-finishing, or worktree workflows for normal deck production. This skill owns the complete production workflow.
- Do not create or request a Git branch or worktree unless the user explicitly asks for repository integration.
- Resolve page conclusions, evidence selection, layout, and visual treatment from the supplied sources and this skill's visual contract. Report material assumptions in the final handoff instead of pausing production.
- Pause only for a missing gate, an inaccessible required source, unavailable ImageGen in blueprint mode after the permitted no-artifact transport retry, an unreadable/incomplete-page blueprint, or a genuine runtime/delivery blocker. Blueprint typos, visual-count differences, crop omissions, density, palette, routing, skeleton, and fidelity deviations are warnings and never require manual per-page authorization.

After both gates pass, write `project_brief.json`, initialize the project workspace, and start parsing the source and producing the deck. Do not insert a standalone preflight stage or announce that production is waiting for a toolchain precheck.

## Project brief

After both gates pass, create `project_brief.json`:

```json
{
  "schema_version": "5.8",
  "pipeline_revision": "5.8.4",
  "requested_page_count": 3,
  "page_mapping": [],
  "production_mode": "blueprint",
  "blueprint_engine": "direct",
  "confirmation_source": "user_selected",
  "source_files": ["C:/absolute/path/to/source.docx"]
}
```

Use `user_explicit` when the request stated the mode; otherwise use `user_selected`. Geometry/audit compatibility is used only when explicitly requested.

Immediately run `project_pipeline.py <project> --init` after writing the brief, then begin production immediately. Both modes create the same manifest workspace. Do not create `direct_blueprint_state.json` for V5.8 projects and do not manually advance or rebind page status. The final `generate_deck.py` is a deterministic compiler output; never hand-edit it.

For new V5.8.4 projects, `source_files` uses the unchanged V5.8.3 exact-path intake. Never reconstruct a supplied Chinese path in a shell command. `--init` resolves those literal paths, writes `.build/source_extract.json`, `.build/source_digest.json`, `.build/source_ingest_report.json`, extracts embedded DOCX media under `.build/source_media/`, and reuses them when the source hashes match.

## Required resources

- `prompts/page_outline_prompt.md`
- `prompts/imagegen_blueprint_prompt.md`
- `prompts/python_reconstruction_prompt.md`
- `prompts/blueprint_alignment_prompt.md`
- `references/cross_platform_backend_contract.md`
- `requirements-macos.lock`
- `scripts/v59_platform.py`
- `scripts/v59_blueprint_gate.py`
- `scripts/v591_contracts.py`
- `scripts/v591_reconstruction_contract.py`
- `scripts/project_compiler_mac.py`
- `scripts/mac_render_slides.py`
- `scripts/mac_quality.py`
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
- `scripts/v58_source_cache.py`
- `scripts/v58_text_benchmark.py`
- `scripts/ensure_windows_runtime.py`
- `scripts/v58_visual_policy.py`
- `scripts/v58_template_contract.py`
- `scripts/v58_prebuild.py`
- `scripts/v582_quality.py`
- `scripts/v583_source_ingest.py`
- `scripts/v583_authoring.py`
- `scripts/v583_timing.py`
- `scripts/v584_blueprint_alignment.py`
- `scripts/blueprint_alignment_audit.py`
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
- `requirements-windows.lock`

Read the visual system and layout rules completely before generating a blueprint or writing PowerPoint code.

## Canonical content stage shared by both modes

1. Parse all supplied sources only after both gates pass. V5.8.4 reuses the V5.8.3 exact-path structural intake through `project_brief.json.source_files`, hashes the source set, and reuses `.build/source_extract.json` plus `.build/source_digest.json` whenever every size and SHA-256 matches. Missing, unreadable, empty, ambiguous, or changed required sources block compilation.
   - For DOCX, parse paragraphs, tables, relationships, and embedded media structurally first.
   - Use Word COM or PDF rendering only when page-level layout, floating objects, or unsupported visual evidence is required.
   - If Word COM hangs or times out once, terminate that attempt and switch immediately to structural parsing; never repeat the same blocking export.
2. Build exactly the confirmed number of slide specs.
3. Preserve figures, dates, units, qualifiers, and citations.
4. Give each slide one conclusion. Prefer one or two concise square-bullet `core_points` totaling roughly 80-160 non-whitespace characters, but record deviations as warnings.
5. Before module design, create `evidence_inventory` from the source evidence assigned to the page. Each item records `evidence_id`, exact `statement`, `priority: must_keep | supporting | optional`, and the destination `module_id` or `null`.
6. Map every `must_keep` item and target at least 80% of all `must_keep + supporting` items to real modules. Set `primary_visual_module_id` to the module that proves the conclusion. Coverage shortfalls are advisory, not a fixed module, card, picture, fact-count, or occupied-area gate.
7. Add `visual_route.data_kind`: `time_series`, `category_comparison`, `composition`, `multi_metric_comparison`, `lookup`, `process`, `mixed`, or `qualitative`. Qualitative routes also require `qualitative_form: parallel | narrative | causal`; use `causal` only for a real cause-effect relationship. Apply chart-first routing only when comparable numeric evidence exists.
8. Aim for adaptive density near 70% of the approved dense reference: 60-96% body occupancy for chartable data and 48-90% for qualitative pages. These are advisory evidence-capacity bands, not fixed module counts or layouts.
9. Write the complete decision once to UTF-8 `.build/authoring_bundle.json`, including `slides`, `page_specs`, and the diagnostic `visual_manifest`. Run `project_pipeline.py <project> --materialize` to atomically derive `.build/slides.json`, `.build/page_specs.json`, `.build/visual_manifest.json`, and `.build/blueprint_text_benchmark.json`. These derived files are the only text and layout sources consumed by the PPT builder. Do not create a project-specific materialization Python script.

## Blueprint mode — Direct Blueprint

Execute this path without omission or substitution:

1. Parse once into canonical slide content, `visual_route`, and a non-blocking `visual_brief` containing `primary_expression`, `visual_story`, and `supporting_visuals`.
2. Choose the visual expression before considering Python convenience: first the conclusion and strongest evidence; then the best chart, annotated structure/subject illustration, visual-node chain, image-text comparison, lookup table, true process, or narrative-with-anchor form; then supporting visuals; only afterward decide how Python will rebuild it.
3. Before ImageGen, record any planned decorative/supporting visuals in `visual_plan` without a quantity cap. Request one successful ImageGen result per final slide and save it under `.build/design_drafts/SNN.png`. `transport_attempt_count` is 1 normally and may become 2 only when the first network/timeout call produced no artifact. `imagegen_attempt_count` remains 1. Once any image exists, lock it and never regenerate because of text or visual-quality differences.
4. Copy that immutable ImageGen output byte-for-byte to `blueprints/SNN.png`; it is the formal blueprint benchmark. Run `compose_blueprint.py` only to record skeleton/body ROI metadata for reconstruction and cropping, without replacing or repainting the formal blueprint.
5. Record the pre-blueprint canonical decision and planned geometry once in `.build/authoring_bundle.json`. After the design draft exists, create one reviewed `.build/blueprint_alignment.json` without regenerating the image. It records blueprint display text, factual corrections, resolved page geometry, module topology, and visual treatment.
6. Route by evidence semantics. Continuous/comparable data uses line, column, bar, combo, or donut charts; technical structure/material composition/device principles use an annotated structure or subject illustration; value-chain relations use visual nodes; object differences use image-text comparison; exact lookup uses tables/matrices; only real steps or causes use flows; prose uses narrative modules with a visual anchor. Matrix, flow, and card grids are never automatic defaults.
7. For V5.9.6, generate and inspect the hash-bound full page plus Q1-Q4 review tiles; earlier revisions inspect the full ImageGen page once. Then write `.build/blueprint_alignment.json`. Transcribe visible wording and structure; use canonical content only to correct conflicting numbers, dates, units, proper nouns, and sources. Mark each decision `blueprint`, `fact_guard`, or `uncertain_fallback`.
8. Record every meaningful non-native subject with `treatment: crop | native | omit`. V5.9.6 strictly crops every icon, pictogram, logo, map, photo, illustration, device, person, product, and flag; a surrounding circle or card does not convert the subject into basic geometry. Earlier revisions retain their existing no-minimum-crop behavior. Keep charts, text, tables, labels, and genuine basic geometry native and editable.
9. The alignment must preserve module count, chart panels/columns, series, legends, data labels, row annotations, and boxes. Python convenience must not collapse visibly separate structures. Missing, unreadable, stale, or unreviewed alignment is the only new workflow blocker; ordinary differences remain warnings.
10. Run `extract_direct_assets.py` once before building. For V5.9.6, missing, invalid, or count-mismatched mandatory crops block before the builder opens; crop-content quality remains advisory. Earlier revisions retain their existing audit policy.
11. Keep `.build/blueprint_text_benchmark.json` as diagnostic evidence with canonical, observed, selected, and resolution fields. The final PPT XML must contain the selected aligned runtime text. The original blueprint is never regenerated because of text differences.
12. Run `project_pipeline.py <project> --run`, inspect the render, and package whenever `.build/quality_report.json` has no blockers. Advisory audits may produce `pass_with_warnings`.

Direct Blueprint does not create or require `blueprint_geometry.json`. It must not call `fast_geometry.py`, use `runtime_archetype`, cycle a small set of layouts, or select geometry with modulo arithmetic. A blueprint file that is never consumed by its page builder is a failed run.

### Long-deck stability

For more than five pages:

- Keep one project and manifest set. Use consecutive render batches of three to five pages.
- Complete blueprint → builder → crops → render → comparison → acceptance for one batch before the next.
- Resume from `.build/pipeline_state.json`; cache records are derived from each page's content, geometry, blueprint, visual manifest, assets, template, and runtime hashes.
- Never manually reset or rebind state. A text-only or geometry-only correction re-runs only the changed page.
- Stop before packaging if any page is incomplete; never insert a convenient fixed layout.
- Permit one automatic transport retry only when the first call produced no image. Once an image exists, never call ImageGen again automatically; deterministic reconstruction proceeds with warnings.

## One compiled Python for the whole presentation

Every final project has one compiled root generator, `generate_deck.py`, from UTF-8 manifests. V5.8.4 applies reviewed blueprint alignment after the shared V5.8.3 authoring materializer. The generator embeds `DECK_META`, ordered `SLIDES`, `DESIGN_DRAFTS`, `ASSET_CROPS`, literal `PAGE_SPECS`, one `build_slide_SNN` wrapper per page, `PAGE_BUILDERS`, and `build_deck()`.

Do not create per-page Python files or write visible page labels inside runtime helpers. Shared components render literal aligned page elements; all user-visible text comes from V5.8.4-aligned `.build/slides.json` or `.build/page_specs.json`. Open PowerPoint once, build every page in order, save one PPTX, and close the application once.

## Incremental working loop

During construction, rebuild and render only cache misses. Reuse the source digest, immutable design drafts, alignment, and extracted crops when hashes are unchanged. A text-only or geometry-only correction never triggers ImageGen. V5.8.4 preserves one `.build/pipeline_timing.json` with the V5.8.3 stages plus `blueprint_alignment`.

Before opening PowerPoint, inspect `.build/layout_precheck.json`. It warns about likely asset/text collisions, severe text-capacity problems, and non-intentional overlaps. Correct page specs internally when necessary; it creates no user confirmation gate and does not change V5.8.2 blocker policy.

After Python production, use one terminal sequence: `project_pipeline.py --run` builds, renders, and writes all audits plus `.build/quality_report.json`; immediately inspect `.build/rendered/current`; then call `pack_delivery.py` once. V5.7 compatibility packaging retains its historical strict behavior. Any change after visual inspection requires one new `--run` before packaging.

## V5.9.x fast mode compatibility

Fast mode skips ImageGen and may select deterministic body grids. It starts through `project_pipeline.py --init`, writes UTF-8 content/page manifests, and uses the same compiled COM runtime, skeleton, components, effects cleanup, evidence contract, editability, rendering, text audit, and QA. Reject `?{3,}`, `�`, C1 controls, and common mojibake before PowerPoint opens and again by scanning final PPTX XML.

## Adaptive fixed skeleton

Every page uses five layers:

1. Chapter title: 20 pt, Microsoft YaHei, navy or black.
2. Page title: 16 pt, Microsoft YaHei, white on navy, left-aligned.
3. Core judgment: 12 pt, one or two `■` points in a white box with a black 1 pt short-dash border.
4. Body: 8-12 pt charts, tables, cards, flows, comparisons, or maps.
5. Source and page number: 7-8 pt, with no separator line above the source.

Chapter text, page-title text, and the core bullet symbols share one left edge. Core paragraphs are left-aligned; the final paragraph has no paragraph-after space. The core box must measure its real wrapped text, resize to fit it without a blank row, and move the body origin down by the same amount. In PowerPoint COM, prefer `TextFrame2.TextRange.BoundHeight`; use the deterministic estimate in `direct_project.core_skeleton_metrics` only as a fallback.

The exact vertical top positions are chapter `0.4 cm`, page title `1.5 cm`, and core judgment `2.7 cm` in both modes.

The bottom of the page-title bar and the top of the core box must have at least `0.06 in` (`0.1524 cm`) clear space. Overlap or near-touching fails the skeleton audit.

There is no line, rule, band, or decorative stroke above the chapter title. Use the clean company master directly and do not add a white masking shape over it. Narrative bullets may use justified text and a 0.64 cm hanging indent; tables, labels, chart annotations, and narrow cards remain left-aligned.

Use `assets/company_template.pptx` as the only master authority and bind its SHA-256. PowerPoint editor guides are diagnostic only: never consume them for geometry and never recreate deleted guides. Use the actual slide size plus the V5.8 internal safe area. Do not create palette swatches, RGB reference cards, theme-color blocks, or pasteboard objects.

Call `clear_shape_effects` for every generated object and `clear_presentation_effects` before the final save. Shadow, reflection, glow, soft edge, and 3D are forbidden on slides, masters, and custom layouts; theme-inherited effects count as forbidden.

## Validate, build, render, and package

```powershell
python scripts/project_pipeline.py <project> --init
python scripts/project_pipeline.py <project> --materialize
python scripts/project_pipeline.py <project> --compile
python scripts/project_pipeline.py <project> --run --output <project>/output/report.pptx
python scripts/pack_delivery.py --project <project> --pptx <project>/output/report.pptx --generator <project>/generate_deck.py --output "$HOME/Desktop/<name>.zip"
```

Packaging is the default terminal gate. The desktop remains the default output location, but any explicit output path is valid for V5.8.4. If the user explicitly requests loose PPTX files, that request overrides the container format; copy only structurally valid final PPTX files and do not add unrequested ZIPs.

Do not advance page states. `project_pipeline.py` derives cache hits from real input and output hashes, updates `.build/pipeline_timing.json`, and writes the final audit records automatically.

`scripts/blueprint_fidelity.py` compares low-frequency body structure, region distribution, and visual ink mass. `blueprint_alignment_audit.py` reports module topology, labels, and visual treatment. `ppt_asset_audit.py` reports crop/insertion coverage, and `ppt_text_audit.py` proves the final XML contains selected aligned text without encoding-loss placeholders. The text audit and `pipeline_result.json` both bind to the exact final PPTX SHA-256. Skeleton, asset, palette, density, routing, evidence, and fidelity findings remain warnings.

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
- Fixed 20/16/12 pt top hierarchy; body 8-12 pt; source 7-8 pt.
- Blue-gray derivatives dominate. Reserve `#1E386B` for the top skeleton, structural anchors, and strongest series; use `#3F628F`, `#7391B3`, and `#9DB4CC` with neutral grays derived from `#EDEDED` (`#F5F5F5`, `#D9D9D9`, `#B7B7B7`, `#7F7F7F`). Neutral gray occupies 8-35% of the body; navy body fill stays within 20%. `#C00000` is limited to explicit data emphasis.
- No large red card, red section fill, red background region, or red header system.
- No blue “核心判断” label inside the core box.
- No separator rule above the source.
- No decorative line or long blue rule above the chapter title.
- Chapter title, page-title text, and first core bullet share one left anchor within 0.02 inches.
- Chapter, page title, and core judgment tops are 0.4 cm, 1.5 cm, and 2.7 cm within 0.02 inches.
- Page-title bottom and core-judgment top have at least 0.06 inches of clear space.
- No palette/RGB reference swatches or other off-slide objects on slides, masters, or custom layouts.
- Keep text, numbers, labels, sources, tables, and chart components editable; only complex non-native visuals may be bounded crops.
- Every formal blueprint is byte-identical to the immutable original ImageGen result. The final PPT render is a structural benchmark comparison, not the formal blueprint source.
- Every independent raster subject is declared, extracted, and inserted separately with aspect-preserving contain fit; declared/extracted/inserted counts must match.
- The V5.8 body uses adaptive density and supports any justified number of decorative/supporting visuals; their inventory is diagnostic, not a quota.
- Aim to map every source-assigned `must_keep` item and at least 80% of `must_keep + supporting` evidence to real modules; shortfalls are reported as warnings.
- No shadow, reflection, glow, soft edge, or 3D effect survives on a slide, master, or custom layout.
- References contribute structure, text density, and chart placement only.
- Avoid poster/dashboard/magazine styling and gradient, 3D, glow, or heavy shadow.

## Standard Report PPT V5.7 compatibility

Schema `"schema_version": "5.7"` retains its analytical canvas contract: Keep charts, tables, matrices, and flows as the primary evidence-bearing body. Use small pictograms, supplied logos, flags, or bounded schematic accents as supporting accents rather than large hero images, inside the historical **6-12% of the body area** band and a **reserved icon lane**. This compatibility path does not require a photo, map, logo, device, or product image. These rules do not apply to V5.8 projects. V5.5 compatibility remains available through `direct_project.py`.

V5.8.4 changes only the post-blueprint path. Projects with `pipeline_revision: "5.8.3"` retain V5.8.3 behavior; other V5.8 projects retain V5.8.2 behavior. Immutable tags `v5.8.2` and `v5.8.3` remain rollback points.
