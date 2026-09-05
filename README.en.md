# Standard Report PPT · V6.3.1

[中文](README.md) | **English**

A Codex skill for research presentations with a fixed PowerPoint master. Understand the source, generate a visual blueprint, then choose a faithful bitmap slide or an editable reconstruction.

V6.3.1 focuses on **visual reverse compilation after blueprint locking**: observe objects, positions, colors, layers and relationships instead of forcing the design into a matrix template. Windows uses PowerPoint COM; macOS uses python-pptx/OOXML with shared scene semantics.

## One page, three actual outputs

The TEST example combines market size, regional sales markets and company competition. Both PPTs use the same locked blueprint, not separately generated designs.

### 1. Original ImageGen blueprint

![Original TEST blueprint](docs/images/S01.png)

### 2. Bitmap-mode PowerPoint

![Bitmap slide exported by native PowerPoint](docs/images/S02.png)

Five editable skeleton regions and one cropped body image: faster delivery with direct preservation of the blueprint appearance.

### 3. Deconstruct-mode PowerPoint

![Editable reconstruction exported by native PowerPoint](docs/images/S03.png)

The example has **195 editable body objects and 11 local images**, plus five master placeholders. Text, numbers, chart components and basic shapes remain editable; the map base and product illustrations retain image detail.

> This demonstrates visual recovery, not validated industry research. The source blueprint has an incorrect Europe leader location and inconsistent bar proportions; the showcase preserves them. Generated brand imagery does not imply authorization or endorsement. Visible bands of overlapping products are not complete transparent object cutouts.

## Choose a mode

| | Bitmap | Deconstruct |
|---|---|---|
| Blueprint | Required and locked | Required and locked |
| Five skeleton regions | Editable | Original master placeholders, text-only updates |
| Body | One cropped image | Object-by-object reconstruction |
| Body text, numbers, charts, tables, basic geometry | Not individually editable | Editable |
| Complex maps, logos, photos, illustrations | Within the body image | Local crops without report text; intrinsic logo text is allowed |
| Trade-off | Faster, direct visual preservation | Slower, easier downstream editing |

Charts may comprise editable axes, paths, bars, nodes and labels—not necessarily Excel-backed native Chart objects. Neither mode silently falls back to the other.

## Install

Use a Codex environment with local skills and built-in ImageGen. Windows requires desktop Microsoft PowerPoint, Python 3.12 and the locked dependencies. macOS uses Python 3.12; visual verification requires PowerPoint for Mac or a supported local renderer.

Fresh Windows installation:

```powershell
git clone --branch v6.3.1 --single-branch https://github.com/edchwx-lang/standard-report-ppt.git "$env:USERPROFILE/.codex/skills/standard-report-ppt"
python -m pip install -r "$env:USERPROFILE/.codex/skills/standard-report-ppt/requirements-windows.lock"
```

Fresh macOS installation:

```bash
git clone --branch v6.3.1 --single-branch https://github.com/edchwx-lang/standard-report-ppt.git "$HOME/.codex/skills/standard-report-ppt"
python3 -m pip install -r "$HOME/.codex/skills/standard-report-ppt/requirements-macos.lock"
```

Back up existing installations and inspect local changes before updating; do not overwrite uncommitted work. The tag pins this release; use `main` to follow development. Reload skills or start a new Codex task after installation.

## From source to presentation

Attach the document and specify the exact page count and mode:

```text
$standard-report-ppt Create 1 slide from TEST.docx in deconstruct mode.
Parse and combine market size, global regional markets and company competition.
```

Select “bitmap mode” for the faster route, or explicitly request both modes against the same blueprint.

1. **Confirm page count and mode.** These are the only routine user confirmations. No unrequested cover or contents slides.
2. **Parse structurally.** Read paragraphs, tables and embedded images; preserve figures, dates, units, qualifiers and sources. Organize conclusions and evidence. Do not relabel sales as production capacity.
3. **Generate the blueprint.** Choose charts, maps, relationships or image/text layouts from the evidence, not reconstruction convenience. Accept one successful ImageGen result per page.
4. **Lock the original.** Keep bytes and hashes immutable. Reconstruction difficulty does not authorize another blueprint generation.
5. **Follow the selected route.** Bitmap reviews the full page and crops out the skeleton. Deconstruct observes the actual body boundary, reviews the full image and six overlapping tiles, writes an independent census, then compiles an atomic scene.
6. **Rebuild and separate assets.** Keep report text, numbers, charts, tables, lines and basic geometry native. Crop complex visuals locally; rebuild map labels and leaders separately. Fill the five master-owned regions without restyling them.
7. **Render and review.** Inspect actual PPT exports for omissions, ghosts, cropping, geometry and typography. Material differences permit one targeted correction, never a third automatic build.
8. **Accept and deliver.** Validate the actual PPT, master, assets and hashes. Retry packaging without rebuilding an accepted PPT. Disclose ordinary residual differences.

The default ZIP contains the PPTX, `blueprints.zip` and `py.zip`, retaining blueprints/assets/scenes and the generator entry point. Re-running requires the matching skill runtime and project manifests; this is not a standalone application. An explicit loose-PPTX request overrides ZIP delivery.

## V6.3.1 fixes and scope

- Independent visual census and per-logo/icon inventory; complex geography is not replaced by schematic polygons.
- One body-coordinate transform keeps images, labels and leaders registered. Optional one-time body text fitting uses actual font measurements.
- Explicit source-pixel corner radii compile into shared editable paths instead of oversized default rounding.
- Packaging understands V6.3 acceptance/compile contracts and includes actual ledger assets while rejecting stale hashes.
- Windows discovers the installed Node bundle with system Python. A failed external bitmap preview can recover through one native export of the existing PPT, without rebuilding.
- Separate PPT acceptance from ZIP completion, retain failure details, and allow at most two actual builds and one visual refinement.

**Boundary:** pre-lock authoring/ImageGen, locked blueprint bytes, bitmap crop/layout logic and the user master remain unchanged. Bitmap changes are limited to post-lock preview environment/recovery.

**Platform verification:** Windows dual-mode output has been run. Shared Mac geometry/compilation has automated coverage, but this release has not been visually verified on native Mac hardware. Preserve `mac_native_render_unverified`; Windows results are not proof of Mac visual parity.

## Development and verification

```bash
python -m unittest discover -s tests -p "test_*.py"
```

Normal users do not need to author scenes or execute every CLI step. To debug a prepared project:

```bash
python scripts/project_pipeline.py <project> --init
# The agent prepares content, real ImageGen provenance, blueprints and mode-specific visual records per SKILL.md
python scripts/project_pipeline.py <project> --materialize
python scripts/project_pipeline.py <project> --run --output <project>/output/report.pptx
```

`awaiting_visual_review` is an internal continuation: inspect the render, record findings, and run again to finalize without rebuilding or another user approval.

Details: [SKILL.md](SKILL.md) · [Post-lock standard](references/v63_visual_repair.md) · [Release validation](docs/releases/v6.3.1.md). The original TEST Word document and complete user projects are not published. Users must verify rights to sources, logos, templates and generated content.
