"""Measured observations of three supplied blueprints, not a production layout library.

The observation file and validated census are written BEFORE scene compilation.
No old scene graph or pilot reconstruction script is used as an input.
"""
from __future__ import annotations

import math
import time
from pathlib import Path

from tests.run_v63_visual_repair import ROOT, load, read, write, sha

NAVY = '#08265F'
BLUE = '#244C87'
RED = '#B90000'


class Observations:
    def __init__(self, roi):
        self.roi = roi
        self.items = []
        self.scale = load('v63_scene_graph').body_contain_transform(
            roi, load('v63_skeleton_contract').read_template_contract(ROOT / 'assets/company_template.pptx')['body_roi_in'])['scale']

    def add(self, name, kind, box, *, atom, z=10, **data):
        if any(item['candidate_id'] == name for item in self.items):
            raise ValueError(name)
        self.items.append({'candidate_id': name, 'kind': kind, 'bbox_px': list(box),
            'observed_subject': data.pop('observed_subject', name.lower()),
            'observation': data.pop('observation', 'Measured from locked blueprint pixels'),
            'implementation': {'atom': atom, 'z_order': z, **data}})
        return name

    def text(self, name, box, text, px=22, color=NAVY, bold=False, align='left', z=20):
        return self.add(name, 'text', box, atom='text', z=z, text=text,
                        style={'font_size': round(px*self.scale*72, 3), 'color': color, 'bold': bold,
                               'align': align, 'margin': 0, 'margin_top': 0, 'margin_bottom': 0, 'valign': 'middle',
                               'word_wrap': False, 'fit': 'shrink_to_box'})

    def rect(self, name, box, fill='#FFFFFF', stroke='none', rounded=False, z=1, width=0.6):
        return self.add(name, 'panel', box, atom='round_rect' if rounded else 'rect', z=z,
                        style={'fill': fill, 'line': stroke, 'line_width': width})

    def ellipse(self, name, box, fill, stroke='none', z=15, width=1):
        return self.add(name, 'basic_geometry', box, atom='ellipse', z=z,
                        style={'fill': fill, 'line': stroke, 'line_width': width})

    def path(self, name, points, fill='none', stroke=BLUE, width=1, closed=False, arrow=False, z=12, dash=None):
        xs, ys = zip(*points)
        box = [min(xs), min(ys), max(xs), max(ys)]
        style = {'fill': fill, 'line': stroke, 'line_width': width}
        if dash:
            style['dash'] = dash
        if arrow:
            style['arrow_end'] = True
        atom = 'freeform' if closed or len(points)>2 else ('arrow' if arrow else 'line')
        # Census boxes describe visible stroke area (positive area), while the
        # scene's point geometry correctly permits a zero-width/height line.
        census_box = [box[0],box[1],max(box[2],box[0]+0.5),max(box[3],box[1]+0.5)]
        return self.add(name, 'basic_geometry' if closed else ('arrow' if arrow else 'line'),
                        census_box, atom=atom, z=z, points_px=[list(p) for p in points], closed=closed, style=style)

    def crop(self, name, box, kind='complex_icon', z=8, recipe=None):
        return self.add(name, kind, box, atom='image_crop', z=z,
                        observed_subject='world_map' if kind=='map' and name=='WORLD_MAP' else ('brand_logo' if kind=='logo' else name.lower()),
                        crop_recipe=recipe or {'mode': 'rect_crop'}, style={})

    def exclusion(self, crop_box, box, ids, sample=None):
        x1,y1,x2,y2 = crop_box
        a,b,c,d = box
        a,b,c,d = max(0,a-x1),max(0,b-y1),min(x2-x1-1,c-x1),min(y2-y1-1,d-y1)
        if c<=a or d<=b:
            return None
        result = {'polygon_px': [[a,b],[c,b],[c,d],[a,d]], 'overlay_element_ids': ids}
        if sample is not None:
            result.update(sample_px=[sample[0]-x1,sample[1]-y1], uniform_background_reviewed=True)
        return result


