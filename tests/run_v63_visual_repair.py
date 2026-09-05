"""Real post-lock replay harness. Never fabricates ImageGen transport evidence."""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import shutil
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def load(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / 'scripts' / f'{name}.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def read(path):
    return json.loads(path.read_text(encoding='utf-8'))


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def prepare(workspace):
    manifest = read(ROOT / 'tests/fixtures/v63_visual_repair_manifest.json')
    if sha(ROOT / 'assets/company_template.pptx') != manifest['template_sha256']:
        raise ValueError('TEMPLATE_CHANGED')
    for sample in manifest['samples'].values():
        if sha(workspace / sample['path']) != sample['sha256']:
            raise ValueError('BLUEPRINT_CHANGED: ' + sample['path'])
    for name, original in [('TEST', 'TEST_v63_full_2p'), ('S3', 'S3_v63_validation')]:
        source = workspace / original
        project = workspace / 'V63_visual_repair_validation' / name
        if project.exists():
            print('REUSE_INPUTS', project)
            continue
        project.mkdir(parents=True)
        (project / '.build').mkdir()
        shutil.copy2(source / 'project_brief.json', project / 'project_brief.json')
        shutil.copytree(source / 'blueprints', project / 'blueprints')
        # Only immutable source/provenance inputs; never copy old scene, acceptance
        # or attempt state. These are new repair validation projects, not restarts.
        for filename in ('slides.json', 'formal_blueprint_manifest.json', 'visual_manifest.json',
                         'imagegen_transport_report.json', 'authoring_bundle.json', 'source_extract.json',
                         'source_digest.json', 'page_specs.json', 'blueprint_text_benchmark.json',
                         'blueprint_alignment.json'):
            if (source / '.build' / filename).is_file():
                shutil.copy2(source / '.build' / filename, project / '.build' / filename)
        if (source / '.build/design_drafts').is_dir():
            shutil.copytree(source / '.build/design_drafts', project / '.build/design_drafts')
        roi_pages = {}
        for sid in ('S01', 'S02') if name == 'TEST' else ('S01',):
            key = f'TEST-{sid[1:]}' if name == 'TEST' else 'S3'
            sample = manifest['samples'][key]
            roi_pages[sid] = {'blueprint_sha256': sample['sha256'],
                             'source_body_roi_px': sample['source_body_roi_px'],
                             'review_basis': 'full source page inspected; excludes five template-owned regions'}
        write(project / '.build/v63_source_body_rois.json', {'pages': roi_pages})
        write(project / '.build/validation_origin.json', {'test_kind': 'post_lock_replay',
            'source_project': str(source), 'source_kind': 'existing_imagegen_lock' if name == 'TEST' else 'user_supplied_locked_blueprint'})
        print('PREPARED', project)


def run_project(project, phase, *, repair=False):
    pipeline = load('project_pipeline')
    brief = read(project / 'project_brief.json')
    output = project / 'output' / f'{project.name}_V6.3_修复验证.pptx'
    if phase == 'finalize':
        return pipeline._finish_v631_review(project, brief, output, auto_package=False)
    if project.name == 'TEST':
        return pipeline._run_v6_project(project, brief, output,
            catastrophic_repair=repair, user_revision=False, auto_package=False)
    # S3 enters the real production POST-LOCK functions. It is not represented
    # as a newly generated image and no production gate is patched/mocked.
    attempt_path = project / '.build/v6_build_attempt.json'
    previous = read(attempt_path) if attempt_path.is_file() else {}
    count = int(previous.get('attempt_count', 0))
    if count and not repair:
        raise ValueError('S3_REPLAY_ALREADY_BUILT')
    if count >= 2 or repair and (count != 1 or previous.get('status') not in {'catastrophic_failed', 'refinement_required'}):
        raise ValueError('S3_REPLAY_BUDGET_EXHAUSTED')
    if repair:
        pipeline._assert_v6_repair_inputs_unchanged(project, construction_mode='deconstruct', previous=previous, uses_v63=True)
    start = time.perf_counter()
    precheck = load('v63_deconstruction').prepare_deconstruction(project, backend='windows_com_v584', template_path=ROOT / 'assets/company_template.pptx')
    if not precheck['ok']:
        raise ValueError(json.dumps(precheck['blockers'], ensure_ascii=False))
    load('project_compiler')._compile_v63_windows_project(project, brief)
    attempt = {'attempt_count': count+1, 'construction_mode': 'deconstruct', 'builder_backend': 'windows_com_v584',
               'status': 'in_progress', 'visual_refinement_count': int(repair and previous.get('status') == 'refinement_required')}
    write(attempt_path, attempt)
    try:
        renderer = load('v63_windows_scene_renderer')
        renderer.build_deck(project, output, template_path=ROOT / 'assets/company_template.pptx')
        render = renderer.render_deck(output, project, expected_page_count=1)
        acceptance = load('v63_acceptance')
        audit = acceptance.audit_v63_pptx(output, project, template_path=ROOT / 'assets/company_template.pptx')
        write(project / '.build/deconstruction_editability_audit.json', audit)
        write(project / '.build/v63_pending_review.json', {'attempt_count': count+1, 'audit': audit, 'render': render,
            'bindings': acceptance.visual_bindings(project, output)})
        write(project / '.build/replay_timing.json', {'build_render_audit_seconds': time.perf_counter()-start})
        return pipeline._finish_v631_review(project, brief, output, auto_package=False)
    except Exception as exc:
        attempt.update(status='catastrophic_failed', error=str(exc), repair_contract_snapshot=pipeline._v63_refinement_contract_snapshot(project))
        write(attempt_path, attempt)
        raise


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--workspace', type=Path, required=True)
    parser.add_argument('--phase', choices=['prepare', 'build', 'finalize'], required=True)
    parser.add_argument('--project', choices=['TEST', 'S3', 'all'], default='all')
    parser.add_argument('--repair', action='store_true')
    args = parser.parse_args()
    if args.phase == 'prepare':
        prepare(args.workspace.resolve())
        return
    names = ['TEST', 'S3'] if args.project == 'all' else [args.project]
    for name in names:
        project = args.workspace.resolve() / 'V63_visual_repair_validation' / name
        print(json.dumps(run_project(project, args.phase, repair=args.repair), ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
