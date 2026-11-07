from pathlib import Path
import sys
import unittest
import sqlite3
from decimal import Decimal

ROOT=Path(__file__).resolve().parent.parent
sys.path.insert(0,str(ROOT));sys.path.insert(0,str(ROOT/'version-5'))
from mechanisms import parse_facts,number,return_kind,service_month,SourceIndex,single_policy,documented_advance,referenced_partial_group,retrieved_fee
from bankrec.io import norm


def bank(**kw):
    t=dict(bank_txn_id='B1',amount='100.00',currency='EUR',entity='ES01',account_id='A',booking_date='2025-08-15',text='',counterparty_name='C1',bank_code='')
    t.update(kw);return t


def item(**kw):
    i=dict(iid='ARI-1',party='C1',entity='ES01',currency='EUR',side='AR',doc='FV-25-1234567',issue='2025-08-01',total=10000,initial=10000,facts='{}')
    i.update(kw);return i


class Catalog:
    def __init__(self,items):
        self.items=items;self.party_info={'C1':{'country':'US','invoice_currency':'EUR'}};self.terms={}
        self.db=sqlite3.connect(':memory:');self.db.row_factory=sqlite3.Row
        self.db.execute('CREATE TABLE items(iid TEXT,party TEXT,currency TEXT,total INTEGER,issue TEXT)')
        self.db.executemany('INSERT INTO items VALUES(?,?,?,?,?)',[(i['iid'],i['party'],i['currency'],i['total'],i['issue']) for i in items])
    def identify(self,*args,**kwargs):return {'C1'}
    def item(self,iid):return next((i for i in self.items if i['iid']==iid),None)
    def by_party(self,parties,booking):return [i for i in self.items if i['party'] in parties and i['issue']<=booking]
    def lookup(self,ref,**kw):return [i for i in self.items if norm(i['doc'])==norm(ref)]
    def rate(self,*args):return Decimal('1')


class Ledger:
    def __init__(self,closed=(),balances=None):self.closed=closed;self.balances=balances or {}
    def balance(self,iid):return 0 if iid in self.closed else self.balances.get(iid,10000)


