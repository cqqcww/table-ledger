"""Question-derived scope guards. Uncertain coverage is a trigger, never truth."""
import json
import re
import hashlib
from pathlib import Path
import time

from .blind_review import leaf_equal, normalize_bound, reread_messages
from .cloud import StopRun
from .pipeline import atomic_json
from .evidence import parse_object
from .comparison import equivalent
from .schema import AnswerError, compact_json


def identity(text):
    return re.sub(r'[\s/|>→：:·]', '', str(text)).casefold()


def contract(question):
    text = question.question
    result = {'shape': 'array' if question.answer_format == 'json_array' else 'unknown',
              'targets': [], 'expected_count': None, 'column_terms': [], 'excluded_rows': [],
              'blank_sensitive': bool(re.search(r'空白|空字符串|备注|blank|empty', text, re.I)),
              'coverage_required': bool(re.search(r'全部|所有|明细|整列|整行|之和|平均|最大|最小|最多|最少|\b(?:all|every|entire|sum|total|average|highest|lowest|largest|smallest|most|least)\b|\bhow many\b', text, re.I)),
              'limitations': 'Only explicit enumerated Chinese extraction and literal scope cues are compiled; other semantics remain unverified.'}
    # A list of named rows sharing ONE requested field. Do not infer a count
    # from "前三行", coordinate numbers, filters, or a list of requested columns.
    match = re.search(r'(?:依次|分别)(?:提取|读取)([^。；;，,]+?)的(本期金额|上期金额|本期数量|上期数量|金额|数量|备注|编号)(?=[，,。；;]|$)', text)
    if question.question_type == 'extract' and match and '、' in match[1]:
        targets = match[1].split('、')
        if all(t.strip() and not re.search(r'以及|或者|到|至|前\d|后\d|[和与]', t) for t in targets):
            result.update(shape='array', targets=targets, expected_count=len(targets), enumeration_quote=match[0])
            field = match[2]
            result['column_terms'] = ([field[:2], field[2:]] if field.startswith(('本期', '上期')) else [field])
    if not result['column_terms'] and question.question_type == 'extract':
        periods = [p for p in ('本期', '上期') if p in text]
        if len(periods) == 1:
            result['column_terms'] = periods
    for match in re.finditer(r'(?:不包含|不包括|排除|不重复计算)([^。；;，,]+)', text):
        result['excluded_rows'].extend(t for t in ('小计', '合计', '附注') if t in match[1])
    return result


def answer_values(answer, c):
    try:
        value = json.loads(answer)
    except (ValueError, TypeError):
        value = answer
    if c['shape'] == 'array' and not isinstance(value, list):
        return [], ['answer_shape']
    values = value if isinstance(value, list) else [value]
    flags = []
    if any(isinstance(v, (dict, list)) or v is None or isinstance(v, bool) for v in values):
        flags.append('unsupported_answer_shape')
    if c['expected_count'] is not None and len(values) != c['expected_count']:
        flags.append('answer_length')
    return values, flags


def audit(question, answer, evidence, plans):
    c = contract(question)
    values, flags = answer_values(answer, c)
    if not answer:
        flags.append('empty_answer')
    if not evidence:
        flags.append('missing_evidence')
    if c['coverage_required']:
        flags.append('scope_coverage_unverified')
    # Existing outputs lack bindings. A unique raw-value match is only a
    # diagnostic mapping; it is never accepted as proof of a correct source.
    if question.question_type == 'extract' and not plans:
        for i, value in enumerate(values):
            matches = [e for e in evidence if leaf_equal(value, e.get('raw', ''))]
            if len(matches) != 1:
                flags.append('source_binding_unverified')
                continue
            e = matches[0]
            row, col = identity(e.get('row_header', '')), identity(e.get('col_header', ''))
            if i < len(c['targets']) and identity(c['targets'][i]) not in row:
                flags.append('requested_row_path')
            if any(identity(term) not in col for term in c['column_terms']):
                flags.append('requested_column_path')
            if c['blank_sensitive'] and e.get('cell_state') not in ('blank', 'value'):
                flags.append('blank_state_unverified')
    if c['excluded_rows']:
        for plan in plans:
            used = set(plan.get('refs', []))
            if any(e.get('id') in used and any(t in e.get('row_header', '') for t in c['excluded_rows']) for e in evidence):
                flags.append('excluded_operand')
    return {'contract': c, 'flags': sorted(set(flags)), 'trigger': bool(flags),
            'note': 'Flags indicate invalid shape or unverified scope, not an oracle that the answer is wrong.'}


