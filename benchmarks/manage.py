"""Offline bundle verification, composition statistics and input-only export."""
# SPDX-License-Identifier: AGPL-3.0-only
import argparse
from collections import Counter
from decimal import Decimal, InvalidOperation
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent
QUESTION_FIELDS = ('id', 'file_name', 'question_type', 'question', 'table_hint', 'answer_format')


def read(path):
    return json.loads(path.read_text(encoding='utf-8'))


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def datasets(name='all'):
    registry = read(ROOT / 'manifest.json')
    entries = [x for x in registry['datasets'] if name == 'all' or x['name'] == name]
    if not entries:
        raise ValueError('Unknown dataset: ' + name)
    return [(entry, read(ROOT / entry['name'] / 'benchmark.json')) for entry in entries]


def counts(questions):
    total = len(questions)
    return {kind: {'count': n, 'percent': round(100*n/total, 2) if total else 0}
            for kind, n in sorted(Counter(q['question_type'] for q in questions).items())}


def statistics(name='all'):
    rows, questions = [], []
    for entry, data in datasets(name):
        qs = data['questions']; questions.extend(qs)
        rows.append({'dataset': entry['name'], 'documents': len(data['documents']),
                     'questions': len(qs), 'types': counts(qs),
                     'historical_splits': dict(Counter(q['split'] for q in qs)),
                     'current_use': entry['current_use']})
    return {'datasets': rows, 'total_documents': sum(r['documents'] for r in rows),
            'total_questions': len(questions), 'types': counts(questions)}


def source_shape(document):
    source = document['source']; rows = source['rows']
    if not rows or not rows[0] or any(len(row) != len(rows[0]) for row in rows):
        raise ValueError('Invalid rectangular source grid')
    occupied, covered = set(), set()
    for cell in source['merges']:
        r, c, rs, cs = (cell[k] for k in ('row','col','rowspan','colspan'))
        if any(type(x) is not int for x in (r,c,rs,cs)) or min(r,c)<0 or min(rs,cs)<1 or r+rs>len(rows) or c+cs>len(rows[0]):
            raise ValueError('Source merge out of bounds')
        positions = {(y,x) for y in range(r,r+rs) for x in range(c,c+cs)}
        if positions & occupied:
            raise ValueError('Source merge overlaps')
        occupied |= positions; covered |= positions-{(r,c)}
    for r,row in enumerate(rows):
        for c,value in enumerate(row):
            if ((r,c) in covered) != (value is None):
                raise ValueError('Covered source cells must be null and only covered cells may be null')


def verify(name='all'):
    ids = set(); assets = 0
    for entry, data in datasets(name):
        directory = ROOT / entry['name']; path = directory / 'benchmark.json'
        if sha256(path) != entry['metadata_sha256']:
            raise ValueError('Metadata digest mismatch: '+entry['name'])
        if len(data['questions']) != entry['questions'] or len(data['documents']) != entry['documents']:
            raise ValueError('Dataset count mismatch')
        if data['license'] != 'AGPL-3.0-only':
            raise ValueError('Unexpected dataset license')
        documents = {d['file_name']: d for d in data['documents']}
        if len(documents) != len(data['documents']):
            raise ValueError('Duplicate document filename')
        if {p.name for p in (directory/'files').iterdir()} != set(documents):
            raise ValueError('Missing or unexpected document asset')
        for filename, document in documents.items():
            asset = directory/'files'/filename
            if Path(filename).name != filename or asset.is_symlink() or asset.suffix not in ('.png','.pdf'):
                raise ValueError('Invalid document path')
            if not asset.is_file() or sha256(asset) != document['sha256']:
                raise ValueError('Asset digest mismatch: '+filename)
            source_shape(document); assets += 1
        for q in data['questions']:
            if not all(k in q for k in (*QUESTION_FIELDS,'split','expected')) or q['id'] in ids:
                raise ValueError('Missing question field or duplicate question id')
            ids.add(q['id'])
            if q['file_name'] not in documents or q['question_type'] not in ('extract','thinking','structure'):
                raise ValueError('Invalid question source or type')
            expected, fmt = q['expected'], q['answer_format']
            if fmt == 'number':
                try: valid = Decimal(str(expected)).is_finite()
                except InvalidOperation: valid = False
                if not valid: raise ValueError('Invalid numeric reference')
            elif fmt == 'json_array':
                if not isinstance(expected,list) or any(not isinstance(v,str) for v in expected):
                    raise ValueError('Invalid ordered array reference')
            elif fmt == 'json':
                if q['question_type'] != 'structure' or not isinstance(expected,dict):
                    raise ValueError('Invalid structure reference')
                rows = documents[q['file_name']]['source']['rows']
                if expected['row_count'] != len(rows) or expected['col_count'] != len(rows[0]):
                    raise ValueError('Structure dimensions differ from source')
                seen=set()
                for cell in expected['cells']:
                    r,c,rs,cs=(cell[k] for k in ('row','col','rowspan','colspan'))
                    if min(r,c)<0 or min(rs,cs)<1 or r+rs>len(rows) or c+cs>len(rows[0]):
                        raise ValueError('Reference structure is out of bounds')
                    positions={(y,x) for y in range(r,r+rs) for x in range(c,c+cs)}
                    if positions & seen or rows[r][c] != cell['text']:
                        raise ValueError('Reference structure overlaps or differs from source')
                    seen |= positions
            else: raise ValueError('Unknown answer format')
            if 'image_sha256' in q and q['image_sha256'] != documents[q['file_name']]['sha256']:
                raise ValueError('Question asset digest mismatch')
    return {'verified': True, 'questions': len(ids), 'documents': assets, 'network_calls': 0}


def inputs(name='all', split='all'):
    for entry, data in datasets(name):
        for q in data['questions']:
            if split != 'all' and q['split'] != split: continue
            # Never export expected answers, source grids or evaluation metadata.
            row = {k: q[k] for k in QUESTION_FIELDS}
            row['document_path'] = (Path('benchmarks')/entry['name']/'files'/q['file_name']).as_posix()
            yield row


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command',choices=['verify','stats','export'])
    parser.add_argument('--dataset',default='all')
    parser.add_argument('--split',choices=['all','train','dev','holdout','confirmation'],default='all')
    parser.add_argument('--output',type=Path)
    args=parser.parse_args()
    try:
        if args.command=='verify':result=verify(args.dataset)
        elif args.command=='stats':result=statistics(args.dataset)
        else:
            if args.output is None:parser.error('export requires --output')
            verify(args.dataset)
            rows=list(inputs(args.dataset,args.split))
            # Exclusive create prevents accidentally overwriting dataset assets.
            with args.output.open('x',encoding='utf-8') as f:
                for row in rows:f.write(json.dumps(row,ensure_ascii=False)+'\n')
            result={'exported_questions':len(rows),'output':str(args.output),'contains_reference_answers':False}
        print(json.dumps(result,ensure_ascii=False,indent=2))
    except (ValueError,KeyError,OSError) as exc:
        parser.exit(1,str(exc)+'\n')


if __name__=='__main__':main()
