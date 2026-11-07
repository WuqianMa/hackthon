"""Accounting/state regressions for the V5 overlay; no archives or labels read."""
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace
import json
import sys
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parent.parent))

from policy import propose


def item(iid='ARI-1',currency='EUR',facts=None,terms=''):
    return dict(iid=iid,currency=currency,total=10000,initial=10000,issue='2025-07-01',
                side='AP' if iid.startswith('API') else 'AR',terms=terms,facts=json.dumps(facts or {}))


def context(i,remaining=10000,reliable=True,terms=None):
    c=SimpleNamespace(item=lambda iid:i if iid==i['iid'] else None,terms=terms or {})
    l=SimpleNamespace(balance=lambda iid:remaining,confident=lambda iid:reliable)
    return c,l


def bank(amount='95.00',text='',booking='2025-07-10',currency='EUR',**kwargs):
    return dict(bank_txn_id='B',amount=amount,text=text,booking_date=booking,currency=currency,**kwargs)


class PolicyTests(unittest.TestCase):
    def test_retention_restores_cash_and_partial_without_mutation(self):
        i=item(facts={'retention':True});c,l=context(i)
        rows=[['B','ARI-1','100.00','','']];original=deepcopy(rows)
        out,reason=propose(bank(),rows,[['B','ARI-1','95.00','','PARTIAL']],c,l)
        self.assertEqual(out,[['B','ARI-1','95.00','','PARTIAL']]);self.assertEqual(rows,original)
        self.assertIn('document_plan_retention_or_advance',reason)

    def test_retention_release_does_not_reopen_partial(self):
        c,l=context(item(facts={'retention':True}),remaining=500)
        out,_=propose(bank('5.00','RETENTION RELEASE'),[['B','ARI-1','5.00','','PARTIAL']],
                      [['B','ARI-1','5.00','','']],c,l)
        self.assertEqual(out[0][4],'')

    def test_supported_liberacion_clears_cash_with_uncertain_history(self):
        c,l=context(item(facts={'retention':True}),remaining=10000,reliable=False)
        out,_=propose(bank('5.00','LIBERACION GARANTIA'),[['B','ARI-1','100.00','','PARTIAL']],
                      [['B','ARI-1','5.00','','']],c,l,'references:single')
        self.assertEqual(out[0][2:],[ '5.00','',''])

    def test_v3_v4_agreement_is_outside_first_policy_overlay(self):
        c,l=context(item(facts={'retention':True}),remaining=10000,reliable=False)
        same=[['B','ARI-1','5.00','','']]
        self.assertIsNone(propose(bank('5.00'),same,same,c,l,'references:single'))

    def test_late_discount_is_cash_partial(self):
        i=item(terms='D2');c,l=context(i,terms={'D2':dict(early_payment_discount_pct='2',discount_days='10')})
        out,reason=propose(bank('98.00',booking='2025-07-15'),[['B','ARI-1','100.00','','SHORT_DISCOUNT']],
                           [['B','ARI-1','98.00','','PARTIAL']],c,l)
        self.assertEqual(out[0][2:],[ '98.00','','PARTIAL']);self.assertIn('late_discount',reason)

    def test_discount_grace_boundary_fully_clears(self):
        i=item(terms='D2');c,l=context(i,terms={'D2':dict(early_payment_discount_pct='2',discount_days='10')})
        out,_=propose(bank('98.00',booking='2025-07-14'),[['B','ARI-1','98.00','','PARTIAL']],
                      [['B','ARI-1','100.00','','SHORT_DISCOUNT']],c,l)
        self.assertEqual(out[0][2:],[ '100.00','','SHORT_DISCOUNT'])

    def test_ap_partial_requires_source_or_explicit_evidence(self):
        c,l=context(item('API-1'));t=bank('-50.00')
        now=[['B','API-1','100.00','','']];old=[['B','API-1','50.00','','PARTIAL']]
        self.assertIsNone(propose(t,now,old,c,l,'v3:party_ranked'))
        out,_=propose(t,now,old,c,l,'structured:payment_runs')
        self.assertEqual(out[0][2:],[ '50.00','','PARTIAL'])

    def test_last_instalment_keeps_final_empty_exception(self):
        i=item(facts={'tranches':[3000,3000,4000]});c,l=context(i,remaining=4000)
        out,_=propose(bank('40.00','PAYMENT 3/3'),[['B','ARI-1','40.00','','PARTIAL']],
                      [['B','ARI-1','40.00','','']],c,l)
        self.assertEqual(out[0][4],'')

    def test_new_ml_item_is_retained_and_gets_own_clause_policy(self):
        c,l=context(item(facts={'advance':True}))
        out,_=propose(bank('75.00'),[['B','ARI-1','100.00','','']],
                      [['B','ARI-WRONG','75.00','','']],c,l)
        self.assertEqual(out[0][1:],[ 'ARI-1','75.00','','PARTIAL'])

    def test_cross_currency_partial_requires_actual_original_amount(self):
        c,l=context(item(currency='USD',facts={'retention':True}))
        rows=[['B','ARI-1','100.00','','']];old=[['B','ARI-1','95.00','','PARTIAL']]
        self.assertIsNone(propose(bank('85.00'),rows,old,c,l))
        out,_=propose(bank('85.00',orig_currency='USD',orig_amount='95.00'),rows,old,c,l)
        self.assertEqual(out[0][2],'95.00');self.assertEqual(out[0][4],'PARTIAL')

    def test_return_decision_preserved(self):
        c,l=context(item(facts={'retention':True}))
        self.assertIsNone(propose(bank('-95.00','RETURNED DD'),[['B','ARI-1','95.00','','RETURNED']],
                                  [['B','ARI-1','95.00','','PARTIAL']],c,l))

    def test_no_speculative_group_cash_reallocation(self):
        c,l=context(item('API-1'))
        now=[['B','API-1','100.00','',''],['B','API-2','20.00','','']]
        old=[['B','API-1','50.00','','PARTIAL'],['B','API-OTHER','70.00','','']]
        self.assertIsNone(propose(bank('-120.00'),now,old,c,l,'structured:payment_runs'))

    def test_duplicate_cash_is_not_clamped(self):
        c,l=context(item(),remaining=0)
        out,_=propose(bank('105.00'),[['B','ARI-1','105.00','','']],
                      [['B','ARI-1','105.00','','DUPLICATE_PAYMENT']],c,l,'references:single')
        self.assertEqual(out[0][2:],[ '105.00','','DUPLICATE_PAYMENT'])


if __name__=='__main__':unittest.main()