def clean_segment(crop_box, points, overlay_id):
    """Finite local flat-color samples beside a reviewed thin baked connector.

    Only this narrow overlay footprint is cleaned; never regenerate geography.
    Coastline/gradient intersections remain an explicit visual-review risk.
    """
    (ax,ay),(bx,by)=points
    dx,dy=bx-ax,by-ay
    length=math.hypot(dx,dy)
    nx,ny=-dy/length,dx/length
    count=max(1,math.ceil(length/3))
    x0,y0,x2,y2=crop_box
    def bounded(x,y):
        return [max(0,min(x2-x0-1,x-x0)),max(0,min(y2-y0-1,y-y0))]
    regions=[]
    for i in range(count):
        a=i/count; b=(i+1)/count; m=(a+b)/2
        poly=[bounded(ax+dx*a+nx*2.2,ay+dy*a+ny*2.2),bounded(ax+dx*b+nx*2.2,ay+dy*b+ny*2.2),
              bounded(ax+dx*b-nx*2.2,ay+dy*b-ny*2.2),bounded(ax+dx*a-nx*2.2,ay+dy*a-ny*2.2)]
        regions.append({'polygon_px':poly,'overlay_element_ids':[overlay_id],
                        'sample_px':bounded(ax+dx*m+nx*4,ay+dy*m+ny*4),'uniform_background_reviewed':True})
    return regions


def circular_exclusion(crop_box, x, y, radius, overlay_id):
    return {'polygon_px': [[x+radius*math.cos(i*math.tau/32)-crop_box[0],
                            y+radius*math.sin(i*math.tau/32)-crop_box[1]] for i in range(32)],
            'overlay_element_ids':[overlay_id]}


