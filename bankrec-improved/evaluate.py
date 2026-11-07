"""Separate offline evaluator. Only this file loads golden labels.

Development: booking date <= 2025-06-20. Temporal holdout: later dates.
The sample was explored previously, so holdout is a development sanity check,
not a blind competition evaluation. Inference still has no access to labels.
"""
import argparse
import importlib.util
import json
from pathlib import Path
from matcher import read_csv

EXCEPTIONS = ['PARTIAL', 'OVERPAYMENT', 'SHORT_DISCOUNT', 'SHORT_BANK_CHARGES', 'SHORT_WITHHOLDING',
              'SHORT_DISPUTE', 'DUPLICATE_PAYMENT', 'UNIDENTIFIED', 'RETURNED', 'FX_DIFFERENCE']


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('prediction')
    ap.add_argument('--data', default=str(Path(__file__).resolve().parent.parent / 'bankrec-docs-and-masters'))
    ap.add_argument('--split', choices=['dev', 'holdout', 'all'], default='dev')
    ap.add_argument('--out')
    args = ap.parse_args()
    root = Path(args.data)
    spec = importlib.util.spec_from_file_location('official_scorer', root / 'starter/bankrec_score.py')
    S = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(S)
    golden = S.load_golden(str(root / 'sample/golden_allocations.csv.gz'), str(root / 'sample/bank_transactions.csv.gz'),
                           EXCEPTIONS, [r['category'] for r in read_csv(root / 'masters/categories.csv')])
    txns = read_csv(root / 'sample/bank_transactions.csv.gz')
    wanted = {r['bank_txn_id'] for r in txns if args.split == 'all' or ((r['booking_date'] <= '2025-06-20') == (args.split == 'dev'))}
    golden.txns = {k: v for k, v in golden.txns.items() if k in wanted}
    golden.weight = {k: v for k, v in golden.weight.items() if k in wanted}
    golden.n_pairs = sum(len(v[0]) for v in golden.txns.values())
    import csv, io
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=['bank_txn_id', 'item_id', 'amount', 'category', 'exception'], lineterminator='\n')
    w.writeheader()
    w.writerows(r for r in read_csv(args.prediction) if r['bank_txn_id'] in wanted)
    result = S.score_submission(golden, buf.getvalue().encode(), 'prediction.csv')
    result['split'] = args.split
    result['cutoff'] = '2025-06-20'
    result['prediction'] = Path(args.prediction).name
    if args.out:
        Path(args.out).write_text(json.dumps(result, indent=2))
    print(json.dumps({k: v for k, v in result.items() if k != 'segments'}, indent=2))
    for name, value in sorted(result['segments'].items(), key=lambda x: -x[1]['n'])[:20]:
        print(name, value)


if __name__ == '__main__':
    main()
