"""Record the agent's image-inspection findings, not an automatic visual scorer."""
from pathlib import Path
import shutil
from tests.run_v63_visual_repair import load, read, write

BASE = Path('C:/Users/edchw/Documents/START PPT/V63_visual_repair_validation')

FIRST = {
    'TEST': {
        'S01': [(['Y_TICK_11000', 'Y_TICK_10000', 'CAGR_LABEL', 'CAGR_VALUE', 'PEOPLE_BODY', 'VALUE_BODY', 'REGION_BODY'],
                 'material', 'Actual first-render text wraps beyond source line breaks; driver copy overlaps headings.'),
                (['CURVE_ARROW_1', 'CURVE_ARROW_2'], 'material', 'Open curved paths are present but native arrowheads are absent.'),
                (['CHART_AREA'], 'warning', 'Editable area uses flat fill rather than source gradient.'),
                (['PHONE_FRAME'], 'warning', 'Tiny synthetic phone UI glyphs are unreadable in source; native marks preserve density without invented copy.')],
        'S02': [(['EUROPE_VALUE', 'EUROPE_SHARE', 'BANDAI_NAME'], 'material', 'European value/percentage overlap and company name wraps.'),
                (['WORLD_MAP'], 'material', 'Detailed geography retained, but transparent connector/pin masks leave visible light apertures.')]
    },
    'S3': {'S01': [(['GROWTH_SUMMARY', 'END_YEAR', 'FORECAST', 'TOP10', 'TOP10_SHARE', 'LEGO_SHARE', 'POPMART_SHARE_VALUE', 'T1_HEADER_TEXT', 'JS_BODY'],
                    'material', 'Actual render shows unexpected wrapping, percent-sign splitting or adjacent text overlap.'),
                   (['CHINA_MAP'], 'material', 'Connector masks miss original dashed strokes, producing parallel ghost lines and pin squares.')]} }

# Recorded only AFTER opening all three second-build images. These are residual
# findings, not evidence of pixel identity or automatically perfect recovery.
SECOND = {
    'TEST': {
        'S01': [(['CHART_AREA'], 'warning', 'Editable chart retains curve, values and ticks; area is flat rather than gradient.'),
                (['PHONE_FRAME'], 'warning', 'Phone shell/products restored; unidentifiable source UI glyphs are native density marks, not exact glyph recovery.'),
                (['PEOPLE_BODY','VALUE_BODY','REGION_BODY'], 'warning', 'Unexpected wrapping/heading overlap removed; one-pass font fit makes dense copy slightly smaller than source.')],
        'S02': [(['WORLD_MAP'], 'warning', 'Geography and native annotations restored; tiny sampled connector seams remain at coast/gradient intersections.'),
                (['US_PANEL','JP_PANEL','FLOW_MIDDLE_PANEL','FLOW_RIGHT_PANEL'], 'warning', 'Native round-corner radius differs from source.'),
                (['CHINA_JAPAN_UP','SOUTHEAST_UP'], 'warning', 'Native arrowhead proportions differ from source circular callout arrows.')]
    },
    'S3': {'S01': [(['CHINA_MAP'], 'warning', 'Parallel ghost lines and square pin apertures removed; thin local cleanup seams may remain at coastal crossings.'),
                   (['GROWTH_ARROW','START_CARD','END_CARD'], 'warning', 'Editable curved outline/flat fills approximate source gradient and corner details.'),
                   (['GD_BODY','ZJ_BODY','JS_BODY'], 'warning', 'Province copy is editable and complete, but in-line province-name weight is not separately restored.')]} }


def record(name, findings, attempt):
    project = BASE / name
    output = next((project / 'output').glob('*.pptx'))
    state = read(project / '.build/v6_build_attempt.json')
    if state['attempt_count'] != attempt:
        raise ValueError('Review must refer to current real build')
    census = read(project / '.build/v63_visual_census.json')
    pages = []
    for sid, page in census['pages'].items():
        groups = findings[sid]
        by_id = {cid: (severity, message) for ids, severity, message in groups for cid in ids}
        known = {c['candidate_id'] for c in page['candidates']}
        if not set(by_id) <= known:
            raise ValueError(set(by_id) - known)
        checks = [{'candidate_id': c['candidate_id'], 'status': 'difference' if c['candidate_id'] in by_id else 'present',
                   'evidence_px': c['bbox_px'],
                   'evidence': by_id[c['candidate_id']][1] if c['candidate_id'] in by_id else
                   'Agent inspected source page/overlapping tiles and this actual PowerPoint render; declared object visible at this source region.'}
                  for c in page['candidates']]
        differences = [{'candidate_ids': ids, 'severity': severity, 'message': message}
                       for ids, severity, message in groups]
        pages.append({'slide_id': sid, 'object_checks': checks, 'differences': differences})
    review = {'schema_version': '6.3', 'deconstruction_runtime_revision': '6.3.1',
              'reviewed': True, 'review_method': 'agent visual inspection; not generated from similarity score',
              'bindings': load('v63_acceptance').visual_bindings(project, output), 'pages': pages}
    write(project / '.build/v63_visual_review.json', review)
    archive = project / '.build' / f'attempt_{attempt}'
    archive.mkdir(exist_ok=True)
    for item in ['v63_visual_review.json', 'v63_scene_graph.json', 'v63_visual_census.json', 'v63_asset_ledger.json',
                 'v63_object_ledger.json', 'v63_pending_review.json', 'v6_build_attempt.json']:
        shutil.copy2(project / '.build' / item, archive / item)
    shutil.copy2(output, archive / output.name)
    shutil.copytree(project / '.build/rendered/current', archive / 'rendered', dirs_exist_ok=True)
    shutil.copytree(project / '.build/assets', archive / 'assets', dirs_exist_ok=True)
    print('REVIEW_RECORDED', name, attempt)


if __name__ == '__main__':
    for name, findings in FIRST.items():
        record(name, findings, 1)
