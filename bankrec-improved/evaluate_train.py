"""Offline full TRAIN evaluation using the supplied official scorer.

Only upload size/row limits are enlarged for the four-year training corpus.
The scorer's matching tolerances, validation and metric formulas are unchanged.
This is not a leaderboard submission.
"""
import argparse
import importlib.util
import json
import resource
import time
from pathlib import Path
from evaluate import EXCEPTIONS
from matcher import read_csv, iter_csv
from train_runner import group


def main():
    here = Path(__file__).resolve().parent
    p = argparse.ArgumentParser()
    p.add_argument('prediction', type=Path)
    p.add_argument('--train', type=Path, default=here.parent / 'train')
    p.add_argument('--docs', type=Path, default=here.parent / 'bankrec-docs-and-masters')
    p.add_argument('--out', type=Path, default=here / 'train_results/full_train_score.json')
    p.add_argument('--by-group', action='store_true', help='Also score each saved prediction group')
    args = p.parse_args()
    spec = importlib.util.spec_from_file_location('official_scorer', args.docs / 'starter/bankrec_score.py')
    scorer = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(scorer)
    scorer.MAX_UNCOMPRESSED = 2 * 1024**3
    scorer.MAX_DECOMPRESS = 2 * 1024**3
    scorer.MAX_ROWS = 20_000_000
    start = time.monotonic()
    print('Loading TRAIN labels for evaluation only...', flush=True)
    golden = scorer.load_golden(str(args.train / 'golden_allocations.csv.gz'),
                               str(args.train / 'bank_transactions.csv.gz'), EXCEPTIONS,
                               [r['category'] for r in read_csv(args.docs / 'masters/categories.csv')])
    loaded = time.monotonic()
    print('Scoring', len(golden.txns), 'transactions,', golden.n_pairs, 'gold allocations', flush=True)
    result = scorer.score_submission(golden, args.prediction.read_bytes(), args.prediction.name)
    result['evaluation'] = 'full TRAIN; official scorer; offline size limits enlarged only'
    result['prediction'] = args.prediction.name
    result['timing'] = {'load_golden_s': round(loaded-start, 2), 'score_s': round(time.monotonic()-loaded, 2)}
    result['max_rss_native'] = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    args.out.write_text(json.dumps(result, indent=2))
    print(json.dumps(result, indent=2), flush=True)
    if not result['ok']:
        raise SystemExit(1)
    if args.by_group:
        grouped = {}
        for row in iter_csv(args.train / 'bank_transactions.csv.gz'):
            grouped.setdefault(group(row['entity']), []).append(row['bank_txn_id'])
        breakdown = {}
        for name, ids in sorted(grouped.items()):
            subset = scorer.Golden()
            subset.exceptions, subset.categories = golden.exceptions, golden.categories
            subset.txns = {t: golden.txns[t] for t in ids}
            subset.weight = {t: golden.weight[t] for t in ids}
            subset.n_pairs = sum(len(v[0]) for v in subset.txns.values())
            path = args.prediction.parent / (name + '.csv.gz')
            breakdown[name] = scorer.score_submission(subset, path.read_bytes(), path.name)
            if not breakdown[name]['ok']:
                raise RuntimeError(f'Group scoring failed: {name}: {breakdown[name]["errors"]}')
            print('GROUP_SCORE', name, breakdown[name]['score'], flush=True)
        args.out.with_name('train_group_scores.json').write_text(json.dumps(breakdown, indent=2))


if __name__ == '__main__':
    main()
