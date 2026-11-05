import copy
import json
from pathlib import Path
from types import SimpleNamespace
import unittest
import tempfile
from unittest.mock import patch

from tableledger.scope_guard import contract, audit, normalize_scope, scope_messages, choose
from tableledger.xlsxio import Question
from tableledger.evidence import execute_plan


class ScopeGuardTests(unittest.TestCase):
    def setUp(self):
        self.q = Question('q', 'x.png', 'extract', '请依次提取甲部服务A、乙部服务B的本期金额，保留原单位。', answer_format='json_array')
        self.obj = {'answer': ['0', ''], 'plans': [], 'answer_bindings': [{'index': 0, 'refs': ['e1']}, {'index': 1, 'refs': ['e2']}],
                    'evidence': [self.cell('e1', '0', ['甲部', '服务A']), self.cell('e2', '', ['乙部', '服务B'])]}

    def cell(self, ident, raw, row):
        return {'id': ident, 'raw': raw, 'page': 1, 'bbox': [0, 0, 200, 200], 'unit': '元',
                'row_path': row, 'row_header': ' / '.join(row), 'col_path': ['本期', '金额'],
                'col_header': '本期 / 金额', 'cell_state': 'blank' if raw == '' else 'value'}

    def test_count_and_order_come_from_question_not_prediction(self):
        c = contract(self.q)
        self.assertEqual(c['expected_count'], 2)
        self.assertEqual(c['targets'], ['甲部服务A', '乙部服务B'])
        self.assertIn('answer_length', audit(self.q, '["0"]', self.obj['evidence'], [])['flags'])
        self.assertIn('requested_row_path', audit(self.q, '["","0"]', self.obj['evidence'], [])['flags'])
        self.assertEqual(json.loads(normalize_scope(json.dumps(self.obj), self.q, 1)['answer']), ['0', ''])

    def test_ambiguous_range_does_not_invent_count(self):
        for text in ['提取前3行、后2列的金额', '请分别提取甲和乙、丙的金额', '请提取2026年全部月份金额']:
            self.assertIsNone(contract(Question('q','x','extract',text))['expected_count'])

    def test_period_leaf_and_blank_are_independently_checked(self):
        for edit in ('period', 'flat', 'blank', 'row', 'length'):
            obj = copy.deepcopy(self.obj)
            if edit == 'period':
                obj['evidence'][0].update(col_path=['上期','金额'], col_header='上期 / 金额')
            if edit == 'flat': obj['evidence'][0]['col_path'] = ['本期金额']
            if edit == 'blank': obj['evidence'][1]['cell_state'] = 'value'
            if edit == 'row':
                obj['evidence'][0].update(row_path=['乙部','服务A'], row_header='乙部 / 服务A')
            if edit == 'length':
                obj['answer'].pop();obj['answer_bindings'].pop()
            with self.assertRaises(ValueError, msg=edit): normalize_scope(json.dumps(obj), self.q, 1)

    def test_equal_answers_can_still_trigger_missing_scope(self):
        obj = copy.deepcopy(self.obj)
        obj['evidence'][0]['col_header'] = '金额'
        self.assertIn('requested_column_path', audit(self.q, '["0",""]', obj['evidence'], [])['flags'])
        q = Question('q','x','extract','请列出全部明细项目')
        self.assertIn('scope_coverage_unverified', audit(q, '甲', [self.cell('a','甲',['甲'])], [])['flags'])
        for text in ['Which country has the highest value?', 'What is the total expense?', 'How many projects exist?']:
            self.assertTrue(contract(Question('q','x','thinking',text))['coverage_required'])

    def test_inventory_requires_exact_evidence_coverage(self):
        q=Question('q','x','extract','请列出全部明细金额',answer_format='json_array')
        obj=copy.deepcopy(self.obj)
        obj['scope_inventory']=[{'row_path':e['row_path'],'included':True,'reason':'明细','refs':[e['id']]} for e in obj['evidence']]
        normalize_scope(json.dumps(obj),q,1)
        obj['scope_inventory'].pop()
        with self.assertRaises(ValueError):normalize_scope(json.dumps(obj),q,1)

    def test_excluded_row_rejected_for_extraction_too(self):
        q=Question('q','x','extract','提取金额，不包含小计和合计',answer_format='json_array')
        obj=copy.deepcopy(self.obj)
        obj['evidence'][0].update(row_path=['合计'],row_header='合计')
        with self.assertRaises(ValueError):normalize_scope(json.dumps(obj),q,1)

    def test_duplicate_logical_operand_and_excluded_total_rejected(self):
        q=Question('q','x','thinking','计算金额之和，不包含小计和合计',answer_format='number')
        obj=copy.deepcopy(self.obj);obj['answer']='0'
        obj['evidence'][1]=self.cell('e2','5',['甲部','服务A'])
        obj['plans']=[{'index':None,'op':'sum','refs':['e1','e2']}]
        obj['answer_bindings']=[{'index':None,'refs':['e1','e2']}]
        with self.assertRaises(ValueError):normalize_scope(json.dumps(obj),q,1)
        obj['evidence'][1]=self.cell('e2','5',['合计'])
        with self.assertRaises(ValueError):normalize_scope(json.dumps(obj),q,1)

    def test_reread_inputs_exclude_old_answers_and_ir(self):
        q=SimpleNamespace(question=self.q.question,question_type='extract',answer_format='json_array',file_name='x',table_hint='',
                          candidate='SECRET_CANDIDATE',expected='SECRET_GOLD',transcript='SECRET_IR')
        with patch('tableledger.blind_review.views',return_value=[]):
            self.assertNotIn('SECRET',json.dumps(scope_messages(q,None,Path('/tmp'))))

    def test_no_single_reader_auto_replacement(self):
        self.assertEqual(choose(self.q,'[1,2]',{'valid':True,'answer':'[3,4]'})['answer'],'[1,2]')
        self.assertEqual(choose(self.q,'[1,2]',{'valid':True,'answer':'[3,4]'}, {'valid':True,'answer':'[3,4]'})['answer'],'[3,4]')

    def test_raw_monetary_units_cannot_be_overridden_or_hidden(self):
        plan=[{'op':'sum','index':None,'refs':['a','b']}]
        evidence={'a':{'raw':'1万元','unit':'万元'},'b':{'raw':'2元','unit':'万元'}}
        with self.assertRaises(ValueError):execute_plan('0',plan,evidence)
        evidence['a']['unit']='';evidence['b']['unit']=''
        with self.assertRaises(ValueError):execute_plan('0',plan,evidence)
        evidence['b']['raw']='2万元'
        self.assertEqual(execute_plan('0',plan,evidence),'3')



if __name__ == '__main__': unittest.main()
