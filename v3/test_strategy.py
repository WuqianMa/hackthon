import csv
import json
import tempfile
import unittest
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
from .engine import Engine
from .sources import Sources
from bankrec.sources import Group


def item(**kwargs):
    r=dict(iid='ARI-2025-0000001',entity='ES01',party='C1',currency='EUR',issue='2025-01-01',
           balance=90000,total=90000,facts='{}',terms='')
    r.update(kwargs)
    return r


def bank(**kwargs):
    r=dict(bank_txn_id='BT-2025-0000001',entity='ES01',account_id='ES01-X-EUR',currency='EUR',
           booking_date='2025-06-02',amount='300.00',text='',ref1='',ref2='',remittance_info='',end_to_end_id='')
    r.update(kwargs)
    return r


class StrategyTests(unittest.TestCase):
    def engine(self,sources=None):
        c=SimpleNamespace(terms={},party_info={},metadata={},rate=lambda *_:Decimal(1))
        return Engine(c,sources)

    def test_mail_deduction_is_subtracted(self):
        text='Subject: Payment advice REF123456\nPayment 900.00 EUR on 06/02/2025\nINV123456 01/05/25 1,000.00 -100.00 DAMAGED GOODS\nKind regards'
        e=Sources.text_advice(text)[3][0]
        self.assertEqual((e['gross'],e['paid'],e['reason']),(100000,90000,'DAMAGED GOODS'))

    def test_final_instalment(self):
        self.assertEqual(self.engine().policy(item(),30000,bank(text='RATE 3/3')), (30000,''))

    def test_nonfinal_instalment(self):
        self.assertEqual(self.engine().policy(item(),30000,bank(text='RATE 1/3')), (30000,'PARTIAL'))

    def test_final_marker_does_not_reclear_closed_item(self):
        self.assertEqual(self.engine().policy(item(balance=0),30000,bank(text='RATE 3/3')), (30000,'DUPLICATE_PAYMENT'))

    def test_fx_partial_keeps_partial(self):
        self.assertEqual(self.engine().policy(item(currency='USD'),30000,bank()),(30000,'PARTIAL'))

    def test_residual_never_reuses_an_item(self):
        self.assertIsNone(Engine.small_residual([item(balance=500)],1000))
        found=Engine.small_residual([item(balance=250),item(iid='ARI-2025-0000002',balance=750)],1000)
        self.assertEqual(len(found),2)

    def test_partial_container_does_not_discard_known_item(self):
        g=Group('R1','remittance','advice.csv','2025-06-02','EUR',100000,'','ES01',
                [{'doc':'A','paid':40000},{'doc':'B','paid':60000}],{'REF123456'})
        engine=self.engine(SimpleNamespace(candidates=lambda _: [g]))
        engine.resolve_entry=lambda e,*_:item(balance=40000,total=40000) if e['doc']=='A' else None
        result=engine.structured(bank(amount='1000.00',text='REF123456'))
        self.assertEqual(result[0],[('ARI-2025-0000001',40000,'')])
        self.assertEqual(result[1]['method'],'v3:partial_container')

    def test_nested_confirming_transfer_total(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);(root/'payment_runs').mkdir()
            fields=['run_id','run_type','execution_date','debtor_account_id','end_to_end_id','beneficiary','beneficiary_iban','currency','transfer_amount','document_number','document_type','document_amount','remittance_info']
            with (root/'payment_runs/run.csv').open('w',newline='') as f:
                w=csv.writer(f);w.writerow(fields)
                for doc,amount in [('INV1','611.91'),('INV2','639.90')]:
                    w.writerow(['RUN123456','confirming','2025-06-10','ES01-X-EUR','E2E123456','Supplier','','EUR','1251.81',doc,'INVOICE',amount,''])
            with (root/'ap_invoices.csv').open('w',newline='') as f:
                w=csv.writer(f)
                w.writerow(['supplier_invoice_number','supplier_name','currency','due_date'])
                w.writerow(['INV1','Supplier','EUR','2025-05-02'])
                w.writerow(['INV2','Supplier','EUR','2025-06-02'])
            s=Sources(root,root/'cache')
            transfers=[g for g in s.groups.values() if g.key.startswith('transfer-unit:')]
            self.assertEqual(len(transfers),1)
            self.assertEqual(transfers[0].cash,-125181)
            self.assertEqual(len(transfers[0].entries),2)
            maturity=[g for g in s.groups.values() if g.key.startswith('maturity:')]
            self.assertEqual(maturity[0].date,'2025-06-02')
            self.assertEqual(maturity[0].cash,-125181)

    def test_speculative_hypothesis_does_not_consume_later_balance(self):
        engine=self.engine()
        engine.speculative=True
        events=[]
        engine.c.identify=lambda *a,**k:set()
        engine.c.by_party=lambda *a:[]
        engine.c.apply=lambda *args:events.append(args)
        engine.structured=lambda t:([('ARI-2025-0000001',30000,'')],{'method':'v3:speculative_prefix'})
        rows,_=engine.reconcile(bank())
        self.assertEqual(len(rows),1)
        self.assertEqual(events,[])

    def test_supported_hypothesis_commits_balance(self):
        engine=self.engine()
        engine.speculative=True
        events=[]
        engine.c.identify=lambda *a,**k:set()
        engine.c.by_party=lambda *a:[]
        engine.c.apply=lambda *args:events.append(args)
        engine.structured=lambda t:([('ARI-2025-0000001',30000,'')],{'method':'structured:remittance'})
        engine.reconcile(bank())
        self.assertEqual(events,[('ARI-2025-0000001',30000,'')])

    def test_export_rows_have_stable_item_order(self):
        engine=self.engine()
        engine.c.identify=lambda *a,**k:set()
        engine.c.by_party=lambda *a:[]
        engine.c.apply=lambda *a:None
        engine.structured=lambda t:([('ARI-2025-0000002',20000,''),('ARI-2025-0000001',10000,'')],{'method':'structured:remittance'})
        result=engine.reconcile(bank())[0]
        self.assertEqual([r[1] for r in result],['ARI-2025-0000001','ARI-2025-0000002'])


if __name__=='__main__':
    unittest.main()
