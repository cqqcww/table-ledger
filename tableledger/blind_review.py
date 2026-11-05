"""Candidate-blind image rereading and conservative, evidence-bound replacement."""
import copy
from decimal import Decimal
import hashlib
import json
import re

from .advanced_prompts import prompt
from .evidence import parse_object,normalize_evidenced
from .fewshot import tokens,demonstration_context
from .comparison import equivalent
from .regions import views
from .schema import AnswerError,compact_json

BINDINGS_PROMPT='''独立读图任务。先确定题目要求的范围、完整多级表头、行标题、空白和单位，再作答。
每个最终答案元素还必须提供 answer_bindings：
标量 [{"index":null,"refs":["e1"]}]；一维数组 [{"index":0,"refs":["e1"]},{"index":1,"refs":["e2"]}]。
纯提取每个元素绑定一个原始单元格，evidence.raw 保留该格原文，包括空字符串；不能把空白填成0。
计算元素的绑定refs必须与该元素plans.refs完全一致，计算与换算交给plans；不要删改操作数以凑结果。
当题目问最大/最小值对应的名称，必须列出完整候选范围的数值证据，用op=argmax/argmin返回row_header；不能只给胜出格或把最大数值当作名称。
argmax/argmin仍只用一个index=null的plan，answer_bindings.refs按顺序列出该plan全部refs，不只绑定胜出项。
每条被绑定证据必须包含有意义的row_header及完整col_header，页码、原图bbox、unit。
一维数组须完整覆盖所有元素、按要求顺序返回；不遗漏重复值、空格或末项。
不能从单个数值相同推断选对了行列。表头计数、复杂嵌套结果等无法可靠绑定时仍如实作答，不编造证据；系统将保留原流程。
'''


def _training_key(v):
    # Keep the original demo selection fixed while repairing reader validation.
    s=re.sub(r'\s+',' ',str(v)).strip().replace('−','-').replace('，',',')
    if re.fullmatch(r'[+-]?(?:0|[1-9]\d*|[1-9]\d{0,2}(?:,\d{3})+)(?:\.\d+)?',s):
        return ('number',Decimal(s.replace(',','')))
    return ('text',s)


def leaf_equal(a,b):
    def norm(v):
        text=re.sub(r'\s+',' ',str(v)).strip().replace('−','-').replace('，',',')
        s=text;currency=''
        if s[:1] in ('$','€','£','¥'):
            currency=s[0];s=s[1:].strip()
        if s.startswith('(') and s.endswith(')'):s='-'+s[1:-1].strip()
        key=_training_key(s)
        return (key,currency) if key[0]=='number' else (('text',text),'')
    (ka,ca),(kb,cb)=norm(a),norm(b)
    return ka==kb and (not ca or not cb or ca==cb)


def validate_bindings(obj,final_answer,evidence,plans):
    # Determine answer shape from the original object, preserving numeric text IDs.
    answer=obj.get('answer')
    try:final_shape=json.loads(final_answer)
    except (ValueError,TypeError):final_shape=final_answer
    if isinstance(final_shape,list) and (not isinstance(answer,list) or any(isinstance(v,(dict,list)) for v in final_shape)):
        raise AnswerError('Calculated arrays need explicit flat per-element bindings')
    if isinstance(answer,list):
        if not answer or any(isinstance(v,(dict,list)) or v is None or isinstance(v,bool) for v in answer):
            raise AnswerError('Bindings support nonempty one-dimensional scalar arrays')
        indexes=list(range(len(answer)))
    elif isinstance(answer,(str,int,float)) and not isinstance(answer,bool):indexes=[None]
    else:raise AnswerError('Unsupported answer shape for binding')
    bindings=obj.get('answer_bindings')
    if not isinstance(bindings,list) or len(bindings)!=len(indexes):raise AnswerError('Every answer element needs one binding')
    by_id={e['id']:e for e in evidence};by_index={}
    for b in bindings:
        if not isinstance(b,dict) or 'index' not in b:raise AnswerError('Binding index required')
        index=b['index']
        if (index is not None and type(index) is not int) or index not in indexes or index in by_index:
            raise AnswerError('Duplicate or invalid binding index')
        refs=b.get('refs')
        if not isinstance(refs,list) or not refs or any(not isinstance(r,str) or r not in by_id for r in refs) or len(set(refs))!=len(refs):
            raise AnswerError('Binding refs invalid')
        for r in refs:
            if not by_id[r]['row_header'].strip() or not by_id[r]['col_header'].strip():raise AnswerError('Binding requires row and column identity')
        by_index[index]=refs
    for index in indexes:
        pp=[p for p in plans if p.get('index')==index]
        refs=by_index[index]
        if pp:
            if len(pp)!=1 or pp[0]['refs']!=refs:raise AnswerError('Binding must preserve ordered calculation refs')
        else:
            value=answer[index] if isinstance(answer,list) else answer
            if len(refs)!=1 or not leaf_equal(value,by_id[refs[0]]['raw']):raise AnswerError('Extracted value differs from bound source text')
    return bindings


