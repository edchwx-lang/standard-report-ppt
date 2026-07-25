# V6.0 Cross-Platform Backend Contract

V6 keeps source ingestion, canonical authoring, ImageGen prompting, one successful
artifact per page, the single no-artifact transport retry, and immutable formal
blueprint locking unchanged. After locking, `construction_mode` selects
`deconstruct` or `bitmap`; it never selects whether ImageGen runs.

| construction mode | Windows | macOS |
|---|---|---|
| `deconstruct` | `windows_com_v584` | `mac_python_pptx_v2` |
| `bitmap` | `windows_com_v584` | `mac_python_pptx_v2` |

Deconstruction must pass both the prebuild composite-body-image prohibition and
the postbuild native editability audit. Unsupported Mac structures fail with
`MAC_RECONSTRUCTION_UNSUPPORTED`; they are not replaced by a page-body bitmap.
Both V6 deconstruction backends require the locked full page plus Q1–Q4 review,
G0–G3 visual census, atomic crop declarations, and reverse bindings for native
lines, arrows, flows, charts, tables, rectangles, and ovals. A raster crop must
contain exactly one tightly bounded non-native subject, no editable text, and no
native geometry. Mac compilation also rejects a crop containing complete dark perimeter frame,
and Mac postbuild auditing rejects any picture outline.

Bitmap construction contains exactly one reviewed body image per page. Its
runtime box uses `SKEL_CORE.left/width`, top `SKEL_CORE.bottom + 0.12in`, and
bottom `SKEL_SOURCE.top - 0.195in`. The image is zero-crop maximal centered
contain. `SKEL_CHAPTER`, `SKEL_TITLE`, `SKEL_CORE`, `SKEL_SOURCE`, and
`SKEL_PAGE_NUMBER` remain native text shapes.

V6 is released first as `6.0.0-rc1`; a real PowerPoint for Mac smoke test is
required before the final `6.0.0` label.

## V5.9.1 compatibility

V5.9.1 retains both local V5.9 backends and adds one shared reconstruction
contract before platform dispatch. Windows remains `windows_com_v584`; macOS
remains `mac_python_pptx_v1`. No remote Windows executor is permitted.

## Shared stages

Source ingestion, canonical authoring, ImageGen, immutable blueprint locking,
blueprint alignment, evidence mapping, and `page_specs` are platform-neutral.

## Blueprint hard gate

In blueprint mode, one valid immutable ImageGen blueprint per final slide must
exist before platform dispatch. Missing or stale blueprints must not reach either builder.

The capability probe is the real first slide, never a throwaway circle or test
image. A first no-artifact transport failure may be retried once. Once an
artifact exists, it is locked and is never regenerated automatically.

## Windows

`windows_com_v584` reuses the V5.8.4 COM generator, PowerPoint text
measurement, native rendering, and existing audits.

## macOS

`mac_python_pptx_v1` constructs the PPTX locally with `python-pptx`.
PowerPoint for Mac or LibreOffice may render locally, but neither constructs
slide objects. No Windows executor is used.

## Quality evidence

COM evidence and Mac OOXML/font-metric evidence are reported separately.
`structurally_valid_unrendered` is not a formal visual pass and cannot be
packaged as the verified three-entry delivery ZIP.

## Prohibited fallbacks

No backend may silently change blueprint mode to fast mode. The Mac backend may
not substitute artifact-tool, PptxGenJS, a Windows executor, or a full-page
blueprint background.

## External boundary

V5.9 cannot guarantee ImageGen entitlement, client tool availability, network
transport, or service health on every computer. It guarantees that a returned
artifact is locked and consumed, and that a missing artifact stops truthfully
before COM or `python-pptx` construction begins.
