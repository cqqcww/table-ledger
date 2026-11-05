"""Render original layout and partial-structure diagnostic suites."""
# SPDX-License-Identifier: AGPL-3.0-only
from pathlib import Path
import argparse
import hashlib
import io
import json
import random
import sys
from PIL import Image, ImageDraw, ImageFont
import pymupdf

def atomic_json(path, value):
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n')


def build(root, *, font_path, seed_start=518231, count=24, dev_count=18, prefix='layout'):
    manifest=root/'benchmark.json'
    if manifest.exists():
        print('Existing frozen layout dataset');return
    (root/'files').mkdir(parents=True,exist_ok=True)
    font=ImageFont.truetype(str(font_path),26)
    small=ImageFont.truetype(str(font_path),22)
    documents=[];questions=[]
    for v in range(count):
        rng=random.Random(seed_start+v);cols=rng.randrange(4,13);headers=1+v%3;body=rng.randrange(7,27)
        rows=headers+body+1;cells=[]
        def cell(r,c,raw,rs=1,cs=1):cells.append({'row':r,'col':c,'rowspan':rs,'colspan':cs,'raw':str(raw)})
        names=['客户','数量','金额','成本','税额','差额','收入','利润','折扣','单价','备注','预算']
        rng.shuffle(names)
        if headers==1:
            for c in range(cols):cell(0,c,'项目' if c==0 else names[c])
        else:
            cell(0,0,'业务项目',headers,1)
            if headers==3:cell(0,1,'经营数据',1,cols-1)
            at=1;group=0
            while at<cols:
                width=min(rng.randrange(2,4),cols-at)
                cell(headers-2,at,['本期','上期','预算','调整','其他','附列'][group],1,width)
                at+=width;group+=1
            for c in range(1,cols):cell(headers-1,c,names[c])
        labels=['华东渠道','华南服务','北方业务','境外项目','总部业务','区域团队']
        for i in range(body):
            if v%4==1:
                if i%3==0:cell(headers+i,0,labels[(i//3)%len(labels)],min(3,body-i),1)
            else:cell(headers+i,0,labels[i%len(labels)])
            for c in range(1,cols):
                raw='' if (i+c+v)%17==0 else str(rng.randrange(10,90000)/100)
                cell(headers+i,c,raw)
        cell(rows-1,0,'合计')
        for c in range(1,cols):cell(rows-1,c,str(rng.randrange(10000,90000)/100))
        title='业务汇总明细表';x0=45;y0=145;rh=48 if v%5 else 38;cw=130
        width=x0*2+cw*cols
        chunks=[list(range(rows))]
        # Split at a body group boundary, so a real merge is not cut in two.
        if v%6==5:
            mid=headers+max(3,(body//2)//3*3)
            chunks=[list(range(mid)),list(range(headers))+list(range(mid,rows))]
        images=[];render_map=[]
        for page,indices in enumerate(chunks,1):
            height=y0+len(indices)*rh+120
            im=Image.new('RGB',(width,height),'white');d=ImageDraw.Draw(im)
            d.text((x0,30),title+('（续表）' if page>1 else ''),font=font,fill='black')
            d.text((x0,85),'统计期：2026年；金额单位：元',font=small,fill='black')
            positions={r:i for i,r in enumerate(indices)}
            for ce in cells:
                r,c=ce['row'],ce['col']
                if r not in positions:continue
                x=x0+c*cw;y=y0+positions[r]*rh
                box=[x,y,x+cw*ce['colspan'],y+rh*ce['rowspan']]
                d.rectangle(box,fill='#edf0f3' if r<headers else 'white',outline='#bbbbbb' if v%5==2 else '#444444',width=1)
                d.text((x+7,y+9),ce['raw'],font=small,fill='black')
            d.text((x0,height-65),'附注：另列说明不属于表格数据行。',font=small,fill='black')
            if v%8==7:im=im.rotate(90,expand=True)
            images.append(im);render_map.append({'page':page,'logical_rows':indices})
        name=f'{prefix}-{v:02d}';filename=name+('.pdf' if len(images)>1 else '.png')
        target=root/'files'/filename
        if len(images)==1:images[0].save(target)
        else:
            pdf=pymupdf.open()
            for im in images:
                buf=io.BytesIO();im.save(buf,'PNG');p=pdf.new_page(width=im.width/2,height=im.height/2);p.insert_image(p.rect,stream=buf.getvalue())
            pdf.save(target,garbage=4,deflate=True);pdf.close()
        split='dev' if v<dev_count else 'confirmation'
        digest=hashlib.sha256(target.read_bytes()).hexdigest()
        documents.append({'file_name':filename,'sha256':digest,'document_group':name,'split':split,
                          'seed':seed_start+v,'source':{'row_count':rows,'col_count':cols,'header_depth':headers,'cells':cells,'pages':render_map}})
        specs=[('column_count','请判断该表的完整逻辑列数。合并表头覆盖的底层列分别计数，包含左侧项目列；只返回整数。',cols),
               ('row_count','请判断该表的完整逻辑行数，包括全部表头行、明细行与合计行，不计标题和附注；跨页重复表头只计一次。只返回整数。',rows),
               ('header_depth','该表有几层逻辑表头？从顶层分组到最底层列名计数，不计表名、单位说明或数据行；跨页重复表头只计一次。只返回整数。',headers)]
        for metric,question,expected in specs:
            questions.append({'id':name+'-'+metric,'file_name':filename,'question_type':'extract','question':question,
                              'table_hint':title,'answer_format':'number','expected':str(expected),'metric':metric,
                              'document_group':name,'split':split,'image_sha256':digest})
    atomic_json(manifest,{'version':'layout-features-v1','source':'original synthetic grids','license':'AGPL-3.0-only',
                          'limitations':'Variable dimensions but shared generator; confirmation is source-disjoint synthetic only, not real-document generalization.',
                          'documents':documents,'questions':questions})
    print(json.dumps({'documents':len(documents),'questions':len(questions),'dev_questions':dev_count*3,'confirmation_questions':(count-dev_count)*3}))



def main():
    from geometry_metadata import finalize
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--font',type=Path,required=True)
    parser.add_argument('--suite',choices=['layout','structure'],required=True)
    args=parser.parse_args()
    args.output=args.output.expanduser();args.font=args.font.expanduser()
    if not args.font.is_file():parser.error('--font must be an existing local font')
    if args.output.exists() and (not args.output.is_dir() or any(args.output.iterdir())):
        parser.error('--output must be a new or empty directory')
    if args.suite=='layout':
        build(args.output,font_path=args.font)
        finalize(args.output,'layout_diagnostics_v1')
    else:
        build(args.output,font_path=args.font,seed_start=619031,count=40,dev_count=16,prefix='struct2')
        finalize(args.output,'structure_diagnostics_v2')


if __name__=='__main__':main()
