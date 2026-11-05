"""Evidence-linked, deterministic arithmetic. No model-generated Python/eval."""
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP, localcontext
import re
from .schema import AnswerError, compact_json, json_loads, normalize_response


def parse_object(raw):
    raw = raw.strip()
    if raw.startswith('```'):
        match = re.fullmatch(r'```(?:json)?\s*(.*?)\s*```', raw, re.S | re.I)
        if not match:
            raise AnswerError('未闭合 JSON 代码块')
        raw = match.group(1)
    obj = json_loads(raw)
    if not isinstance(obj, dict):
        raise AnswerError('应返回 JSON 对象')
    return obj


def number(raw):
    """Only parse numeric cells; preserve identifiers and raw strings separately."""
    s = str(raw).strip().replace('−', '-').replace('，', ',').replace('％', '%')
    s = re.sub(r'\s+', '', s).replace(',', '')
    if s.startswith(('(', '（')) and s.endswith((')', '）')):
        s = '-' + s[1:-1]
    percent = s.endswith('%')
    if percent:
        s = s[:-1]
    s = re.sub(r'(亿元|万元|元|吨|公斤|千克|件|台|人|个)$', '', s)
    if not re.fullmatch(r'[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?', s):
        raise AnswerError(f'操作数不是明确数值: {raw!r}')
    try:
        value = Decimal(s)
    except InvalidOperation as exc:
        raise AnswerError('无效操作数') from exc
    if not value.is_finite() or abs(value) > Decimal('1e100'):
        raise AnswerError('操作数超出范围')
    return value / 100 if percent else value


def bbox(value):
    if (not isinstance(value, list) or len(value) != 4
            or any(type(v) not in (int, float) for v in value)
            or not (0 <= value[0] < value[2] <= 1000 and 0 <= value[1] < value[3] <= 1000)):
        raise AnswerError('bbox 须为 0..1000 的 [左,上,右,下] 有效矩形')
    return value


def validate_evidence(items, pages):
    if not isinstance(items, list) or len(items) > 500:
        raise AnswerError('evidence 必须是至多 500 项的列表')
    found = {}
    for item in items:
        if not isinstance(item, dict) or not isinstance(item.get('id'), str) or not item['id']:
            raise AnswerError('证据必须有非空字符串 id')
        if item['id'] in found:
            raise AnswerError('证据 id 重复')
        if type(item.get('page')) is not int or not 1 <= item['page'] <= pages:
            raise AnswerError('证据页码越界')
        for key in ('raw', 'row_header', 'col_header', 'unit'):
            if not isinstance(item.get(key), str):
                raise AnswerError(f'证据缺少字符串 {key}')
        bbox(item.get('bbox'))
        found[item['id']] = item
    return found


SCALES = {Decimal(s) for s in ('1', '100', '0.01', '1000', '0.001', '10000', '0.0001', '100000000', '0.00000001')}


def operand_unit(item):
    """Cross-check explicit monetary suffixes; never silently rescale a value."""
    raw = item['raw'].strip()
    match = re.fullmatch(r'[（(]?[+\-−]?[\d,，]+(?:\.\d+)?[)）]?\s*(亿元|万元|元)', raw)
    declared = item['unit'].strip()
    if not match:
        return declared
    explicit = match[1]
    if declared:
        unit = re.search(r'亿元|万元|元', declared)
        if not unit or unit[0] != explicit:
            raise AnswerError('原文金额单位与声明单位冲突，须回原图核对')
        # Composite dimensions (e.g. 元/吨) must still match across operands.
        return declared
    return explicit


