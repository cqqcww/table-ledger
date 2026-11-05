"""Seeded layout families; reference answers are computed before rendering."""
# SPDX-License-Identifier: AGPL-3.0-only
from _common import arguments, finalize
from pathlib import Path
import json
import random
import hashlib
from decimal import Decimal, ROUND_HALF_UP
from PIL import Image,ImageDraw,ImageFont,ImageFilter
import pymupdf

ROOT=Path()
FONT=''
FAMILIES=['finance_merged','sales_plain','purchase_merged','quality_weak',
          'logistics_wide','statistics_small','receivables_negative','inventory_unit',
          'rotated_scan','multipage_statement','footnote_noise','multilevel_statement']
HOLDOUT={'quality_weak','receivables_negative','multipage_statement','multilevel_statement'}
ORDERS=[(0,1,2,3,4),(1,0,4,2,3),(4,0,1,2,3),(4,0,2,1,3),
        (0,3,4,2,1),(1,2,0,4,3),(3,4,1,0,2),(4,3,1,2,0),
        (1,4,0,3,2),(2,3,0,4,1),(3,2,1,4,0),(3,1,2,4,0)]


def build():
    (ROOT/'files').mkdir(parents=True,exist_ok=True)
    docs=[];questions=[]
    for family_index,family in enumerate(FAMILIES):
        for variant in range(3):
            rng=random.Random(84673+family_index*100+variant)
            labels=[f'产品{x}' for x in '甲乙丙丁戊己']
            current=[rng.randrange(10000,90000)/100 for _ in labels]
            previous=[rng.randrange(10000,90000)/100 for _ in labels]
            if family_index==6: current[2]=-current[2]
            unit='万元' if family_index==7 else '元'
            notes=['00123','','待复核','已确认','00007','正常']
            merged=family_index in (0,2,5,7,11)
            grid=([['项目','销售额',None,'数量','备注'],[None,'本期','上期',None,None]] if merged else
                  [['项目','本期销售额','上期销售额','数量','备注']])
            h=len(grid)
            merges=([{'row':0,'col':0,'rowspan':2,'colspan':1},
                     {'row':0,'col':1,'rowspan':1,'colspan':2},
                     {'row':0,'col':3,'rowspan':2,'colspan':1},
                     {'row':0,'col':4,'rowspan':2,'colspan':1}] if merged else [])
            def money(x): return f'({abs(x):,.2f})' if x<0 else f'{x:,.2f}'
            grid += [[l,money(a),money(b),str(rng.randrange(5,99)),n] for l,a,b,n in zip(labels,current,previous,notes)]
            total=sum(Decimal(str(v)) for v in current)
            grid.append(['合计',f'{total:,.2f}',f'{sum(Decimal(str(v)) for v in previous):,.2f}','', ''])
            merged_by={(m['row'],m['col']):m for m in merges}
            cells=[{'text':value,**merged_by.get((r,c),{'row':r,'col':c,'rowspan':1,'colspan':1})}
                   for r,row in enumerate(grid) for c,value in enumerate(row) if value is not None]
            # Each held-out family has a distinct physical column layout, not just a new filename.
            order=ORDERS[family_index]; inverse={old:new for new,old in enumerate(order)}
            remapped=[]
            for cell in cells:
                columns=[inverse[c] for c in range(cell['col'],cell['col']+cell['colspan'])]
                assert max(columns)-min(columns)+1==len(columns)
                remapped.append({**cell,'col':min(columns)})
            cells=sorted(remapped,key=lambda c:(c['row'],c['col']))
            grid=[[None]*5 for _ in grid]
            for cell in cells:grid[cell['row']][cell['col']]=cell['text']
            merges=[{k:v for k,v in cell.items() if k!='text'} for cell in cells if cell['rowspan']>1 or cell['colspan']>1]
            title=f'{family} 业务明细表'
            widths=[[240,240,240,160,240][i] for i in order]; rowheight=82
            x0,y0=110,190
            canvas=(1580,1280) if family_index not in (4,10) else (2400,1750)
            font=ImageFont.truetype(FONT,28);small=ImageFont.truetype(FONT,24)
            def render(row_start=0,row_end=None,repeat=False):
                im=Image.new('RGB',canvas,'white');d=ImageDraw.Draw(im)
                d.text((x0,55),title,font=font,fill='black');d.text((x0,110),'金额单位：'+unit+'；统计期：2025年',font=small,fill='black')
                xs=[x0]
                for w in widths:xs.append(xs[-1]+w)
                indices=list(range(row_start,len(grid) if row_end is None else row_end))
                if repeat:indices=list(range(h))+indices
                pos={r:i for i,r in enumerate(indices)}
                for cell in cells:
                    r,c=cell['row'],cell['col']
                    if r not in pos:continue
                    y=y0+pos[r]*rowheight
                    box=(xs[c],y,xs[c+cell['colspan']],y+cell['rowspan']*rowheight)
                    d.rectangle(box,fill='#e5eaf0' if r<h else 'white',outline='#b5b5b5' if family_index==3 else '#333333',width=1 if family_index==3 else 2)
                    d.text((box[0]+12,box[1]+20),cell['text'],font=font,fill='black')
                foot='注：合计仅汇总明细；备注中的编号应保留前导零。'
                d.text((x0,y0+len(indices)*rowheight+40),foot,font=small,fill='black')
                if family_index==10:
                    d.text((x0,y0+len(indices)*rowheight+100),'附注：另有未纳入本表的订单 999999 元。',font=font,fill='black')
                if family_index==5:
                    im=im.resize((790,640)).filter(ImageFilter.GaussianBlur(.25))
                if family_index==8:im=im.rotate(90,expand=True)
                return im
            name=f'{family}-{variant}.png'
            if family_index==9:
                name=f'{family}-{variant}.pdf'
                pdf=pymupdf.open()
                for i,im in enumerate((render(0,h+3),render(h+3,repeat=True))):
                    import io
                    buf=io.BytesIO();im.save(buf,'PNG');page=pdf.new_page(width=canvas[0]/2,height=canvas[1]/2)
                    page.insert_image(page.rect,stream=buf.getvalue())
                pdf.save(ROOT/'files'/name);pdf.close()
            else:render().save(ROOT/'files'/name)
            split='holdout' if family in HOLDOUT else 'dev'
            docid=f'{family}-{variant}'
            docs.append({'document_id':docid,'file_name':name,'family':family,'split':split,
                         'layout_signature':{'column_order':order,'header_rows':h},
                         'source':{'rows':grid,'merges':merges,'unit':unit,'row_count':len(grid),'col_count':5},
                         'sha256':hashlib.sha256((ROOT/'files'/name).read_bytes()).hexdigest()})
            growth=((Decimal(str(current[0]))-Decimal(str(previous[0])))/Decimal(str(previous[0]))*100).quantize(Decimal('.01'),rounding=ROUND_HALF_UP)
            qspec=[('extract','请提取产品甲的本期销售额，只返回数值。','number',str(current[0])),
                   ('extract','请依次提取产品乙和产品丙的本期销售额。','json_array',[str(current[1]),str(current[2])]),
                   ('extract','请依次提取产品甲、产品乙、产品戊的备注，保留前导零，空格填空字符串。','json_array',[notes[0],notes[1],notes[4]]),
                   ('thinking',f'请计算六个产品的本期销售额之和，结果单位为元，不要重复计算合计行。','number',str(total*10000 if unit=='万元' else total)),
                   ('thinking','请计算产品甲本期销售额较上期的增长率，用百分数数值表示，保留2位小数，不带百分号。','number',str(growth)),
                   ('structure','请恢复表格前1行和前1列的结构，保留完整表格行列数；跨页重复表头只计一次。','json',
                    {'row_count':len(grid),'col_count':5,'cells':[c for c in cells if c['row']==0 or c['col']==0]})]
            for i,(typ,question,fmt,answer) in enumerate(qspec):
                questions.append({'id':f'{docid}-q{i+1}','file_name':name,'family':family,'split':split,
                     'question_type':typ,'question':question,'table_hint':title,'answer_format':fmt,'expected':answer})
    payload={'schema_version':1,'seed':84673,'description':'独立程序生成，真值来自生成前的逻辑表格。',
             'split_method':'按语义/版式模板族隔离，24文档144题开发；12文档72题保留。该划分是历史元数据，当前用于回归。',
             'documents':docs,'questions':questions}
    (ROOT/'benchmark.json').write_text(json.dumps(payload,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({'documents':len(docs),'questions':len(questions),'dev':sum(q['split']=='dev' for q in questions),
                      'holdout':sum(q['split']=='holdout' for q in questions)},ensure_ascii=False))


if __name__=='__main__':
    args=arguments();ROOT=args.output;FONT=str(args.font)
    build();finalize(ROOT, 'synthetic_v1')
