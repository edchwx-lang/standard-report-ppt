# PPT quality policy V5.8.4

V5.8.4 retains V5.8.3 intake and the V5.8.2 visual-first default-release policy. It adds one internal post-blueprint alignment stage so display text, visual subjects, and module topology reach the PPT builder.

## Blockers

1. Required source, template, or blueprint missing, corrupt, unreadable, empty, or changed since its recorded SHA-256 digest.
2. Blueprint aspect ratio outside 1.50-2.05, full-page effective content below 0.5%, or body-region effective content below 0.25%.
3. Invalid JSON/runtime structure, unsupported element types, invalid executable coordinates, or unusable chart data.
4. PowerPoint dependency repair failure, build/save/open/render failure, invalid page count, or damaged PPTX.
5. Canonical text missing or corrupted in final PPT XML.
6. Formal blueprint hash differs from the locked ImageGen artifact, or the delivery package fails integrity checks.
7. For a V5.8.4 blueprint project only, `.build/blueprint_alignment.json` is missing, unreadable, stale, does not cover every page, or is not internally reviewed.

## Warnings

Blueprint text/OCR differences; recorded factual corrections; uncertain text fallback; additional numbering; visual-plan/count/crop/insertion differences; many or no decorative visuals; crop contamination or omission; chart routing; module topology differences; missing advisory labels; matrices; density; palette; red semantics; evidence coverage; core length; master skeleton; minor overlap; asset audit; and structural fidelity.

Warnings produce `pass_with_warnings` and never ask the user to manually release a page. ImageGen may receive one transport retry only when no image artifact was produced. Once an image exists, it is locked.

Audits continue to run and contribute metrics. Packaging requires correct page count, valid PPTX and ZIP artifacts, exact canonical PPT text, formal-blueprint hash identity, matching final-PPTX SHA-256 in both `ppt_text_audit.json` and `pipeline_result.json`, and `blocker_count: 0`; it does not require every advisory audit to report `ok=true`.

Run `ppt_skeleton_audit.py` and `ppt_asset_audit.py` for diagnostic metrics; their ordinary visual findings are warnings in V5.8.2.
