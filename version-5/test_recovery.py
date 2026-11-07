from copy import deepcopy
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from bankrec.io import norm
from recovery import propose, service_period


class Catalog:
    def __init__(self, items=(), accounts=None):
        self.items = {i['iid']: i for i in items}
        self.bank_accounts = accounts or {}
        self.related = {}
        self.metadata = {}
    def item(self, iid): return deepcopy(self.items.get(iid))
    def identify(self, *args, **kwargs): return {'C1'}
    def by_party(self, parties, booking):
        return [deepcopy(i) for i in self.items.values() if i['party'] in parties and i['issue'] <= booking]
    def lookup(self, ref, **kwargs):
        return [deepcopy(i) for i in self.items.values() if norm(ref) in (norm(i['doc']), norm(i['facts'].get('replaces', '')))
                and not i['facts'].get('cancelled')]


class Ledger:
    def __init__(self, balances=None, original=None, paired=False):
        self.balances = balances or {}; self.original = original; self.paired = paired
    def balance(self, iid): return self.balances.get(iid, 10000)
    def confident(self, iid): return iid in self.balances
    def original_operation(self, t): return self.original
    def cash_pool_pair(self, t): return self.paired


def item(iid, doc, amount=10000, **kwargs):
    return dict(iid=iid, doc=doc, total=amount, initial=amount, balance=amount, party='C1',
                issue=kwargs.get('issue', '2025-07-01'), side='AR', currency='EUR', entity='ES01',
                facts=kwargs.get('facts', {}))


def bank(**kwargs):
    t=dict(bank_txn_id='B1', amount='100.00', currency='EUR', booking_date='2025-08-01',
           entity='ES01', account_id='ES01-RHEI-EUR', bank='RHEI', statement_format='camt053',
           bank_code='', text='', counterparty_name='Customer', counterparty_account='')
    t.update(kwargs);return t


class RecoveryTests(unittest.TestCase):
    def test_named_period_uses_cached_service_month_not_issue_month(self):
        june=item('ARI-JUNE', 'FJUN', facts={'service_month':'SERVICIO JUNIO 2025.'})
        july=item('ARI-JULY', 'FJUL', issue='2025-08-01',facts={'service_month':'SERVICIO JULIO 2025.'})
        c=Catalog([june,july]);before=deepcopy(c.items)
        result=propose(bank(text='MANT. JUNIO 25'), [['B1','ARI-JULY','100.00','','']], [], c, Ledger())
        self.assertEqual(result[0],[['B1','ARI-JUNE','100.00','','']])
        self.assertEqual(c.items,before)

    def test_ambiguous_named_period_does_not_force_a_choice(self):
        c=Catalog([item('ARI-A','A',facts={'service_month':'SERVICIO JUNIO 2025'}),
                   item('ARI-B','B',facts={'service_month':'SERVICIO JUNIO 2025'})])
        self.assertIsNone(propose(bank(text='MANT. JUNIO 25'),[['B1','','','UNIDENTIFIED','UNIDENTIFIED']],[],c,Ledger()))

    def test_omitted_december_year_is_prior_year(self):
        self.assertEqual(service_period('SERVICIOS DICIEMBRE','2025-01-03'),(2024,12))
        self.assertEqual(service_period('MANT. MAYO 25','2025-07-03'),(2025,5))

    def test_scoped_zero_balance_code_is_cash_pool_not_bank_fees(self):
        c=Catalog(accounts={'ES01-RHEI-EUR':{'purpose':'Operativa / participante cash pool'}})
        result=propose(bank(text='TRASPASO PROPIO',bank_code='CAMT/ACCB/ZABA'),[['B1','','','UNIDENTIFIED','UNIDENTIFIED']],[],c,Ledger())
        self.assertEqual(result[0],[['B1','','','CASH_POOL','']])
        c.bank_accounts['ES01-RHEI-EUR']['purpose']='Cobros / Pagos'
        self.assertIsNone(propose(bank(bank_code='CAMT/ACCB/ZABA'),[['B1','','','UNIDENTIFIED','UNIDENTIFIED']],[],c,Ledger()))

    def test_unique_related_credit_recovers_full_invoice_netting(self):
        inv=item('ARI-1','F100');credit=item('ARC-1','NC100',1000)
        c=Catalog([inv,credit]);c.related[('ES01','F100')]={'ARC-1'}
        base=[['B1','ARI-1','90.00','','PARTIAL']]
        result=propose(bank(amount='90.00'),base,base,c,Ledger())
        self.assertEqual(sorted(result[0]),[['B1','ARC-1','10.00','',''],['B1','ARI-1','100.00','','']])

    def test_ambiguous_credit_netting_keeps_incumbent(self):
        inv=item('ARI-1','F100');c=Catalog([inv,item('ARC-1','NC1',1000),item('ARC-2','NC2',1000)])
        c.related[('ES01','F100')]={'ARC-1','ARC-2'}
        base=[['B1','ARI-1','90.00','','PARTIAL']]
        self.assertIsNone(propose(bank(amount='90.00'),base,base,c,Ledger()))

    def test_explained_discount_is_not_replaced_by_coincidental_credit(self):
        c=Catalog([item('ARI-1','F100'),item('ARC-1','NC100',1000)])
        c.related[('ES01','F100')]={'ARC-1'}
        base=[['B1','ARI-1','100.00','','SHORT_DISCOUNT']]
        self.assertIsNone(propose(bank(amount='90.00'),base,base,c,Ledger()))

    def test_return_uses_original_allocation_and_reopens_each_item(self):
        c=Catalog([item('ARI-1','F1'),item('ARI-2','F2',5000)])
        original=[['OLD','ARI-1','100.00','',''],['OLD','ARI-2','50.00','','']]
        result=propose(bank(amount='-150.00',text='CHARGEBACK'),[['B1','','','UNIDENTIFIED','UNIDENTIFIED']],[],c,Ledger(original=original))
        self.assertEqual(result[0],[['B1','ARI-1','100.00','','RETURNED'],['B1','ARI-2','50.00','','RETURNED']])

    def test_replacement_requires_actual_old_reference_and_matching_amount(self):
        c=Catalog([item('ARI-NEW','NEW123',facts={'replaces':'OLD123'})])
        base=[['B1','','','UNIDENTIFIED','UNIDENTIFIED']]
        result=propose(bank(text='TRANSFER OLD123'),base,base,c,Ledger())
        self.assertEqual(result[0],[['B1','ARI-NEW','100.00','','']])
        self.assertIsNone(propose(bank(text='TRANSFER OLD123',amount='99.00'),base,base,c,Ledger()))

    def test_unidentified_equal_amount_alone_is_not_forced(self):
        c=Catalog([item('ARI-1','F100')]);base=[['B1','','','UNIDENTIFIED','UNIDENTIFIED']]
        self.assertIsNone(propose(bank(text='CASH FROM UNKNOWN'),base,base,c,Ledger()))


if __name__=='__main__':unittest.main()