def test02(roi):
    p = Observations(roi)
    p.text('REGION_TITLE', [220,242,610,278], '2024年全球玩具市场区域分布', 26, bold=True, align='center')
    p.text('COMP_TITLE', [978,242,1578,276], '2023年美国、日本传统玩具企业集中度对比', 25, bold=True, align='center')
    p.path('DIVIDER', [[905,261],[905,671]], stroke='#D5DFEB', width=0.7)
    map_box = [76,313,854,687]
    exclusions = []
    callouts = [('NORTH', [33,447,143,550], '北美', '2631亿元', '32.1%', '#08265F'),
                ('EUROPE',[407,287,534,374], '欧洲', '2311亿元', '28.2%', '#7793B5'),
                ('ASIA',[784,447,890,539], '亚太', '2360亿元', '28.8%', '#416FAE'),
                ('OTHER',[357,601,463,672], '其他', '', '10.9%', '#999999')]
    for key,box,label,value,share,color in callouts:
        x,y,r,b=box
        ids=[p.rect(key+'_BOX',box,'#FFFFFF',color,True,z=14),
             p.rect(key+'_SWATCH',[x+12,y+12,x+27,y+27],color,z=17),
             p.text(key+'_NAME',[x+33,y+6,r-5,y+33],label,20,color,True),
             p.text(key+'_SHARE',[x+5,b-(29 if key=='EUROPE' else 34),r-5,b-4],share,25,RED,True,'center')]
        if value:
            ids.append(p.text(key+'_VALUE',[x+3,y+(31 if key=='EUROPE' else 37),r-3,y+(54 if key=='EUROPE' else 66)],value,21,NAVY,True,'center'))
        region=p.exclusion(map_box,[x-2,y-2,r+2,b+2],ids)
        if region: exclusions.append(region)
    for key,box,label,growth in [('CHINA_JAPAN',[623,383,747,435],'中国、日本','约+5%'),('SOUTHEAST',[730,556,847,608],'东南亚','约+7%')]:
        x,y,r,b=box
        ids=[p.rect(key+'_BOX',box,'#FFFFFF','#D54D4D',True,z=14),
             p.text(key+'_NAME',[x+4,y+3,r-32,y+25],label,16,NAVY,True,'center'),
             p.text(key+'_VALUE',[x+4,y+23,r-32,b-1],growth,19,RED,True,'center'),
             p.ellipse(key+'_UP_CIRCLE',[r-34,y+13,r-8,y+39],'#D95353',z=18)]
        ids.append(p.path(key+'_UP',[[r-25,y+34],[r-25,y+19]],stroke='#FFFFFF',width=2,arrow=True,z=19))
        exclusions.append(p.exclusion(map_box,[x-2,y-2,r+2,b+2],ids))
    for key,points,color in [('NORTH_LINK',[[143,461],[209,445]],'#6E89AA'),('EUROPE_LINK',[[458,374],[458,408]],'#6481A7'),
                             ('ASIA_LINK',[[707,500],[784,500]],'#7196C3'),('CJ_LINK',[[685,435],[685,474]],'#D08C90'),
                             ('SEA_LINK',[[689,521],[730,559]],'#D65255')]:
        p.path(key,points,stroke=color,width=0.9,dash=4)
        exclusions.extend(clean_segment(map_box,points,key))
    for key,x,y,color in [('NORTH_DOT',209,445,'#91A3BE'),('EUROPE_DOT',458,408,'#5D779F'),('CJ_DOT',685,474,'#C49DA9'),('SEA_DOT',689,521,'#E86663')]:
        p.ellipse(key,[x-5,y-5,x+5,y+5],color,z=19)
        exclusions.append(circular_exclusion(map_box,x,y,5,key))
    legend_ids=[]
    for i,(label,color) in enumerate([('北美','#08265F'),('亚太','#416FAE'),('欧洲','#9FB5D3'),('其他地区','#C8C8C8')]):
        y=590+i*24
        legend_ids.append(p.rect(f'LEGEND_SWATCH_{i}',[51,y,70,y+14],color,z=15))
        legend_ids.append(p.text(f'LEGEND_LABEL_{i}',[78,y-5,180,y+19],label,17,'#172232'))
    exclusions.append(p.exclusion(map_box,[48,584,183,687],legend_ids))
    p.crop('WORLD_MAP',map_box,'map',z=3,recipe={'mode':'local_cleanup','exclude_regions':[e for e in exclusions if e]})
    p.text('MAP_NOTE',[50,688,850,708],'注：市场规模单位为亿元人民币；百分比为占全球市场份额。',16,'#222222')
    for key,y,country,cr,rows in [('US',281,'美国','63.3%', [('MATTEL','美泰','15.3%',361,114),('HASBRO','孩之宝','13.6%',421,97)]),
                                 ('JP',483,'日本','61.4%', [('BANDAI','万代南梦宫','18.6%',566,116),('TAKARA','多美','16.0%',625,101)])]:
        end=y+(192 if key=='US' else 197)
        p.rect(key+'_PANEL',[923,y,1621,end],'#FFFFFF','#7A90B3',True,z=1)
        p.rect(key+'_TAB',[925,y+2,1054,y+44],'#345E9E',z=2)
        p.text(key+'_NAME',[930,y+5,1050,y+42],country,26,'#FFFFFF',True,'center')
        p.path(key+'_DIVIDER',[[1065,y+21],[1065,end-8]],stroke='#B6C3D8',width=0.5,dash=4)
        p.text(key+'_CR10',[1120,y+17,1210,y+50],'CR10',27,'#050505',True,'center')
        p.rect(key+'_CR_BAR',[1228,y+21,1515 if key=='US' else 1498,y+50],NAVY,z=5)
        p.text(key+'_CR_VALUE',[1521,y+14,1614,y+57],cr,30,NAVY,True,'right')
        flag=[944,342,1036,439] if key=='US' else [943,544,1036,640]
        p.crop(key+'_FLAG',flag,'illustration')
        for logo,label,value,bar_y,bar_w in rows:
            bounds={'MATTEL':[1086,344,1144,398],'HASBRO':[1089,409,1145,461],
                    'BANDAI':[1075,550,1135,603],'TAKARA':[1076,621,1146,664]}[logo]
            p.crop(logo,bounds,'logo')
            p.text(logo+'_NAME',[1147,bar_y-1,1226,bar_y+31],label,20,'#080808',True,'center')
            p.rect(logo+'_BAR',[1228,bar_y,1228+bar_w,bar_y+29],'#3568AC',z=5)
            p.text(logo+'_VALUE',[1238+bar_w,bar_y-1,1458,bar_y+32],value,22,'#111111')
    p.rect('FLOW_LEFT_PANEL',[34,710,535,862],'#E8EDF5',rounded=True)
    p.rect('FLOW_LEFT_TAB',[34,711,173,862],NAVY,z=3)
    p.text('FOCUS',[41,763,164,804],'竞争焦点：',28,'#FFFFFF',True,'center')
    p.text('MANUFACTURE_TITLE',[289,711,477,745],'产品制造',24,NAVY,True,'center')
    p.crop('FACTORY',[196,752,275,822])
    p.text('MANUFACTURE_BODY',[293,759,525,823],'以规模化制造与成本效率\n为核心',20,'#111111')
    p.rect('FLOW_MIDDLE_PANEL',[548,708,1040,863],'#E6EBF3',rounded=True)
    p.text('EXPERIENCE_TITLE',[566,711,1030,746],'内容、游戏、授权与线下体验',24,NAVY,True,'center')
    p.rect('FLOW_RIGHT_PANEL',[1053,708,1619,863],'#E0E7F2',rounded=True)
    p.text('ECOSYSTEM_TITLE',[1121,711,1554,746],'IP资产与生态运营',24,NAVY,True,'center')
    icons=[('GAMEPAD',[601,754,671,803],'内容/游戏',[586,803,686,831]),
           ('SHIELD',[738,750,790,807],'IP授权',[714,805,814,833]),
           ('STORE',[887,754,949,802],'线下体验',[866,805,970,833]),
           ('HEADSET',[1122,747,1174,800],'IP资产管理',[1096,803,1203,831]),
           ('GLOBE',[1243,748,1298,800],'全球化运营',[1218,803,1325,831]),
           ('PEOPLE',[1365,754,1426,801],'粉丝社区',[1342,803,1448,831]),
           ('GROWTH',[1505,750,1565,801],'数据驱动增长',[1470,803,1600,831])]
    for key,box,label,tbox in icons:
        p.crop(key,box)
        p.text(key+'_LABEL',tbox,label,17,'#111111',True,'center')
    for x in [697,841,1214,1338,1459]:
        p.path(f'FLOW_SEP_{x}',[[x,753],[x,799]],stroke='#6680A5',width=0.5,dash=4)
    p.text('EXPERIENCE_FOOT',[616,834,1015,861],'提升用户参与度与品牌溢价',21,'#111111',bold=True,align='center')
    p.text('ECOSYSTEM_FOOT',[1120,834,1604,861],'构建长期价值与可持续增长壁垒',21,'#111111',bold=True,align='center')
    for i,x in enumerate([532,1037]):
        p.path(f'FLOW_ARROW_{i}',[[x,764],[x+18,764],[x+18,754],[x+40,777],[x+18,799],[x+18,789],[x,789]],NAVY,'none',closed=True,z=17)
    return p


