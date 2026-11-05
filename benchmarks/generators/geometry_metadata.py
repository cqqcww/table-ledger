"""Package original geometric grids and their task annotations."""
# SPDX-License-Identifier: AGPL-3.0-only
import json
from pathlib import Path


def finalize(root, suite):
    path=Path(root)/'benchmark.json';data=json.loads(path.read_text())
    if suite not in ('layout_diagnostics_v1','structure_diagnostics_v2'):
        raise ValueError('Unknown geometry suite')
    structure=suite=='structure_diagnostics_v2'
    for i,document in enumerate(data['documents']):
        source=document['source'];rows=[[None]*source['col_count'] for _ in range(source['row_count'])];merges=[]
        for cell in source['cells']:
            rows[cell['row']][cell['col']]=cell['raw']
            if cell['rowspan']>1 or cell['colspan']>1:
                merges.append({k:cell[k] for k in ('row','col','rowspan','colspan')})
        source.update(rows=rows,merges=merges)
        if structure:
            split='train' if i<6 else 'dev' if i<16 else 'confirmation'
            document['split']=split
            document['usage_status']={'train':'designated_training','dev':'observed_development','confirmation':'reserved_confirmation'}[split]
            for q in data['questions']:
                if q['file_name']==document['file_name']:
                    q['generation_split']=q['split'];q['split']=split
                    q['usage_status']='not_directly_evaluated; inherits document exposure'
            top=1 if i%2==0 else 2
            cells=[{'text':c['raw'],**{k:c[k] for k in ('row','col','rowspan','colspan')}} for c in source['cells'] if c['row']<top or c['col']<1]
            data['questions'].append({'id':document['document_group']+'-structure','file_name':document['file_name'],'question_type':'structure',
                'question':f'请恢复目标表格的前 {top} 行和前 1 列结构，输出两个区域的并集。行列数填写完整表格的逻辑行列数；跨页重复表头只计一次，合并单元格保留真实完整跨度。',
                'table_hint':'业务汇总明细表','answer_format':'json',
                'expected':{'row_count':source['row_count'],'col_count':source['col_count'],'cells':cells},
                'document_group':document['document_group'],'split':split,'image_sha256':document['sha256'],
                'usage_status':('training_demo' if i in (2,5) else 'reserved_training') if split=='train' else 'development_and_regression' if split=='dev' else 'reserved_confirmation'})
        else:
            document['usage_status']='development_and_regression'
    if not structure:
        for q in data['questions']:q['usage_status']='development_and_regression'
    data.update(version=suite.replace('_','-'),description='原创程序生成的中文版式与结构诊断数据，标准答案来自渲染前的逻辑网格。',
        license='AGPL-3.0-only',usage_status='mixed; see per-document and per-question status' if structure else 'development_and_regression',
        limitations='共享生成器家族，不能代表真实扫描或拍照文档。汇总数值是装饰性随机数据，不用于算术评测。源网格与答案只用于核验，不进入视觉求解输入。',
        split_method='按源文档统一角色；同一文档的所有问法不得跨训练与确认集合。generation_split仅保留生成时的旧计数划分。' if structure else '18文档54题开发、6文档18题历史确认；现均为回归。')
    path.write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n')
