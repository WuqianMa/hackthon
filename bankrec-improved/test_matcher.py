"""Small independent accounting cases; expectations are not dataset labels."""
import csv
import gzip
import tempfile
import unittest
from pathlib import Path
from matcher import Matcher, cents, parsed_money, read_csv


def write_rows(path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    op = gzip.open if path.suffix == '.gz' else open
    with op(path, 'wt', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


class ReconciliationTest(unittest.TestCase):
    def test_amount_parsing(self):
        self.assertEqual(cents('1.005'), 101)
        self.assertEqual(parsed_money('1.234,56'), 123456)
        self.assertEqual(parsed_money('-1,234.56'), -123456)

    def test_payments_and_state_without_labels(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            customers = [dict(customer_id='C' + str(n), entity='E1', name=name, trade_name='',
                              iban='', sepa_mandate_id='VTM-ES-0000004' if n == 4 else '', country='ES', group_id='')
                         for n, name in enumerate(['Amber Tools', 'Birch Motors', 'Cedar Gardens', 'Dahlia Plumbing', 'Elm Services'], 1)]
            write_rows(root / 'masters/customers.csv', customers)
            write_rows(root / 'masters/payment_terms.csv', [dict(code='D2', early_payment_discount_pct='2', discount_days='10')])
            write_rows(root / 'masters/categories.csv', [dict(category='UNIDENTIFIED')])
            invoices = []
            for n, pid, amount in [(1, 'C1', '100'), (2, 'C2', '100'), (3, 'C2', '200'), (4, 'C3', '100'), (5, 'C4', '60'), (6, 'C5', '100')]:
                invoices.append(dict(item_id=f'ARI-2025-{n:07d}', entity='E1', document_number=f'INV{n:06d}',
                                     customer_id=pid, customer_name=customers[int(pid[1:]) - 1]['name'], issue_date='2025-06-01',
                                     due_date='2025-07-01', total_amount=amount, currency='EUR', payment_terms='D2' if n == 4 else 'T30', customer_po=''))
            write_rows(root / 'sample/ar_invoices.csv.gz', invoices)
            specs = [('100', 'Amber Tools INV000001'), ('300', 'Birch Motors'), ('98', 'Cedar Gardens INV000004'),
                     ('-60', 'DEVOLUCION RECIBO VTM-ES-0000004'), ('100', 'Unknown person'),
                     ('50', 'Elm Services INV000006'), ('50', 'Elm Services INV000006'), ('100', 'Amber Tools INV000001')]
            txns = [dict(bank_txn_id=f'BT-2025-{n:07d}', account_id='ACCOUNT', entity='E1', amount=amount, currency='EUR',
                         booking_date=f'2025-06-{n + 1:02d}', text=text)
                    for n, (amount, text) in enumerate(specs, 1)]
            write_rows(root / 'sample/bank_transactions.csv.gz', txns)
            matcher = Matcher(root, mode='masters')
            matcher.run(root / 'result.csv', None)
            rows = read_csv(root / 'result.csv')
            got = {(r['bank_txn_id'], r['item_id'], r['amount'], r['category'], r['exception']) for r in rows}
            def allocation(t, i, amount, exc=''):
                return (f'BT-2025-{t:07d}', f'ARI-2025-{i:07d}', amount, '', exc)
            expected = {allocation(1, 1, '100.00'), allocation(2, 2, '100.00'), allocation(2, 3, '200.00'),
                        allocation(3, 4, '100.00', 'SHORT_DISCOUNT'), allocation(4, 5, '60.00', 'RETURNED'),
                        ('BT-2025-0000005', '', '', 'UNIDENTIFIED', 'UNIDENTIFIED'),
                        allocation(6, 6, '50.00', 'PARTIAL'), allocation(7, 6, '50.00'),
                        allocation(8, 1, '100.00', 'DUPLICATE_PAYMENT')}
            self.assertEqual(got, expected)
            # A historical account is in bank transactions but absent from masters.
            write_rows(root / 'sample/direct_debit_batches/batch.csv', [
                dict(batch_id='B1', account_id='ACCOUNT', collection_date='2025-06-02',
                     mandate_id='', remittance_info='INV000001', amount='100',
                     batch_total='100', currency='EUR')])
            full = Matcher(root, mode='full')
            full.run(root / 'full.csv', None)
            actual = {(r['bank_txn_id'], r['item_id'], r['amount'], r['category'], r['exception'])
                      for r in read_csv(root / 'full.csv')}
            self.assertEqual(actual, expected)
            self.assertEqual(full.stats['batch_dd'], 1)


if __name__ == '__main__':
    unittest.main()