def execute_plan(answer, plans, evidence):
    if not isinstance(plans, list) or len(plans) > 100:
        raise AnswerError('plans 应为至多 100 项的列表')
    used = set()
    for plan in plans:
        if not isinstance(plan, dict):
            raise AnswerError('plan 应为对象')
        index = plan.get('index')
        if isinstance(answer, list):
            if type(index) is not int or not 0 <= index < len(answer):
                raise AnswerError('plan.index 必须指向答案数组的一个元素')
        elif index is not None:
            raise AnswerError('标量答案的 plan.index 必须为 null')
        if index in used:
            raise AnswerError('同一答案位置不能重复计算')
        used.add(index)
        refs = plan.get('refs')
        if (not isinstance(refs, list) or not refs or len(refs) != len(set(refs))
                or any(r not in evidence for r in refs)):
            raise AnswerError('plan.refs 必须引用互不重复的真实证据 id')
        values = [number(evidence[r]['raw']) for r in refs]
        units = {operand_unit(evidence[r]) for r in refs} - {''}
        if len(units) > 1:
            raise AnswerError('操作数单位不一致，须回原图核对并拆分换算，不可直接聚合')
        filt = plan.get('filter')
        if filt:
            threshold = number(filt.get('value', ''))
            predicates = {'gt':lambda v:v>threshold, 'ge':lambda v:v>=threshold,
                          'lt':lambda v:v<threshold, 'le':lambda v:v<=threshold,
                          'eq':lambda v:v==threshold}
            if filt.get('op') not in predicates:
                raise AnswerError('仅支持 gt/ge/lt/le/eq 数值筛选')
            keep = [i for i,v in enumerate(values) if predicates[filt['op']](v)]
            values, refs = [values[i] for i in keep], [refs[i] for i in keep]
        op = plan.get('op')
        with localcontext() as ctx:
            ctx.prec = 80
            if op == 'count': value = Decimal(len(values))
            elif not values: raise AnswerError('筛选后无数值，不能当作零继续计算')
            elif op == 'sum': value = sum(values, Decimal(0))
            elif op == 'mean': value = sum(values, Decimal(0))/len(values)
            elif op == 'min': value = min(values)
            elif op == 'max': value = max(values)
            elif op in ('subtract', 'divide', 'growth'):
                if len(values) != 2: raise AnswerError(f'{op} 需要恰好两个操作数')
                a,b = values
                if op in ('divide','growth') and b == 0: raise AnswerError('分母为零')
                value = a-b if op == 'subtract' else a/b if op == 'divide' else (a-b)/b
            elif op == 'multiply':
                value = Decimal(1)
                for v in values: value *= v
            elif op in ('argmax','argmin','sort'):
                reverse = op == 'argmax' or (op == 'sort' and plan.get('descending', False))
                indices = sorted(range(len(values)), key=lambda i:values[i], reverse=reverse)
                if op != 'sort':
                    best = values[indices[0]]
                    indices = [i for i in indices if values[i] == best]
                top = plan.get('top_k')
                if top is not None:
                    if type(top) is not int or top < 1: raise AnswerError('top_k 必须为正整数')
                    indices = indices[:top]
                value = [evidence[refs[i]]['row_header'] for i in indices]
                if len(value) == 1 and op != 'sort': value = value[0]
            else: raise AnswerError(f'不支持的运算: {op}')
            if isinstance(value, Decimal):
                scale = number(plan.get('scale','1'))
                if scale not in SCALES: raise AnswerError('单位/百分比换算倍率不在允许范围')
                value *= scale
                places = plan.get('decimals')
                if places is not None:
                    if type(places) is not int or not 0 <= places <= 20: raise AnswerError('decimals 超出范围')
                    value = value.quantize(Decimal(1).scaleb(-places), rounding=ROUND_HALF_UP)
                if abs(value) > Decimal('1e100'): raise AnswerError('计算结果超出范围')
                suffix = plan.get('suffix', '')
                if not isinstance(suffix, str) or len(suffix) > 16: raise AnswerError('suffix 无效')
                value = format(value, 'f') + suffix
        if isinstance(answer, list): answer[index] = value
        else: answer = value
    return answer


def normalize_evidenced(raw, question, pages, *, calculations=True):
    obj = parse_object(raw)
    answer = obj.get('answer', '')
    evidence = validate_evidence(obj.get('evidence', []), pages)
    if answer != '' and answer is not None and not evidence:
        raise AnswerError('非空答案必须提供原图证据，不能只给最终结论')
    plans = obj.get('plans', [])
    if calculations:
        answer = execute_plan(answer, plans, evidence)
    elif plans:
        raise AnswerError('此消融配置不允许 plans')
    final = normalize_response(compact_json({'answer':answer,'calculations':[]}),
                               question.question_type, question.answer_format)
    return final, list(evidence.values()), plans
