"""Conservative local exact-match checks with ordered values and exact decimals."""
from collections import defaultdict
from decimal import Decimal,InvalidOperation
import re
import random
from .schema import json_loads,validate_structure


def scalar(value,numeric=False):
    s=str(value).strip()
    if numeric or re.fullmatch(r'-?(?:0|[1-9]\d*)(?:\.\d+)?',s):
        # Do not collapse identifiers with significant leading zeros.
        try:return ('number',Decimal(s.replace(',','')))
        except InvalidOperation:pass
    return ('text',re.sub(r'\s+',' ',s))


def exact(prediction,expected,kind,question_type):
    try:
        if question_type=='structure':
            p=validate_structure(json_loads(prediction));e=validate_structure(expected)
            return p==e
        if kind=='json_array':
            p=json_loads(prediction)
            def tree(v):return [tree(x) for x in v] if isinstance(v,list) else scalar(v)
            return tree(p)==tree(expected)
        return scalar(prediction,kind=='number')==scalar(expected,kind=='number')
    except (ValueError,TypeError,KeyError):return False


def evaluate(predictions,questions):
    by_type=defaultdict(lambda:[0,0]);by_doc=defaultdict(lambda:[0,0]);rows=[]
    for q in questions:
        ok=exact(predictions.get(str(q['id']),''),q['expected'],q['answer_format'],q['question_type'])
        for target,key in ((by_type,q['question_type']),(by_doc,q['file_name'])):
            target[key][0]+=int(ok);target[key][1]+=1
        rows.append({'id':q['id'],'file_name':q['file_name'],'question_type':q['question_type'],'correct':ok})
    correct=sum(r['correct'] for r in rows)
    return {'correct':correct,'total':len(rows),'accuracy':correct/len(rows) if rows else 0,
            'by_type':{k:{'correct':a,'total':b,'accuracy':a/b} for k,(a,b) in by_type.items()},
            'by_document':dict(by_doc),'rows':rows,
            'scorer':'local_exact_v1; ordered arrays; Decimal numbers; exact normalized structure; not official scorer'}


def compare(reference,candidate):
    a={r['id']:r for r in reference['rows']};b={r['id']:r for r in candidate['rows']}
    if a.keys()!=b.keys():raise ValueError('评测题目集合不一致')
    docs=defaultdict(list)
    corrected=regressed=0
    for key in a:
        delta=int(b[key]['correct'])-int(a[key]['correct'])
        docs[a[key]['file_name']].append(delta)
        corrected+=delta==1;regressed+=delta==-1
    rng=random.Random(167);keys=list(docs);samples=[]
    for _ in range(2000):
        draw=[rng.choice(keys) for _ in keys]
        values=[v for k in draw for v in docs[k]]
        samples.append(sum(values)/len(values))
    samples.sort()
    return {'corrected':corrected,'regressed':regressed,
            'net_questions':corrected-regressed,'document_bootstrap_95pct_delta':[samples[50],samples[1949]]}
