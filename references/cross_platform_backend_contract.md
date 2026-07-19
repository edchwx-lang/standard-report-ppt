# V5.9.1 Cross-Platform Backend Contract

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
