import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from types import SimpleNamespace

from tableledger.blind_review import normalize_bound,reread_messages,decide,leaf_equal
from tableledger.xlsxio import Question


class BlindReviewTests(unittest.TestCase):
    def setUp(self):
        self.q=Question('q','x.png','extract','按甲乙顺序提取编号','', 'json_array')
        self.obj={'answer':['001',''],'evidence':[
          {'id':'e1','raw':'001','page':1,'bbox':[0,0,200,200],'row_header':'甲','col_header':'编号','unit':''},
          {'id':'e2','raw':'','page':1,'bbox':[0,200,200,400],'row_header':'乙','col_header':'编号','unit':''}],
          'plans':[],'answer_bindings':[{'index':0,'refs':['e1']},{'index':1,'refs':['e2']}]}

    def test_preserves_empty_and_identifiers(self):
        r=normalize_bound(json.dumps(self.obj),self.q,1)
        self.assertEqual(json.loads(r['answer']),['001',''])
        self.assertFalse(leaf_equal('001','1'))
        self.assertTrue(leaf_equal('1,250.00','1250'))
        self.assertFalse(leaf_equal('12%','.12'))
        self.assertTrue(leaf_equal('$ (5,135)','-5135'))
        self.assertTrue(leaf_equal('$ 1.30','$1.30'))
        self.assertFalse(leaf_equal('$100','€100'))
        self.assertFalse(leaf_equal('1万元','10000'))
        self.assertFalse(leaf_equal('(100)','100'))

    def test_missing_misbound_or_duplicate_array_element_rejected(self):
        for edit in ('missing','wrong','duplicate','identity'):
            obj=copy.deepcopy(self.obj)
            if edit=='missing':obj['answer_bindings'].pop()
            if edit=='wrong':obj['answer_bindings'][1]['refs']=['e1']
            if edit=='duplicate':obj['answer_bindings'][1]['index']=0
            if edit=='identity':obj['evidence'][0]['col_header']=''
            with self.assertRaises(ValueError):normalize_bound(json.dumps(obj),self.q,1)

    def test_compute_refs_and_operand_order_required(self):
        obj=copy.deepcopy(self.obj);obj['answer']='0'
        obj['evidence'][0]['raw']='10';obj['evidence'][1]['raw']='3'
        obj['plans']=[{'index':None,'op':'subtract','refs':['e1','e2']}]
        obj['answer_bindings']=[{'index':None,'refs':['e1','e2']}]
        q=Question('n','x.png','thinking','计算差额',answer_format='number')
        self.assertEqual(normalize_bound(json.dumps(obj),q,1)['answer'],'7')
        obj['answer_bindings'][0]['refs'].reverse()
        with self.assertRaises(ValueError):normalize_bound(json.dumps(obj),q,1)

    def test_rereader_cannot_see_candidate_gold_or_transcript(self):
        q=SimpleNamespace(question='取值',file_name='x.png',table_hint='',answer_format='text',question_type='extract',
             expected='SECRET_GOLD',candidate='SECRET_CANDIDATE',transcript='SECRET_IR')
        with patch('tableledger.blind_review.views',return_value=[{'type':'text','text':'ORIGINAL_IMAGE'}]):
            text=json.dumps(reread_messages(q,None,Path('/tmp')))
        self.assertNotIn('SECRET',text)
        self.assertIn('ORIGINAL_IMAGE',text)

    def test_only_valid_independent_support_can_replace(self):
        q=Question('n','x.png','extract','取值',answer_format='number')
        for reader in (None,{'valid':False,'answer':'2'},{'valid':True,'answer':'3'}):
            self.assertEqual(decide(q,'1','2',reader)['answer'],'1')
        self.assertEqual(decide(q,'1','2',{'valid':True,'answer':'2'})['answer'],'2')

    def test_calculation_cannot_hide_array_behind_scalar_binding(self):
        obj=copy.deepcopy(self.obj);obj['answer']='placeholder'
        obj['evidence'][0]['raw']='10';obj['evidence'][1]['raw']='10'
        obj['plans']=[{'index':None,'op':'argmax','refs':['e1','e2']}]
        obj['answer_bindings']=[{'index':None,'refs':['e1','e2']}]
        q=Question('n','x.png','thinking','返回并列最高项',answer_format='text')
        with self.assertRaises(ValueError):normalize_bound(json.dumps(obj),q,1)


if __name__=='__main__':unittest.main()