SCOPE_PROMPT = '''额外输出协议：逐条evidence增加 row_path、col_path、cell_state。
row_path是从外层分组到当前行的原图标题数组，例如["业务一部","项目乙"]；col_path是从顶层表头到叶表头的数组，例如["本期","金额"]。不得只留重复的叶表头，不得把整条路径放在一个元素里冒充层级。
row_header与col_header分别等于对应路径用" / "连接的文本。合并格的标题应继承；真实数据空白不能继承上一行的值。
cell_state仅能是"blank"或"value"，blank的raw必须是空字符串；0、横杠、前导零编号都是value。
按题目要求的行顺序输出，每一个空白也占一个数组位置。未要求的汇总行和脚注不能作为明细操作数。
对于全部行、所有项目、明细范围等要求，再输出scope_inventory：按原图顺序列出相关范围中每一个候选行，格式[{"row_path":["分组","行名"],"included":true,"reason":"题意内明细","refs":["e1"]}]。小计、合计等排除行也列出included=false、refs=[]并说明原因。只按图中实际行枚举，不从候选答案猜测长度。
scope_inventory中被包含行的refs之并集必须恰好覆盖所有答案绑定的refs。该清单用于检查范围，不能代替原图证据。
'''


def scope_messages(question, doc, root):
    messages = reread_messages(question, doc, root)
    messages[0]['content'][0]['text'] += '\n' + SCOPE_PROMPT + '\n从题目确定的约束（未知数量不猜）：' + compact_json(contract(question))
    return messages


def normalize_scope(raw, question, pages):
    obj = parse_object(raw)
    result = normalize_bound(raw, question, pages)
    c = contract(question)
    _, flags = answer_values(result['answer'], c)
    if flags:
        raise AnswerError('Scope: ' + ','.join(flags))
    evidence = {e['id']: e for e in result['evidence']}
    used = {ref for b in result['answer_bindings'] for ref in b['refs']}
    for ref in used:
        e = evidence[ref]
        for path, header in [('row_path', 'row_header'), ('col_path', 'col_header')]:
            parts = e.get(path)
            if not isinstance(parts, list) or not parts or any(not isinstance(p, str) or not p.strip() for p in parts):
                raise AnswerError('Scope: missing hierarchical ' + path)
            if identity(''.join(parts)) != identity(e[header]):
                raise AnswerError('Scope: path/header mismatch')
        state = e.get('cell_state')
        if state not in ('blank', 'value') or (e['raw'] == '') != (state == 'blank'):
            raise AnswerError('Scope: blank/value mismatch')
        if any(t in ''.join(e['row_path']) for t in c['excluded_rows']):
            raise AnswerError('Scope: excluded row used in answer')
    for binding in result['answer_bindings']:
        index = binding['index']
        for ref in binding['refs']:
            e = evidence[ref]
            if index is not None and index < len(c['targets']) and identity(c['targets'][index]) not in identity(''.join(e['row_path'])):
                raise AnswerError('Scope: requested row/order mismatch')
            if question.question_type == 'extract' and any(identity(t) not in identity(''.join(e['col_path'])) for t in c['column_terms']):
                raise AnswerError('Scope: requested header mismatch')
            if len(c['column_terms']) > 1 and len(e['col_path']) < 2:
                raise AnswerError('Scope: flattened multi-level header')
    for plan in result['plans']:
        positions = []
        for ref in plan['refs']:
            e = evidence[ref]
            if any(t in ''.join(e['row_path']) for t in c['excluded_rows']):
                raise AnswerError('Scope: excluded subtotal/footnote operand')
            positions.append((e['page'], tuple(e['row_path']), tuple(e['col_path'])))
        if len(set(positions)) != len(positions):
            raise AnswerError('Scope: duplicate logical operand')
    if c['coverage_required']:
        inventory = obj.get('scope_inventory')
        if not isinstance(inventory, list) or not inventory:
            raise AnswerError('Scope: range inventory missing')
        refs, rows = [], set()
        for item in inventory:
            path = item.get('row_path')
            if not isinstance(path, list) or not path or any(not isinstance(p, str) or not p for p in path):
                raise AnswerError('Scope: invalid inventory row')
            key = tuple(path)
            if key in rows or type(item.get('included')) is not bool or not isinstance(item.get('reason'), str) or not item['reason']:
                raise AnswerError('Scope: duplicate/invalid inventory')
            rows.add(key)
            rr = item.get('refs')
            if not isinstance(rr, list) or any(not isinstance(r, str) or r not in evidence for r in rr):
                raise AnswerError('Scope: invalid inventory refs')
            if not item['included'] and rr:
                raise AnswerError('Scope: excluded row supplies evidence')
            if item['included']:
                if not rr or any(tuple(evidence[r].get('row_path', [])) != key for r in rr):
                    raise AnswerError('Scope: inventory/source mismatch')
                refs.extend(rr)
        if len(refs) != len(set(refs)) or set(refs) != used:
            raise AnswerError('Scope: incomplete inventory binding')
        result['scope_inventory'] = inventory
    result['contract'] = c
    return result