def normalize_bound(raw,question,pages):
    obj=parse_object(raw)
    answer,evidence,plans=normalize_evidenced(raw,question,pages)
    if not answer:raise AnswerError('Blank reread answer')
    bindings=validate_bindings(obj,answer,evidence,plans)
    return {'answer':answer,'evidence':evidence,'plans':plans,'answer_bindings':bindings}


def bind_training_example(e):
    e=copy.deepcopy(e);obj=e['output'];answer=obj['answer']
    if isinstance(answer,list) and any(isinstance(v,(dict,list)) for v in answer):return None
    indices=list(range(len(answer))) if isinstance(answer,list) else [None]
    bindings=[]
    for i in indices:
        plans=[p for p in obj['plans'] if p.get('index')==i]
        if plans:refs=plans[0]['refs']
        else:
            v=answer[i] if isinstance(answer,list) else answer
            matches=[x['id'] for x in obj['evidence'] if _training_key(v)==_training_key(x['raw'])]
            if len(matches)!=1:return None
            refs=matches
        bindings.append({'index':i,'refs':refs})
    obj['answer_bindings']=bindings
    try:validate_bindings(obj,str(answer),obj['evidence'],obj['plans'])
    except (ValueError,KeyError,TypeError):return None
    return e


def tags(text):
    patterns={
      'blank':r'空白|空格|备注|编号|blank|empty|code',
      'unit':r'单位|万元|亿元|百分|增长|率|percent|ratio|million|billion|growth',
      'aggregate':r'合计|之和|总额|平均|sum|total|average|how many',
      'scope':r'依次|分别|顺序|前|后|之前|之后|before|after|which|list|all',
      'header':r'表头|列|本期|上期|年度|year|column|header',
      'comparison':r'最高|最低|最大|最小|最多|差|highest|lowest|largest|smallest|more|less|difference'}
    return {name for name,pat in patterns.items() if re.search(pat,text,re.I)}


def specialized_examples(question,bank,doc_hash,group=''):
    wanted=tags(question.question);words=tokens(question.question);ranked=[]
    for e in bank:
        if e.get('split')!='train' or not e.get('verified'):raise ValueError('Reread demos must be verified training examples')
        if e['image_sha256']==doc_hash or e['document_group']==group:continue
        bound=bind_training_example(e)
        if bound is None:continue
        score=4*len(wanted&tags(e['question']))+2*(e['question_type']==question.question_type)+len(words&tokens(e['question']))/max(1,len(words|tokens(e['question'])))
        ranked.append((-score,hashlib.sha256(e['id'].encode()).hexdigest(),bound))
    result=[];groups=set()
    for _,__,e in sorted(ranked,key=lambda x:(x[0],x[1])):
        if e['document_group'] in groups:continue
        result.append(e);groups.add(e['document_group'])
        if len(result)==2:break
    return result


def reread_messages(question,doc,root,examples=()):
    # There is intentionally NO parameter for candidate/reference/IR/target gold.
    text=prompt(question)+'\n'+BINDINGS_PROMPT
    if examples:text+='\n'+demonstration_context(examples)
    return [{'role':'user','content':[{'type':'text','text':text},*views(doc,root,local=True,ir=None,max_crops=4)]}]


def decide(question,baseline,candidate,reread):
    if not candidate or equivalent(question,baseline,candidate):
        return {'answer':baseline,'route':'baseline_agreement'}
    if reread and reread.get('valid') and equivalent(question,candidate,reread['answer']):
        return {'answer':candidate,'route':'confirmed_candidate'}
    return {'answer':baseline,'route':'baseline_unconfirmed'}
