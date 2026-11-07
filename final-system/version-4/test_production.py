"""Production temporal boundaries, sampling, and episode purge invariants."""
import csv
import tempfile
from pathlib import Path
import unittest
from production_data import role,sample_banks,DiskCatalog,MonthSources
from train_live import attach_targets,amount_contract_guard
import json
import sqlite3
from types import SimpleNamespace


class ProductionTests(unittest.TestCase):
    def test_invalid_blank_duplicate_falls_back_without_clamping_cash(self):
        static={'B':[['B','I','105.00','','DUPLICATE_PAYMENT']]}
        pred={'B':[['B','I','105.00','','']]}
        c=SimpleNamespace(item=lambda iid:dict(total=10000))
        repairs=amount_contract_guard(pred,static,c)
        self.assertEqual(len(repairs),1)
        self.assertEqual(pred,static)
        self.assertEqual(amount_contract_guard(pred,static,c),[])

    def test_temporal_roles(self):
        for dt,expected in [('2023-12-31','pair_fit'),('2024-01-01','hypothesis_fit'),
                            ('2024-07-01','calibration'),('2025-01-01','test'),
                            ('2025-06-01','inspected_starter_excluded')]:
            self.assertEqual(role(dt),expected)

    def test_sampling_does_not_depend_on_order_or_labels(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp);records=[dict(bank_txn_id=f'B{i}',booking_date='2024-01-05') for i in range(20)]
            records.append(dict(bank_txn_id='SAMPLE',booking_date='2025-06-10'))
            def write(rs):
                with (p/'bank_transactions.csv').open('w',newline='') as f:
                    w=csv.DictWriter(f,fieldnames=['bank_txn_id','booking_date']);w.writeheader();w.writerows(rs)
            write(records);a,counts=sample_banks(p,5)
            write(list(reversed(records)));b,_=sample_banks(p,5)
            self.assertEqual(set(a['2024-01']),set(b['2024-01']))
            self.assertNotIn('2025-06',a);self.assertEqual(counts['2024-01'],20)

    def test_shared_item_purges_entire_earlier_transaction(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)
            with (p/'golden_allocations.csv').open('w',newline='') as f:
                w=csv.DictWriter(f,fieldnames=['bank_txn_id','item_id','amount','category','exception','segment']);w.writeheader()
                for t,i in [('B1','I1'),('B1','I2'),('B2','I1'),('B3','I3')]:
                    w.writerow(dict(bank_txn_id=t,item_id=i,amount='10.00',category='',exception='',segment='unit'))
            _,_,_,purged=attach_targets(p,{'B1':'pair_fit','B2':'test','B3':'calibration'})
            self.assertEqual(purged,{'B1'})

    def test_future_cancellation_not_visible_in_past(self):
        c=object.__new__(DiskCatalog);c.as_of='2024-01-01'
        original=dict(iid='I',facts=json.dumps(dict(cancelled=True,cancelled_from='2024-02-01')))
        self.assertFalse(json.loads(c.visible(original)['facts']).get('cancelled'))
        c.as_of='2024-02-01'
        self.assertTrue(json.loads(c.visible(original)['facts'])['cancelled'])

    def test_candidate_policy_cannot_see_end_of_month_ledger(self):
        c=object.__new__(DiskCatalog);c.as_of='2024-01-01';c.candidate_mode=True
        item=dict(iid='I',initial=10000,balance=0,facts='{}')
        self.assertEqual(c.visible(item)['balance'],10000)
        c.candidate_mode=False
        self.assertEqual(c.visible(item)['balance'],0)

    def test_short_supplier_reference_retains_maturity_container(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp);(p/'payment_runs').mkdir()
            db=sqlite3.connect(':memory:');db.row_factory=sqlite3.Row
            db.execute('CREATE TABLE items(iid,side,doc,name,currency,due)')
            db.execute("INSERT INTO items VALUES('API-2024-0000001','AP','1234','Supplier ABC','EUR','2024-02-01')")
            r=dict(run_type='confirming',run_id='RUN0001',end_to_end_id='TRANSFER001',debtor_account_id='ES01-RIBA-EUR',
                   execution_date='2024-01-01',currency='EUR',transfer_amount='10.00',document_number='1234',
                   document_amount='10.00',beneficiary='Supplier ABC',beneficiary_iban='')
            with (p/'payment_runs/run.csv').open('w',newline='') as f:
                w=csv.DictWriter(f,fieldnames=list(r));w.writeheader();w.writerow(r)
            source=MonthSources(p,p/'cache',SimpleNamespace(db=db))
            key='maturity:ES01-RIBA-EUR:RUN0001:2024-02-01'
            self.assertIn(key,source.groups)
            self.assertEqual(source.groups[key].cash,-1000)
            db.close()


if __name__=='__main__':unittest.main()
