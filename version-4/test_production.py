"""Production temporal boundaries, sampling, and episode purge invariants."""
import csv
import tempfile
from pathlib import Path
import unittest
from production_data import role,sample_banks,DiskCatalog
from train_live import attach_targets
import json


class ProductionTests(unittest.TestCase):
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


if __name__=='__main__':unittest.main()
