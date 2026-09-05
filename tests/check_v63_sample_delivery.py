"""Read-only Windows cache check and isolated, unrendered Mac-branch compilation."""
from pathlib import Path
import shutil
import time
from PIL import Image, ImageDraw
from pptx import Presentation
from tests.run_v63_visual_repair import ROOT, load, read, write, sha

BASE = Path('C:/Users/edchw/Documents/START PPT/V63_visual_repair_validation')


def main():
    result = {}
    contract = load('v63_skeleton_contract').read_template_contract(ROOT/'assets/company_template.pptx')
    for name in ('TEST','S3'):
        project = BASE/name
        pptx = next((project/'output').glob('*.pptx'))
        before = sha(pptx)
        state = read(project/'.build/v6_build_attempt.json')
        start = time.perf_counter()
        cached = load('project_pipeline')._run_v6_project(project, read(project/'project_brief.json'), pptx,
            catastrophic_repair=False,user_revision=False,auto_package=False)
        seconds = time.perf_counter()-start
        assert cached.get('cached') is True and before == sha(pptx)
        assert state['attempt_count'] == read(project/'.build/v6_build_attempt.json')['attempt_count'] == 2
        mac = BASE/'mac_structure'/name
        (mac/'.build').mkdir(parents=True,exist_ok=True)
        for filename in ('v63_scene_graph.json','v63_visual_census.json','v63_asset_ledger.json','slides.json'):
            shutil.copy2(project/'.build'/filename, mac/'.build'/filename)
        shutil.copytree(project/'.build/assets',mac/'.build/assets',dirs_exist_ok=True)
        # No native Mac render, no acceptance receipt, no Windows rebuild.
        mac_pptx = mac/'output/mac_structure_only.pptx'
        load('v63_mac_scene_renderer').build_deck(mac,mac_pptx,template_path=ROOT/'assets/company_template.pptx')
        mac_audit = load('v63_acceptance').audit_v63_pptx(mac_pptx,mac,template_path=ROOT/'assets/company_template.pptx')
        write(mac/'.build/structure_audit.json',mac_audit)
        result[name] = {'windows_cached':True,'cache_seconds':seconds,'pptx_sha256':before,
            'build_attempts':state['attempt_count'],'visual_refinements':state.get('visual_refinement_count'),
            'mac_structure':mac_audit,'mac_native_render_unverified':True}
        # Diagnostic source-body/output-body comparison, not an edited artifact.
        deck = Presentation(pptx)
        target = contract['body_roi_in']
        for sid,page in read(project/'.build/v63_scene_graph.json')['pages'].items():
            source = Image.open(project/'blueprints'/f'{sid}.png').convert('RGB')
            x,y,w,h = page['body_roi_px']
            source = source.crop((x,y,x+w,y+h))
            rendered = Image.open(project/'.build/rendered/current'/f'{sid}.png').convert('RGB')
            sx,sy = rendered.width/(deck.slide_width/914400),rendered.height/(deck.slide_height/914400)
            a,b,c,d = target
            rendered = rendered.crop((round(a*sx),round(b*sy),round((a+c)*sx),round((b+d)*sy)))
            canvas = Image.new('RGB',(1640,420),'#E6E6E6')
            draw=ImageDraw.Draw(canvas)
            draw.text((20,8),'LOCKED SOURCE BODY',fill='black')
            draw.text((840,8),'NATIVE PPT BODY - BUILD 2',fill='black')
            for left,img in ((10,source),(830,rendered)):
                img.thumbnail((800,380),Image.Resampling.LANCZOS)
                canvas.paste(img,(left+(800-img.width)//2,30+(380-img.height)//2))
            dest=BASE/f'{name}_{sid}_comparison.png'
            canvas.save(dest)
        print(name, 'cached',round(seconds,3),'Mac structure',mac_audit['ok'])
    write(BASE/'delivery_checks.json',result)


if __name__=='__main__':
    main()