def choose(question, baseline, reader, corroborator=None):
    if not reader or not reader.get('valid'):
        return {'answer': baseline, 'route': 'invalid_scope_reader'}
    if equivalent(question, baseline, reader['answer']):
        return {'answer': baseline, 'route': 'scope_agrees_baseline'}
    if corroborator and corroborator.get('valid') and equivalent(question, reader['answer'], corroborator['answer']):
        return {'answer': reader['answer'], 'route': 'independently_confirmed_change'}
    return {'answer': baseline, 'route': 'unconfirmed_change'}


def run_guard(question, doc, record, meter, root):
    """Opt-in bounded stage: one scoped read, then one blind corroboration if changed."""
    check = audit(question, record['answer'], record.get('evidence', []), record.get('plans', []))
    if question.question_type == 'structure' or not check['trigger']:
        return {'answer': record['answer'], 'route': 'not_triggered', 'audit': check, 'readers': {}, 'new_calls': 0}
    from .fingerprint import implementation_hash
    code = implementation_hash()
    fingerprint = hashlib.sha256(compact_json({'question': {'question':question.question,'question_type':question.question_type,
        'table_hint':question.table_hint,'answer_format':question.answer_format}, 'document':doc.sha256,
        'render':[str(p) for p in doc.images], 'code':code,'model':meter.client.model,
        'baseline':record['answer'],'audit':check}).encode()).hexdigest()
    folder = root / 'scope_guard' / fingerprint
    path = folder / 'result.json'
    if path.exists():
        return {**json.loads(path.read_text()), 'cached': True, 'new_calls': 0}
    readers = {}; new_calls = 0
    for mode in ('scope', 'corroborate'):
        if mode == 'corroborate' and (not readers['scope'].get('valid') or equivalent(question,record['answer'],readers['scope']['answer'])):
            break
        saved = folder / (mode+'.json')
        if saved.exists():
            readers[mode] = json.loads(saved.read_text())
            continue
        messages = scope_messages(question,doc,folder/'crops') if mode == 'scope' else reread_messages(question,doc,folder/'crops')
        atomic_json(folder/(mode+'_input.json'), {'text':messages[0]['content'][0]['text'],
            'document_sha256':doc.sha256,'image_count':sum(p['type']=='image_url' for p in messages[0]['content']),
            'inputs':'Question and original image only; no answer, transcript, or target gold.'})
        started = time.monotonic()
        try:
            new_calls += 1
            raw = meter.call(messages,label=mode+'-'+fingerprint[:16],tokens=8192,thinking=4096)
            normalized = (normalize_scope if mode == 'scope' else normalize_bound)(raw,question,len(doc.images))
            reader = {**normalized,'valid':True}
        except StopRun:
            raise
        except (ValueError,RuntimeError,TypeError,KeyError,IndexError,AttributeError) as exc:
            reader = {'valid':False,'answer':'','error':str(exc)}
        reader['seconds'] = time.monotonic()-started
        atomic_json(saved,reader);readers[mode]=reader
    decision = choose(question,record['answer'],readers.get('scope'),readers.get('corroborate'))
    result = {**decision,'audit':check,'readers':readers,'fingerprint':fingerprint,'cached':False,
              'new_calls':new_calls,'limitation':'Matching independent prompts on the same model is corroboration, not proof of image truth.'}
    atomic_json(path,result)
    return result