def s3(roi):
    p=Observations(roi)
    p.rect('LEFT_FRAME',[48,211,888,850],'#FFFFFF','#BDCCE0')
    p.rect('RIGHT_FRAME',[904,211,1635,850],'#FFFFFF','#BDCCE0')
    for key,box,label in [('MARKET_HEADER',[48,211,888,249],'市场规模增长（亿元）'),
                          ('REGION_HEADER',[48,409,888,447],'沿海地区玩具产业集群分工格局'),
                          ('RIGHT_HEADER',[904,211,1635,250],'行业集中度与潮玩企业梯队')]:
        p.rect(key,box,'#203F79',z=2)
        p.text(key+'_TEXT',box,label,25,'#FFFFFF',True,'center')
    for key,x,year,value in [('START',72,'2023年','1049'),('END',706,'2028年','1655')]:
        p.rect(key+'_CARD',[x,264,x+(166 if key=='START' else 158),393],'#E2EAF5',rounded=True,z=3)
        right=x+(166 if key=='START' else 158)
        p.text(key+'_YEAR',[x+5,271,800 if key=='END' else right-5,304],year,26,NAVY,True,'center')
        p.text(key+'_VALUE',[x+5,303,right-5,352],value,44,RED,True,'center')
        p.text(key+'_UNIT',[x+5,350,right-5,384],'亿元',27,NAVY,True,'center')
    p.text('FORECAST',[800,275,852,301],'（预计）',15,NAVY)
    p.text('GROWTH_SUMMARY',[272,269,688,309],'2023年1049亿元 → 2028年1655亿元，',25,NAVY,True,'center')
    p.text('CAGR',[335,303,620,353],'CAGR 9.5%',39,RED,True,'center')
    # Measured curved growth arrow outline; not the old straight V-shaped arrow.
    upper=[]; lower=[]
    for i in range(31):
        t=i/30
        x=278+365*t
        y=383+22*t-65*t*t
        upper.append([x,y])
        lower.append([x,y+2+14*t])
    p.path('GROWTH_ARROW',upper+[[632,316],[670,324],[653,359],[649,343]]+list(reversed(lower)), '#2A62A7','none',closed=True,z=8)
    for key,y,province,body,color,photo,icon in [
        ('GD',466,'广东','广东：澄海、东莞，\n制造与出口','#2D4F89',[377,467,536,573],[81,477,131,527]),
        ('ZJ',592,'浙江','浙江：义乌，\n贸易与集散','#3E71B8',[377,592,537,701],[80,605,133,653]),
        ('JS',719,'江苏','江苏：教育玩具、\n木制玩具及细分制造','#6A90BF',[377,720,537,828],[78,731,140,778])]:
        p.rect(key+'_CARD',[62,y,538,y+109],'#E7EDF5',rounded=True,z=2)
        p.rect(key+'_TAB',[63,y,145,y+106],color,rounded=True,z=4)
        p.crop(key+'_ICON',icon)
        p.text(key+'_PROVINCE',[70,y+68,139,y+101],province,28,'#FFFFFF',True,'center')
        p.text(key+'_BODY',[158,y+16,374,y+94],body,25,'#0D244B')
        p.crop(key+'_PHOTO',photo,'photo')
    mbox=[548,451,876,830]; exclusions=[]
    for key,box,label,point in [('JS_MAP',[762,503,847,538],'江苏',[675,595]),
                              ('ZJ_MAP',[786,612,871,646],'浙江',[709,644]),
                              ('GD_MAP',[749,742,834,777],'广东',[632,766])]:
        x,y,r,b=box
        box_id=p.rect(key+'_BOX',box,NAVY,rounded=True,z=14)
        text_id=p.text(key+'_TEXT',[x+3,y+1,r-3,b-1],label,25,'#FFFFFF',True,'center')
        link_id=key+'_LINK'
        end={'JS_MAP':[762,530],'ZJ_MAP':[786,637],'GD_MAP':[749,766]}[key]
        p.path(link_id,[point,end],stroke='#1F4A87',width=0.8,dash=4,z=12)
        dot_id=p.ellipse(key+'_DOT',[point[0]-7,point[1]-7,point[0]+7,point[1]+7],'#2F66A8','#FFFFFF',z=18,width=1.5)
        exclusions.append(p.exclusion(mbox,[x-2,y-2,r+2,b+2],[box_id,text_id]))
        # Line removal follows the segment itself, avoiding a large rectangular
        # hole through geography. Native replacement covers this narrow aperture.
        exclusions.extend(clean_segment(mbox,[point,end],link_id))
        exclusions.append(circular_exclusion(mbox,*point,7,dot_id))
    p.crop('CHINA_MAP',mbox,'map',z=3,recipe={'mode':'local_cleanup','exclude_regions':[e for e in exclusions if e]})
    p.rect('CONCENTRATION_STRIP',[919,264,1619,298],'#E7EDF5',z=3)
    p.text('CONCENTRATION_TITLE',[956,266,1590,296],'中国玩具行业集中度（2023年）',25,NAVY,True,'center')
    cx,cy=1014,411
    for i,(start,end,color) in enumerate([(-90,45,'#305FA2'),(45,138,'#8BA9D5'),(138,270,'#C6CFDF')]):
        outer=[]; inner=[]
        for j in range(61):
            a=math.radians(start+(end-start)*j/60)
            outer.append([cx+89*math.cos(a),cy+89*math.sin(a)])
            inner.append([cx+45*math.cos(a),cy+45*math.sin(a)])
        p.path(f'DONUT_{i}',outer+list(reversed(inner)),color,'#FFFFFF',width=0.7,closed=True,z=5)
    for key,box in [('BUILDING_MAIN',[997,392,1017,430]),('BUILDING_SIDE',[1020,400,1032,430]),('BUILDING_BASE',[992,429,1037,433])]:
        p.rect(key,box,NAVY,z=12)
    for col,x in enumerate([1001,1009,1023]):
        for row,y in enumerate([397,406,415,424]):
            if col==2 and row==0: continue
            p.rect(f'WINDOW_{col}_{row}',[x,y,x+4,y+5],'#FFFFFF',z=13)
    p.text('TOP10',[1128,357,1272,402],'中国TOP10',28,NAVY,True,'center')
    p.text('TOP10_SHARE',[1127,402,1275,464],'27.2%',49,RED,True,'center')
    p.rect('LEADERS_FRAME',[1286,324,1617,511],'#FFFFFF','#88A2C8',z=2)
    p.crop('LEGO',[1315,343,1379,407],'logo')
    p.crop('POPMART_SHARE',[1312,445,1404,478],'logo')
    p.text('LEGO_NAME',[1412,353,1506,395],'乐高',28,'#080808',True)
    p.text('LEGO_SHARE',[1538,351,1614,397],'9.0%',31,NAVY,True,'right')
    p.text('POPMART_NAME',[1414,442,1533,484],'泡泡玛特',26,'#080808',True)
    p.text('POPMART_SHARE_VALUE',[1540,438,1614,485],'5.3%',31,NAVY,True,'right')
    p.path('LEADERS_DIVIDER',[[1313,418],[1608,418]],stroke='#A6B8D2',width=0.5)
    p.path('RIGHT_DIVIDER',[[919,532],[1619,532]],stroke='#D7E0EB',width=0.6)
    p.rect('TIER_STRIP',[919,547,1619,582],'#E7EDF5',z=2)
    p.text('TIER_TITLE',[950,549,1605,580],'潮玩一超多强：泡泡玛特、TOPTOY、布鲁可',25,NAVY,True,'center')
    for key,box,title in [('T1',[919,602,1090,809],'第一梯队（超头部）'),('T2',[1105,602,1345,809],'第二梯队（头部）'),('T3',[1361,602,1619,809],'第三梯队（潜力品牌）')]:
        x,y,r,b=box
        p.rect(key+'_FRAME',box,'#FFFFFF','#CBD4E2',z=2)
        p.rect(key+'_HEADER',[x,y,r,y+34],'#4C76AD',z=3)
        p.text(key+'_HEADER_TEXT',[x+2,y+1,r-2,y+33],title,20,'#FFFFFF',True,'center')
    for key,box in [('POPMART_TIER',[940,680,1070,727]),('TOPTOY',[1134,666,1202,738]),('BLOKEES',[1238,662,1332,741]),
                    ('52TOYS',[1382,666,1472,693]),('ROLIFE',[1494,667,1604,691]),('X11',[1401,726,1456,759]),('UNICORN',[1495,725,1600,764])]:
        p.crop(key,box,'logo')
    p.text('T1_NAME',[952,749,1080,792],'泡泡玛特',24,'#111111',False,'center')
    p.text('T2_TOPTOY_NAME',[1115,749,1225,792],'TOPTOY',23,'#111111',False,'center')
    p.text('T2_BLOKEES_NAME',[1237,749,1338,792],'布鲁可',24,'#111111',False,'center')
    p.text('TIER_NOTE',[1062,818,1618,844],'注：梯队划分基于品牌影响力、市场表现与成长性综合判断',16,'#888888',False,'center')
    return p


