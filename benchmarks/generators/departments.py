"""Seeded department tables with merged labels, units and explicit blanks."""
# SPDX-License-Identifier: AGPL-3.0-only
from pathlib import Path
from decimal import Decimal
import hashlib
import json
import random
from PIL import Image, ImageDraw, ImageFont
from _common import arguments, finalize


def build(root, font_path):
    root.mkdir(parents=True,exist_ok=True)
    (root/'files').mkdir(exist_ok=True);docs=[];qs=[]
    font=ImageFont.truetype(str(font_path),28)
    small=ImageFont.truetype(str(font_path),25)
    for v in range(12):
        rng=random.Random(730031+v);unit='万元' if v%2==0 else '元';scale=10000 if unit=='万元' else 1
        amounts=[Decimal(rng.randrange(1200,97000))/100 for _ in range(6)];amounts[1]=-amounts[1]
        old=[Decimal(rng.randrange(1200,97000))/100 for _ in range(6)]
        notes=[f'{rng.randrange(10,99):05d}','','-','0',f'{rng.randrange(10,99):05d}','已核']
        departments=['研发一部','运维二部'];projects=['常规服务','专项服务','其他服务']
        grid=[['部门','项目','本期',None,'上期','备注'],[None,None,'金额','数量','金额',None]]
        merges=[{'row':0,'col':c,'rowspan':2,'colspan':1} for c in (0,1,5)]+[{'row':0,'col':2,'rowspan':1,'colspan':2}]
        def money(x):return f'({abs(x):,.2f})' if x<0 else f'{x:,.2f}'
        for group in range(2):
            start=len(grid);merges.append({'row':start,'col':0,'rowspan':3,'colspan':1})
            for j in range(3):
                i=group*3+j
                grid.append([departments[group] if j==0 else None,projects[j],money(amounts[i]),str(rng.randrange(1,50)),money(old[i]),notes[i]])
            grid.append([departments[group],'小计',money(sum(amounts[group*3:group*3+3])),'',money(sum(old[group*3:group*3+3])),''])
        grid.append(['全公司','合计',money(sum(amounts)),'',money(sum(old)),''])
        merged={(m['row'],m['col']):m for m in merges}
        cells=[{'text':value,**merged.get((r,c),{'row':r,'col':c,'rowspan':1,'colspan':1})} for r,row in enumerate(grid) for c,value in enumerate(row) if value is not None]
        order=(0,1,2,3,4,5) if v%3==0 else (5,4,0,1,2,3) if v%3==1 else (1,2,3,5,0,4)
        inv={c:i for i,c in enumerate(order)};width=[180,220,260,160,260,180];xs=[65]
        for c in order:xs.append(xs[-1]+width[c])
        im=Image.new('RGB',(1500,1150),'white');draw=ImageDraw.Draw(im)
        title='部门服务结算明细表'
        draw.text((65,35),title,font=font,fill='black');draw.text((65,90),'金额单位：'+unit+'；本期2026年，上期2025年。',font=small,fill='black')
        for cell in cells:
            cols=sorted(inv[c] for c in range(cell['col'],cell['col']+cell['colspan']))
            assert cols[-1]-cols[0]+1==len(cols)
            x0,x1=xs[cols[0]],xs[cols[-1]+1];y0=160+cell['row']*72;y1=y0+cell['rowspan']*72
            draw.rectangle((x0,y0,x1,y1),fill='#e7edf3' if cell['row']<2 else 'white',outline='#999999' if v%4==0 else '#333333',width=1 if v%4==0 else 2)
            draw.text((x0+9,y0+20),cell['text'],font=font,fill='black')
        draw.text((65,995),'附注：未纳入本表的预算调整金额为9999.99；不要并入明细。',font=small,fill='black')
        draw.text((65,1040),'备注中的空白、数字0和横杠分别保留；小计和合计不是明细。',font=small,fill='black')
        if v%4==2:im=im.resize((1050,805),Image.Resampling.LANCZOS)
        if v%4==3:im=im.rotate(90,expand=True)
        name=f'cn-review-{v:02d}.png';path=root/'files'/name;im.save(path)
        sha=hashlib.sha256(path.read_bytes()).hexdigest()
        docs.append({'file_name':name,'sha256':sha,'source':{'rows':grid,'merges':merges,'unit':unit,'column_order':order},'seed':730031+v})
        specs=[('extract','请依次提取运维二部专项服务、研发一部常规服务的本期金额，保留表中金额单位的数值。','json_array',[str(amounts[4]),str(amounts[0])]),
          ('extract','请依次提取研发一部专项服务、运维二部常规服务、研发一部其他服务的备注；空白填空字符串。','json_array',[notes[1],notes[3],notes[2]]),
          ('thinking','请计算研发一部三项明细本期金额之和，结果以元表示，不重复计算小计、合计和附注。','number',str(sum(amounts[:3])*scale)),
          ('thinking','请计算运维二部常规服务本期金额减上期金额的差额，保持表中金额单位，只返回数值。','number',str(amounts[3]-old[3])),
          ('extract','请按表格顺序列出运维二部的全部明细项目名称，不包含小计和合计。','json_array',projects)]
        for i,(typ,q,fmt,gold) in enumerate(specs):
            qs.append({'id':f'cn-review-{v:02d}-{i}','file_name':name,'question':q,'question_type':typ,'answer_format':fmt,'table_hint':title,
               'expected':gold,'split':'holdout','document_group':name,'image_sha256':sha})
    payload={'version':'chinese-diagnostics-v1','description':'Independent program-generated source truth; New merged department labels, repeated leaf headers, negative numbers, units, blanks, subtotals, footnotes, reordered columns and rotated/small pages.',
       'limitations':'60 questions across12 documents share one generator and question family. Diagnostic regression, not real-document blind generalization. Source tables retained for scoring/audit only.',
       'documents':docs,'questions':qs}
    (root/'benchmark.json').write_text(json.dumps(payload,ensure_ascii=False,indent=2));print('chinese_questions',len(qs),flush=True)


if __name__=='__main__':
    args=arguments();build(args.output,args.font);finalize(args.output, 'chinese_diagnostics_v1')
