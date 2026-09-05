from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
from typing import Any

from PIL import Image, ImageChops, ImageStat, ImageDraw


SCHEMA_VERSION = "6.3"
RUNTIME_REVISION = "6.3.1"
_EDITABLE_KINDS = frozenset(
    {
        "text",
        "number",
        "panel",
        "section_bar",
        "chart",
        "chart_segment",
        "table",
        "table_cell",
        "line",
        "connector",
        "arrow",
        "basic_geometry",
        "icon",
        "pictogram",
    }
)
_CROP_KINDS = frozenset({"photo", "logo", "map", "illustration", "complex_icon"})
_IGNORABLE_KINDS = frozenset({"texture", "noise", "antialiasing", "decoration"})
_KINDS = _EDITABLE_KINDS | _CROP_KINDS | _IGNORABLE_KINDS


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"expected object: {path}")
    return value


def _write_json_atomic(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    temporary.replace(path)


def _issue(code: str, slide_id: str, message: str) -> dict[str, str]:
    return {
        "code": code,
        "severity": "blocker",
        "stage": "v63_visual_census",
        "slide_id": slide_id,
        "message": message,
    }


def _valid_box(box: Any, body: list[int]) -> bool:
    if not isinstance(box, list) or len(box) != 4:
        return False
    try:
        x1, y1, x2, y2 = [float(value) for value in box]
    except (TypeError, ValueError):
        return False
    left, top, width, height = body
    return (
        all(math.isfinite(v) for v in (x1,y1,x2,y2))
        and x2 > x1
        and y2 > y1
        and x1 >= left
        and y1 >= top
        and x2 <= left + width
        and y2 <= top + height
    )


def _body_has_material_ink(project: Path, slide_id: str, body: list[int]) -> bool:
    path = project / "blueprints" / f"{slide_id}.png"
    if not path.is_file():
        return True
    left, top, width, height = body
    with Image.open(path) as source:
        image = source.convert("RGB").crop((left, top, left + width, top + height))
    if image.width == 0 or image.height == 0:
        return False
    background = Image.new("RGB", image.size, image.getpixel((0, 0)))
    difference = ImageChops.difference(image, background).convert("L")
    statistic = ImageStat.Stat(difference)
    return bool(statistic.mean and statistic.mean[0] > 0.75)


def validate_candidate_hierarchy(candidates: list[dict]) -> list[dict]:
    errors = []
    by_id = {c.get('candidate_id'): c for c in candidates if isinstance(c, dict)}
    for cid, candidate in by_id.items():
        subject = candidate.get('observed_subject', '')
        if subject in {'world_map', 'complex_map'} and (candidate.get('kind') != 'map' or candidate.get('expected_treatment') != 'crop'):
            errors.append(_issue('V63_CENSUS_SUBJECT_SUBSTITUTED', '', str(cid)))
        if subject == 'brand_logo' and candidate.get('kind') != 'logo':
            errors.append(_issue('V63_CENSUS_SUBJECT_SUBSTITUTED', '', str(cid)))
        children = candidate.get('child_candidate_ids', [])
        if not isinstance(children, list):
            errors.append(_issue('V63_CENSUS_CHILD_MISSING', '', str(cid)))
            continue
        for child in children:
            if child not in by_id:
                errors.append(_issue('V63_CENSUS_CHILD_MISSING', '', f'{cid}: {child}'))
            elif by_id[child].get('parent_candidate_id') != cid:
                errors.append(_issue('V63_CENSUS_PARENT_MISMATCH', '', f'{cid}: {child}'))
        trail = set()
        current = cid
        while current is not None:
            if current in trail:
                errors.append(_issue('V63_CENSUS_PARENT_CYCLE', '', str(cid)))
                break
            trail.add(current)
            node = by_id.get(current)
            if node is None:
                errors.append(_issue('V63_CENSUS_PARENT_MISSING', '', str(cid)))
                break
            parent = node.get('parent_candidate_id')
            if parent in by_id and current not in by_id[parent].get('child_candidate_ids', []):
                errors.append(_issue('V63_CENSUS_PARENT_MISMATCH', '', str(current)))
            current = parent
    return errors


def validate_census_amendment(original: dict, amended: dict, changes: list[dict]) -> list[dict]:
    errors = []
    if set(original.get('pages', {})) != set(amended.get('pages', {})):
        return [_issue('V63_CENSUS_AMENDMENT_INVALID', '', 'page set changed')]
    evidence = {(c.get('slide_id'), c.get('candidate_id')): c for c in changes if isinstance(c, dict)}
    for sid, old_page in original.get('pages', {}).items():
        new_page = amended['pages'][sid]
        for key in ('blueprint_sha256', 'body_roi_px'):
            if old_page.get(key) != new_page.get(key):
                errors.append(_issue('V63_CENSUS_AMENDMENT_INVALID', sid, f'{key} changed'))
        old = {c['candidate_id']: c for c in old_page.get('candidates', [])}
        new = {c['candidate_id']: c for c in new_page.get('candidates', [])}
        for cid in set(old) - set(new):
            errors.append(_issue('V63_CENSUS_AMENDMENT_REMOVAL', sid, cid))
        for cid, candidate in new.items():
            if candidate == old.get(cid):
                continue
            record = evidence.get((sid, cid), {})
            box = record.get('evidence_px')
            if not record.get('reason') or record.get('action') not in {'add', 'correct', 'refine'} or not isinstance(box, list) or len(box) != 4 or box != candidate.get('bbox_px'):
                errors.append(_issue('V63_CENSUS_AMENDMENT_EVIDENCE_REQUIRED', sid, cid))
            if cid in old and (candidate.get('expected_treatment') == 'ignore' or old[cid].get('text') != candidate.get('text')):
                errors.append(_issue('V63_CENSUS_AMENDMENT_REMOVAL', sid, cid))
    return errors


def validate_visual_census(
    project_dir: str | Path, census: dict[str, Any]
) -> dict[str, Any]:
    project = Path(project_dir).resolve()
    tiles_path = project / ".build" / "v63_visual_review_tiles.json"
    if not tiles_path.is_file():
        return {
            "schema_version": SCHEMA_VERSION,
            "ok": False,
            "blockers": [_issue("V63_REVIEW_TILES_MISSING", "", str(tiles_path))],
            "candidate_count": 0,
        }
    tiles = _read_json(tiles_path)
    blockers: list[dict[str, str]] = []
    pages = census.get("pages") if isinstance(census, dict) else None
    expected_pages = tiles.get("pages", {})
    if (
        census.get("schema_version") != SCHEMA_VERSION
        or census.get("deconstruction_runtime_revision") != RUNTIME_REVISION
        or not isinstance(pages, dict)
        or set(pages) != set(expected_pages)
    ):
        blockers.append(
            _issue("V63_CENSUS_HEADER_INVALID", "", "census header or page set is invalid")
        )
        pages = pages if isinstance(pages, dict) else {}
    candidate_count = 0
    for slide_id, expected in expected_pages.items():
        page = pages.get(slide_id, {}) if isinstance(pages.get(slide_id), dict) else {}
        body = expected.get("body_roi_px", [])
        expected_tile_ids = [item.get("tile_id") for item in expected.get("tiles", [])]
        if page.get("blueprint_sha256") != expected.get("blueprint_sha256"):
            blockers.append(_issue("V63_CENSUS_BLUEPRINT_HASH_MISMATCH", slide_id, "blueprint hash does not match review tiles"))
        if page.get("body_roi_px") != body:
            blockers.append(_issue("V63_CENSUS_BODY_ROI_MISMATCH", slide_id, "body ROI does not match review tiles"))
        reviewed = page.get("reviewed_tile_ids")
        if not isinstance(reviewed, list) or set(reviewed) != set(expected_tile_ids):
            blockers.append(_issue("V63_CENSUS_REVIEW_INCOMPLETE", slide_id, "all full-body and overlapping tiles must be reviewed"))
        candidates = page.get("candidates", [])
        if not isinstance(candidates, list):
            blockers.append(_issue("V63_CENSUS_CANDIDATES_INVALID", slide_id, "candidates must be a list"))
            candidates = []
        if not candidates and isinstance(body, list) and len(body) == 4 and _body_has_material_ink(project, slide_id, body):
            blockers.append(_issue("V63_CENSUS_EMPTY_NONBLANK", slide_id, "nonblank blueprint body cannot self-certify an empty census"))
        for error in validate_candidate_hierarchy(candidates):
            error['slide_id'] = slide_id
            blockers.append(error)
        seen: set[str] = set()
        for candidate in candidates:
            candidate_count += 1
            if not isinstance(candidate, dict):
                blockers.append(_issue("V63_CENSUS_CANDIDATE_INVALID", slide_id, "candidate must be an object"))
                continue
            candidate_id = candidate.get("candidate_id")
            if not isinstance(candidate_id, str) or not candidate_id or candidate_id in seen:
                blockers.append(_issue("V63_CENSUS_ID_INVALID", slide_id, f"invalid or duplicate candidate id {candidate_id!r}"))
            else:
                seen.add(candidate_id)
            kind = candidate.get("kind")
            treatment = candidate.get("expected_treatment")
            if kind not in _KINDS:
                blockers.append(_issue("V63_CENSUS_KIND_INVALID", slide_id, f"unsupported kind {kind!r}"))
            if not _valid_box(candidate.get("bbox_px"), body):
                blockers.append(_issue("V63_CENSUS_BOX_INVALID", slide_id, f"{candidate_id or '?'} has invalid body box"))
            candidate_tiles = candidate.get("review_tile_ids")
            if (
                not isinstance(candidate_tiles, list)
                or "FULL" not in candidate_tiles
                or not set(candidate_tiles).issubset(set(expected_tile_ids))
            ):
                blockers.append(_issue("V63_CENSUS_TILE_BINDING_INVALID", slide_id, f"{candidate_id or '?'} has invalid tile binding"))
            if candidate.get("confidence") not in {"high", "medium", "low"}:
                blockers.append(_issue("V63_CENSUS_CONFIDENCE_INVALID", slide_id, f"{candidate_id or '?'} requires confidence"))
            if kind in _EDITABLE_KINDS and treatment != "editable":
                blockers.append(_issue("V63_CENSUS_EDITABLE_CLASS_CROPPED", slide_id, f"{candidate_id or '?'} must remain editable"))
            if kind in _CROP_KINDS and treatment == "ignore":
                blockers.append(_issue("V63_CENSUS_MATERIAL_OBJECT_IGNORED", slide_id, f"{candidate_id or '?'} is material and cannot be ignored"))
            if treatment == "crop" and kind not in _CROP_KINDS:
                blockers.append(_issue("V63_CENSUS_EDITABLE_CLASS_CROPPED", slide_id, f"{candidate_id or '?'} is not an approved crop class"))
            if treatment == "ignore" and (
                kind not in _IGNORABLE_KINDS
                or not isinstance(candidate.get("ignore_reason"), str)
                or not candidate.get("ignore_reason", "").strip()
            ):
                blockers.append(_issue("V63_CENSUS_IGNORE_INVALID", slide_id, f"{candidate_id or '?'} has invalid ignore treatment"))
            if treatment not in {"editable", "crop", "ignore"}:
                blockers.append(_issue("V63_CENSUS_TREATMENT_INVALID", slide_id, f"{candidate_id or '?'} has invalid treatment"))
    return {
        "schema_version": SCHEMA_VERSION,
        "deconstruction_runtime_revision": RUNTIME_REVISION,
        "ok": not blockers,
        "status": "pass" if not blockers else "blocked",
        "candidate_count": candidate_count,
        "blockers": blockers,
    }


def validate_and_write_visual_census(
    project_dir: str | Path, census: dict[str, Any]
) -> dict[str, Any]:
    project = Path(project_dir).resolve()
    report = validate_visual_census(project, census)
    _write_json_atomic(project / ".build" / "v63_visual_census_report.json", report)
    if report["ok"]:
        _write_json_atomic(project / ".build" / "v63_visual_census.json", census)
        for sid, page in census['pages'].items():
            with Image.open(project / 'blueprints' / f'{sid}.png') as source:
                preview = source.convert('RGB')
            draw = ImageDraw.Draw(preview)
            for index, candidate in enumerate(page['candidates'], 1):
                box = candidate['bbox_px']
                draw.rectangle(box, outline='#FF6600', width=1)
                draw.text((box[0], box[1]), str(index), fill='#E00000')
            preview.save(project / '.build' / f'v63_census_preview_{sid}.png')
    return report