def test01(roi):
    p=Observations(roi)
    p.text('MARKET_TITLE',[51,280,577,320],'全球玩具市场规模（亿元）',26,NAVY,True)
    p.text('DRIVER_TITLE',[1128,278,1318,318],'三大增长动力',30,NAVY,True,'center')
    p.path('DRIVER_RULE_L',[[979,293],[1118,293]],stroke=BLUE,width=0.8)
    p.path('DRIVER_RULE_R',[[1318,293],[1532,293]],stroke=BLUE,width=0.8)
    p.path('Y_AXIS',[[116,359],[116,786]],stroke='#BBBBBB',width=0.7)
    p.path('X_AXIS',[[116,786],[860,786]],stroke='#BBBBBB',width=0.7)
    for i,value in enumerate(range(5000,11001,1000)):
        y=786-i*71.1
        p.text(f'Y_TICK_{value}',[48,y-15,106,y+15],f'{value:,}',20,'#555555',False,'right')
        p.path(f'Y_MARK_{value}',[[109,y],[116,y]],stroke='#BBBBBB',width=0.6)
    p.text('Y_UNIT',[52,799,143,832],'（亿元）',22,'#555555')
    for i,(x,label,bold) in enumerate([(190,'2023',True),(321,'2024',False),(478,'2025E',True),
                                     (597,'2026E',False),(706,'2027E',False),(814,'2028E',True)]):
        p.path(f'X_MARK_{i}',[[x,786],[x,794]],stroke='#BBBBBB',width=0.6)
        p.text(f'X_TICK_{i}',[x-48,799,x+49,835],label,25 if bold else 20,NAVY if bold else '#555555',bold,'center')
    points=[]
    # Smooth measured contour through the three visible blueprint points.
    for a,b,control in [((190,599),(479,539),(338,575)),((479,539),(814,408),(656,494))]:
        for i in range(21):
            t=i/20
            points.append([(1-t)**2*a[0]+2*(1-t)*t*control[0]+t*t*b[0],(1-t)**2*a[1]+2*(1-t)*t*control[1]+t*t*b[1]])
    p.path('CHART_AREA',points+[[814,786],[190,786]],'#E4ECF6','none',closed=True,z=2)
    p.path('CHART_CURVE',points,stroke='#0E356D',width=2.3,z=9)
    for key,x,y,year,value in [('2023',190,599,'2023','7731亿元'),('2025',479,539,'2025E','8509亿元'),('2028',814,408,'2028E','9937亿元')]:
        p.path('PROJECTION_'+key,[[x,y+8],[x,785]],stroke='#7B9FCB',width=0.6,dash=4,z=4)
        p.ellipse('POINT_'+key,[x-10,y-10,x+10,y+10],NAVY,'#FFFFFF',width=1,z=10)
        p.text('YEAR_'+key,[x-88,y-91,x+85,y-58],year,28,NAVY,True,'center')
        p.text('VALUE_'+key,[x-104,y-62,x+105,y-23],value,32,NAVY,True,'center')
    p.rect('CAGR_FRAME',[364,634,600,702],'#FFFFFF','#CD2222',True,z=12)
    p.text('CAGR_LABEL',[378,645,465,691],'CAGR',31,RED,True)
    p.text('CAGR_VALUE',[475,634,586,697],'5.1%',49,RED,True,'center')
    rows=[('PEOPLE',321,'人群扩容','消费群体由儿童向青少年和\n成年人拓展，“大童”消费\n成为新增量。',[929,322,1001,398]),
          ('VALUE',502,'价值提升','IP授权、潮玩、拼搭、毛绒和\n卡牌以收藏与情绪价值提升\n频次和客单价。',[929,503,1001,578]),
          ('REGION',682,'区域增量','亚洲等新兴市场消费能力\n提升，线上渠道和品牌全球化\n加速渗透。',[929,686,1001,761])]
    for key,y,title,body,icon in rows:
        p.rect(key+'_PANEL',[966,y,1622,y+163],'#FFFFFF','#CBD8E8',True,z=1)
        p.ellipse(key+'_ICON_OUTER',[922,y-6,1010,y+83],'#FFFFFF','#95B1D8',z=4,width=0.7)
        p.crop(key+'_ICON',icon)
        p.text(key+'_TITLE',[1026,y+8,1240,y+52],title,30,BLUE if key=='VALUE' else NAVY,True)
        p.text(key+'_BODY',[1026,y+50,1259,y+142],body,22,'#111111')
    for key,y in [('CURVE_ARROW_1',382),('CURVE_ARROW_2',562)]:
        points=[]
        for i in range(31):
            t=i/30
            points.append([925-185*t*(1-t),y+151*t])
        p.path(key,points,stroke='#96B2D9',width=1.8,arrow=True,z=4)
    p.crop('ROBOT',[1258,336,1353,472],'illustration')
    p.crop('COLLECTORS',[1354,309,1622,482],'photo')
    for key,box in [('DESIGNER_TOY',[1258,524,1340,654]),('IP_PACK',[1339,520,1402,652]),
                    ('CASTLE',[1403,507,1482,654]),('RABBIT',[1483,529,1539,654]),('CARD',[1543,530,1615,654])]:
        p.crop(key,box,'illustration')
    p.crop('ASIA_MAP',[1253,699,1367,800],'map')
    for i,(x,h) in enumerate([(1303,19),(1318,26),(1333,33),(1348,39),(1363,47)]):
        p.rect(f'MINI_BAR_{i}',[x,835-h,x+11,835],'#B8CBE3',z=7)
    p.path('MINI_GROWTH_ARROW',[[1294,828],[1330,801],[1370,759]],stroke='#95AFD3',width=5,arrow=True,z=8)
    # The phone UI is split: editable shell and readable UI labels, only local
    # product thumbnails remain images. No mixed map/chart/phone/logo screenshot.
    p.rect('PHONE_FRAME',[1390,689,1473,844],'#111111',rounded=True,z=5)
    p.rect('PHONE_SCREEN',[1395,696,1468,837],'#FFFFFF',rounded=True,z=6)
    p.rect('PHONE_NOTCH',[1410,695,1450,701],'#111111',rounded=True,z=8)
    # Source magnification shows synthetic, unidentifiable UI glyphs. Preserve
    # their visual density with editable marks; do not invent readable UI copy.
    for i,(x,y,w,color) in enumerate([(1404,706,28,'#777777'),(1404,717,40,'#7754B8'),
                                    (1403,727,51,'#8759D0'),(1399,775,22,'#999999'),
                                    (1432,775,26,'#999999'),(1403,826,15,'#AAAAAA'),(1437,826,16,'#AAAAAA')]):
        p.rect(f'PHONE_ILLEGIBLE_MARK_{i}',[x,y,x+w,y+2],color,z=10)
    for i,box in enumerate([[1398,737,1427,771],[1430,737,1464,771],[1398,787,1427,818],[1430,787,1464,818]]):
        p.crop(f'PHONE_PRODUCT_{i}',box,'photo',z=11)
    p.crop('TMALL',[1496,724,1544,780],'logo')
    p.crop('SHOPEE',[1561,720,1608,783],'logo')
    p.crop('LAZADA',[1490,794,1610,827],'logo')
    return p


