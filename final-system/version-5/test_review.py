"""LLM revision boundary and fact-regeneration checks with synthetic packets only."""
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace
import sys
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parent.parent))

from review import apply_decisions


class ReviewTests(unittest.TestCase):
    def setUp(self):
        self.items={
            'ARI-1':dict(iid='ARI-1',currency='EUR',total=10000,issue='2025-07-01'),
            'ARI-2':dict(iid='ARI-2',currency='EUR',total=10000,issue='2025-07-01'),
        }
        self.catalog=SimpleNamespace(item=lambda iid:self.items.get(iid))
        self.incumbent=[['B','ARI-2','100.00','','']]
        self.predictions={'B':deepcopy(self.incumbent)}
        self.bank=dict(bank_txn_id='B',booking_date='2025-07-15',currency='EUR',
                       amount='100.00',text='MAINTENANCE JUNE 2025')
        self.packet=dict(
            packet_sha256='packet-v1',bank=self.bank,
            candidates=[
                dict(id='incumbent',rows=deepcopy(self.incumbent)),
                dict(id='june-service',rows=[['B','ARI-1','100.00','','']]),
                dict(id='invalid-total',rows=[['B','ARI-1','105.00','','']]),
                dict(id='valid-duplicate',rows=[['B','ARI-1','105.00','','DUPLICATE_PAYMENT']]),
            ],
            items=[dict(item_id='ARI-1',issue='2025-07-01',balance_before='100.00',
                        cached_text='Invoice INV-123. Service period JUNE 2025. Total EUR 100.00.')],
        )
        self.packets={'B':self.packet}

    def decision(self,action,**values):
        return dict(bank_txn_id='B',packet_sha256='packet-v1',action=action,
                    reason='Synthetic source supports this interpretation',**values)

    def apply(self,decision):
        return apply_decisions(self.predictions,self.packets,[decision],self.catalog)

    def test_valid_choose_applies_listed_candidate(self):
        audit=self.apply(self.decision('CHOOSE',candidate_id='june-service'))
        self.assertEqual(self.predictions['B'],[['B','ARI-1','100.00','','']])
        self.assertTrue(audit[0]['changed'])
        self.assertFalse(audit[0]['regenerated'])
        self.assertEqual(audit[0]['before'],self.incumbent)

    def test_keep_and_abstain_preserve_incumbent(self):
        for action in ('KEEP','ABSTAIN'):
            with self.subTest(action=action):
                self.predictions={'B':deepcopy(self.incumbent)}
                original=self.predictions['B']
                audit=self.apply(self.decision(action))
                self.assertIs(self.predictions['B'],original)
                self.assertFalse(audit[0]['changed'])
                self.assertFalse(audit[0]['regenerated'])

    def test_stale_packet_rejected_without_changing_prediction(self):
        decision=self.decision('CHOOSE',candidate_id='june-service')
        decision['packet_sha256']='obsolete-packet'
        with self.assertRaisesRegex(ValueError,'Stale LLM packet'):self.apply(decision)
        self.assertEqual(self.predictions['B'],self.incumbent)

    def test_unknown_candidate_rejected(self):
        with self.assertRaisesRegex(ValueError,'Unknown LLM candidate'):
            self.apply(self.decision('CHOOSE',candidate_id='invented-candidate'))
        self.assertEqual(self.predictions['B'],self.incumbent)

    def test_nonduplicate_above_document_total_rejected(self):
        with self.assertRaisesRegex(ValueError,'exceeds document total'):
            self.apply(self.decision('CHOOSE',candidate_id='invalid-total'))
        self.assertEqual(self.predictions['B'],self.incumbent)

    def test_duplicate_cash_above_document_total_remains_eligible(self):
        self.apply(self.decision('CHOOSE',candidate_id='valid-duplicate'))
        self.assertEqual(self.predictions['B'][0][2:],[ '105.00','','DUPLICATE_PAYMENT'])

    def test_service_period_fact_regenerates_known_item_and_exact_cash(self):
        audit=self.apply(self.decision('EXTRACT_FACT',fact=dict(
            kind='service_period',item_id='ARI-1',value='2025-06',quote='Service period JUNE 2025.')))
        self.assertEqual(self.predictions['B'],[['B','ARI-1','100.00','','']])
        self.assertTrue(audit[0]['regenerated'])
        self.assertTrue(audit[0]['changed'])

    def test_fact_quote_must_appear_verbatim_in_cached_text(self):
        with self.assertRaisesRegex(ValueError,'Unverifiable fact span'):
            self.apply(self.decision('EXTRACT_FACT',fact=dict(
                kind='service_period',item_id='ARI-1',value='2025-06',quote='June service as approved by customer')))
        self.assertEqual(self.predictions['B'],self.incumbent)

    def test_quote_must_establish_the_claimed_period(self):
        self.packet['items'][0]['cached_text']='Service period JULY 2025.'
        with self.assertRaisesRegex(ValueError,'not established by source span'):
            self.apply(self.decision('EXTRACT_FACT',fact=dict(
                kind='service_period',item_id='ARI-1',value='2025-06',quote='Service period JULY 2025.')))
        self.assertEqual(self.predictions['B'],self.incumbent)

    def test_fact_regeneration_does_not_invent_missing_cash(self):
        self.packet['items'][0]['balance_before']='90.00'
        with self.assertRaisesRegex(ValueError,'unsupported amount'):
            self.apply(self.decision('EXTRACT_FACT',fact=dict(
                kind='service_period',item_id='ARI-1',value='2025-06',quote='Service period JUNE 2025.')))
        self.assertEqual(self.predictions['B'],self.incumbent)


if __name__=='__main__':unittest.main()
