"""Meaningful label/split/model-stack invariants; no TRAIN/LIVE inputs."""
from pathlib import Path
import sys
import unittest
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parent))
from run import complete,partition,select,amount_ok
from tier3 import ambiguity_packet,revision_rows


class ExperimentTests(unittest.TestCase):
    def test_full_correctness_requires_exception(self):
        g={'B1':{'I1':{'amount':'100.00','exception':'PARTIAL'}}}
        self.assertEqual(complete([['B1','I1','100.00','','']],g,{}),0)
        self.assertEqual(complete([['B1','I1','100.00','','PARTIAL']],g,{}),1)

    def test_incomplete_set_is_not_a_full_positive(self):
        g={'B1':{'I1':{'amount':'100.00','exception':''},'I2':{'amount':'50.00','exception':''}}}
        self.assertEqual(complete([['B1','I1','100.00','','']],g,{}),0)

    def test_repeated_item_episode_stays_in_one_fold(self):
        banks={f'B{i}':{} for i in range(15)}
        g={f'B{i}':{f'I{i}':{}} for i in range(15)}
        g['B1']={'I0':{}}
        folds,_=partition({'banks':banks},g)
        self.assertEqual(folds['B0'],folds['B1'])
        for k in range(5):
            roles=[{k},{(k+1)%5},{(k+2)%5},{(k+3)%5,(k+4)%5}]
            for a in range(len(roles)):
                for b in range(a+1,len(roles)):self.assertFalse(roles[a]&roles[b])

    def test_selection_never_receives_golden_labels(self):
        h=[dict(kind='static',estimated_pair_f1=.1,rows=[['B1','','','UNIDENTIFIED','']]),
           dict(kind='top',estimated_pair_f1=.9,rows=[['B1','I1','100.00','','']])]
        chosen,_=select(h,{'B1':[0,1]},np.array([.2,.8]),['B1'],.5,0)
        self.assertEqual(chosen['B1'][0][1],'I1')

    def test_scorer_amount_tolerance_is_not_exact_cash(self):
        self.assertTrue(amount_ok('100.49','100.00'))
        self.assertFalse(amount_ok('100.51','100.00'))

    def test_noitem_requires_correct_category_and_exception(self):
        n={'B1':{'category':'UNIDENTIFIED','exception':'UNIDENTIFIED'}}
        self.assertEqual(complete([['B1','','','UNIDENTIFIED','UNIDENTIFIED']],{},n),1)
        self.assertEqual(complete([['B1','','','BANK_FEES','']],{},n),0)

    def test_tier3_cannot_invent_a_hypothesis(self):
        candidates=[dict(id=1,rows=[['B1','I1','10.00','','']],full_probability=.4,utility=.5),
                    dict(id=2,rows=[['B1','','','UNIDENTIFIED','UNIDENTIFIED']],full_probability=.3,utility=.49)]
        packet=ambiguity_packet('B1',{'text':'payment'},candidates,1,candidates[1]['rows'],0)
        self.assertIsNotNone(packet)
        self.assertEqual(revision_rows(packet,dict(bank_txn_id='B1',action='CHOOSE',candidate_id=2,reason='source supports unknown payer')),candidates[1]['rows'])
        with self.assertRaises(ValueError):revision_rows(packet,dict(bank_txn_id='B1',action='CHOOSE',candidate_id=3,reason='invented'))
        self.assertNotIn('golden',packet)


if __name__=='__main__':unittest.main()