class MechanismTests(unittest.TestCase):
    def test_amount_locales_and_advance(self):
        self.assertEqual(number('1.008,08'),100808)
        self.assertEqual(number('1,008.08'),100808)
        f=parse_facts('Less advance received against proforma PF24-01: 1.008,08 BRL. Net amount due 2.352,20 BRL.')
        self.assertEqual(f['advance_net'],235220)
    def test_english_replacement(self):
        self.assertEqual(parse_facts('This invoice cancels and replaces invoice 1082423780 dated 10/10/2024. Do not pay both.')['replaces'],'1082423780')
    def test_typed_returns_and_direction(self):
        self.assertEqual(return_kind(bank(text='RETURN AC04 supplier PR010025081234-0001')),'ap')
        self.assertEqual(return_kind(bank(amount='-100.00',text='RETURNED ITEM CHK 5927225 NSF')),'cheque')
        self.assertEqual(return_kind(bank(amount='-100.00',text='CHARGEBACK ****7553 MID 888565688')),'card')
        self.assertEqual(return_kind(bank(text='TAX RETURN CREDIT')),'')
    def test_month_offset_and_compact_year(self):
        july=item();june=item(iid='ARI-2',issue='2025-07-01')
        c=Catalog([june,july]);r=service_month(bank(text='SERVICE JULY2025'),[['B1','ARI-2','100.00','','']],c,Ledger())
        self.assertEqual(r[0][0][1],'ARI-1')
    def test_month_never_reuses_closed_invoice_or_forces_tie(self):
        i=item();j=item(iid='ARI-2')
        self.assertIsNone(service_month(bank(text='SERVICE JULY 2025'),[],Catalog([i,j]),Ledger()))
        self.assertIsNone(service_month(bank(text='SERVICE JULY 2025'),[],Catalog([i]),Ledger(['ARI-1'])))
    def test_withholding_fully_clears(self):
        i=item(total=100000,initial=100000);c=Catalog([i]);c.party_info['C1']['country']='MX'
        r=single_policy(bank(amount='987.50'),[['B1','ARI-1','987.50','','PARTIAL']],c,Ledger())
        self.assertEqual(r[0][0][2:],[ '1000.00','','SHORT_WITHHOLDING'])
    def test_crossborder_charge_respects_both_limits(self):
        i=item(total=1000000,initial=1000000);c=Catalog([i])
        r=single_policy(bank(amount='9975.00',bank_code='PMNT/RCDT/XBCT'),[['B1','ARI-1','9975.00','','PARTIAL']],c,Ledger())
        self.assertEqual(r[0][0][-1],'SHORT_BANK_CHARGES')
        self.assertIsNone(single_policy(bank(amount='9900.00',bank_code='PMNT/RCDT/XBCT'),[['B1','ARI-1','9900.00','','PARTIAL']],c,Ledger()))
    def test_return_card_source_checks_merchant_and_gross(self):
        s=object.__new__(SourceIndex);s.c=Catalog([item()]);s.ap={};s.cheques={};s.cards={('A','7553'):[dict(merchant_id='888565688',gross='100.00',currency='EUR',settlement_date='2025-08-10',order_number='FV-25-1234567')]}
        s.resolve=lambda *args:item()
        self.assertIsNotNone(s.returned(bank(amount='-100.00',text='CHARGEBACK ****7553 MID 888565688')))
        self.assertIsNone(s.returned(bank(amount='-100.00',text='CHARGEBACK ****7553 MID 000000000')))
        self.assertIsNone(s.returned(bank(amount='-99.00',text='CHARGEBACK ****7553 MID 888565688')))
    def test_document_net_recovers_missing_advance_item_but_requires_party(self):
        i=item(facts='{"advance":true,"advance_net":6000}')
        c=Catalog([i]);c.advance_cash={('ES01','EUR',6000):{'ARI-1'}}
        r=documented_advance(bank(amount='60.00'),[['B1','','','UNIDENTIFIED','UNIDENTIFIED']],c,Ledger())
        self.assertEqual(r[0],[['B1','ARI-1','60.00','','PARTIAL']])
        c.items=[item(party='C2',facts=i['facts'])]
        self.assertIsNone(documented_advance(bank(amount='60.00'),[],c,Ledger()))
    def test_multi_reference_partial_is_cash_balanced_and_newest(self):
        old=item(doc='DOC1000010',issue='2025-06-01');new=item(iid='ARI-2',doc='DOC1000020',total=30000,initial=30000)
        c=Catalog([old,new]);ledger=Ledger(balances={'ARI-2':30000})
        r=referenced_partial_group(bank(amount='250.00',text='PAY DOC1000010 DOC1000020'),[],c,ledger)
        self.assertEqual(r[0],[['B1','ARI-1','100.00','',''],['B1','ARI-2','150.00','','PARTIAL']])
        self.assertIsNone(referenced_partial_group(bank(amount='247.00',text='PAY DOC1000010 DOC1000020'),[],c,ledger))
        self.assertIsNone(referenced_partial_group(bank(amount='250.00',text='PAY DOC1000020'),[],c,ledger))
    def test_fee_retrieval_preserves_withholding_and_exact_cash_incumbent(self):
        c=Catalog([item(total=1000000,initial=1000000)]);l=Ledger(balances={'ARI-1':1000000})
        t=bank(amount='9975.00',bank_code='PMNT/RCDT/XBCT')
        self.assertIsNotNone(retrieved_fee(t,[['B1','ARI-1','9975.00','','PARTIAL']],c,l))
        self.assertIsNone(retrieved_fee(t,[['B1','ARI-1','9975.00','','SHORT_WITHHOLDING']],c,l))
        self.assertIsNone(retrieved_fee(t,[['B1','ARI-1','9975.00','','']],c,l))
    def test_fee_retrieval_does_not_mine_unreferenced_old_invoice(self):
        c=Catalog([item(total=1000000,initial=1000000,issue='2023-01-01')]);l=Ledger(balances={'ARI-1':1000000})
        t=bank(amount='9975.00',bank_code='PMNT/RCDT/XBCT')
        self.assertIsNone(retrieved_fee(t,[['B1','','','UNIDENTIFIED','UNIDENTIFIED']],c,l))


if __name__=='__main__':unittest.main()