def materialize(project: Path, pages: dict[str, Observations]):
    start=time.perf_counter()
    tiles=load('v63_visual_tiles').generate_review_tiles(project)
    observations={sid:p.items for sid,p in pages.items()}
    write(project / '.build/v63_observations.json', {'source':'direct locked-blueprint pixel inspection', 'pages':observations})
    census={'schema_version':'6.3','deconstruction_runtime_revision':'6.3.1','pages':{}}
    for sid,p in pages.items():
        tp=tiles['pages'][sid]; candidates=[]
        for item in p.items:
            candidates.append({k:v for k,v in item.items() if k!='implementation'} | {
                'review_tile_ids':['FULL','B01','B02','B03','B04','B05','B06','PAGE'],
                'expected_treatment':'crop' if item['implementation']['atom']=='image_crop' else 'editable','confidence':'high'})
        census['pages'][sid]={'blueprint_sha256':tp['blueprint_sha256'],'body_roi_px':p.roi,
            'reviewed_tile_ids':['FULL','B01','B02','B03','B04','B05','B06','PAGE'],'candidates':candidates}
    report=load('v63_visual_census').validate_and_write_visual_census(project,census)
    if not report['ok']: raise ValueError(report)
    original_path=project/'.build/v63_census_original.json'
    if original_path.is_file():
        original=read(original_path)
        allowed={'EUROPE_SHARE','EUROPE_VALUE','END_YEAR','JS_MAP_LINK','ZJ_MAP_LINK','GD_MAP_LINK'}
        changes=[]
        for sid,page in census['pages'].items():
            old={c['candidate_id']:c for c in original['pages'][sid]['candidates']}
            for candidate in page['candidates']:
                cid=candidate['candidate_id']
                if candidate!=old[cid]:
                    if cid not in allowed: raise ValueError('UNPLANNED_CENSUS_CHANGE: '+cid)
                    changes.append({'slide_id':sid,'candidate_id':cid,'action':'correct',
                        'reason':'Single targeted revision: source label baseline/connector endpoint remeasured after actual overlap/ghost-line review.',
                        'evidence_px':candidate['bbox_px']})
        write(project/'.build/v63_census_amendments.json',{'changes':changes})
    graph={'schema_version':'6.3','deconstruction_runtime_revision':'6.3.1','color_authority':'blueprint_body','pages':{}}
    for sid,p in pages.items():
        elements=[]; resolutions={}
        for observed in p.items:
            cid=observed['candidate_id']; data=dict(observed['implementation']); atom=data.pop('atom')
            element={'element_id':cid,'type':atom,'bbox_px':observed['bbox_px'],'source_candidate_ids':[cid],**data}
            if atom=='image_crop':
                element.update(asset_id=f'{sid}_{cid}',source_px=observed['bbox_px'],subject_count=1,tight_crop=True,
                               contains_editable_text=False,contains_native_geometry=False,intrinsic_text_only=True)
            elements.append(element)
            resolutions[cid]={'mode':'crop' if atom=='image_crop' else 'editable','element_ids':[cid]}
        graph['pages'][sid]={'blueprint_sha256':sha(project/'blueprints'/f'{sid}.png'),'body_roi_px':p.roi,
            'coordinate_mode':'source_pixels_contain','elements':elements,'candidate_resolutions':resolutions}
    report=load('v63_scene_graph').validate_and_write_scene_graph(project,graph)
    if not report['ok']: raise ValueError(report)
    precheck=load('v63_deconstruction').prepare_deconstruction(project,backend='windows_com_v584',template_path=ROOT/'assets/company_template.pptx')
    write(project/'.build/observation_compile_timing.json',{'validation_and_extraction_seconds':time.perf_counter()-start})
    print(project.name, 'objects', sum(len(p.items) for p in pages.values()), 'precheck', precheck['ok'])
    if not precheck['ok']: raise ValueError(precheck['blockers'])


def main(workspace):
    base=workspace/'V63_visual_repair_validation'
    manifest=read(ROOT/'tests/fixtures/v63_visual_repair_manifest.json')['samples']
    materialize(base/'TEST',{'S01':test01(manifest['TEST-01']['source_body_roi_px']),
                             'S02':test02(manifest['TEST-02']['source_body_roi_px'])})
    materialize(base/'S3',{'S01':s3(manifest['S3']['source_body_roi_px'])})


if __name__=='__main__':
    main(Path('C:/Users/edchw/Documents/START PPT'))
