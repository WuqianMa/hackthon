"""Run the unchanged matching rules over all TRAIN, partitioned by legal entity.

ES00/ES01/ES02/PT01 share a partition to retain payment-factory relationships.
No golden labels are copied into inference workspaces. Reusable checkpoints.
"""
import argparse
import csv
import gzip
import heapq
import json
import os
import signal
import subprocess
import sys
import time
from collections import Counter
from pathlib import Path
from matcher import Matcher, iter_csv, read_csv

ES_GROUP = {'ES00', 'ES01', 'ES02', 'PT01'}


def group(entity):
    return 'ES_PAYMENT_FACTORY' if entity in ES_GROUP else entity


def symlink(src, dst):
    if not dst.exists():
        dst.symlink_to(src.resolve(), target_is_directory=src.is_dir())


def prepare(source, docs, work):
    groups = sorted({group(r['entity']) for r in read_csv(docs / 'masters/entities.csv')})
    for g in groups:
        (work / g / 'train').mkdir(parents=True, exist_ok=True)
        symlink(docs / 'masters', work / g / 'masters')
    manifest = {'source': str(source), 'groups': groups, 'tables': {}}
    for filename in ['bank_transactions', 'ar_invoices', 'ap_invoices', 'credit_notes']:
        handles, writers, counts = {}, {}, Counter()
        try:
            for r in iter_csv(source / (filename + '.csv.gz')):
                g = group(r['entity'])
                if g not in writers:
                    f = gzip.open(work / g / 'train' / (filename + '.csv.gz'), 'wt', compresslevel=1, newline='')
                    handles[g] = f
                    writers[g] = csv.DictWriter(f, fieldnames=list(r), lineterminator='\n')
                    writers[g].writeheader()
                writers[g].writerow(r)
                counts[g] += 1
        finally:
            for f in handles.values():
                f.close()
        manifest['tables'][filename] = dict(counts)
        print('PARTITIONED', filename, sum(counts.values()), flush=True)
    for folder in ['pdfs', 'remittance_advices']:
        records = {}
        for r in iter_csv(source / folder / 'index.csv'):
            records.setdefault(group(r['entity']), []).append(r)
        for g in groups:
            dst = work / g / 'train' / folder
            dst.mkdir(exist_ok=True)
            rows = records.get(g, [])
            if rows:
                with (dst / 'index.csv').open('w', newline='') as f:
                    w = csv.DictWriter(f, fieldnames=list(rows[0]), lineterminator='\n')
                    w.writeheader()
                    w.writerows(rows)
            for subdir in (source / folder).iterdir():
                if subdir.is_dir() and group(subdir.name) == g:
                    symlink(subdir, dst / subdir.name)
    for folder in ['payment_runs','direct_debit_batches','card_settlements','cheque_deposits']:
        for f in (source / folder).glob('*.csv'):
            g = group(f.name.split('_')[0])
            if g not in groups:
                raise ValueError(f'Unexpected file entity: {f}')
            dst = work / g / 'train' / folder
            dst.mkdir(exist_ok=True)
            symlink(f, dst / f.name)
    (work / 'prepared.json').write_text(json.dumps(manifest, indent=2))
    return manifest


def worker(root, out, mode):
    def forbid_labels(event, args):
        if event == 'open' and isinstance(args[0], (str,bytes)) and 'golden_allocations' in str(args[0]):
            raise RuntimeError('Prediction cannot open golden allocations')
    sys.addaudithook(forbid_labels)
    begin = time.monotonic()
    print('LOADING', root.name, flush=True)
    m = Matcher(root, phase='train', mode=mode, cache='/tmp/bankrec-pdf-text-cache')
    print('LOADED', root.name, len(m.items), 'items', len(m.transactions), 'transactions', round(time.monotonic()-begin,1), 'seconds', flush=True)
    result = m.run(out, None)
    result['total_seconds'] = round(time.monotonic()-begin, 2)
    result['label_access_guard'] = True
    result['group'] = root.name
    out.with_name(out.name + '.stats.json').write_text(json.dumps(result, indent=2))


def main():
    p = argparse.ArgumentParser()
    here = Path(__file__).resolve().parent
    p.add_argument('--train', type=Path, default=here.parent / 'train')
    p.add_argument('--docs', type=Path, default=here.parent / 'bankrec-docs-and-masters')
    p.add_argument('--work', type=Path, default=here / 'train_work')
    p.add_argument('--out', type=Path, default=here / 'train_results')
    p.add_argument('--mode', choices=['full','masters'], default='full')
    p.add_argument('--workers', type=int, default=2)
    p.add_argument('--worker-root', type=Path)
    p.add_argument('--worker-output', type=Path)
    args = p.parse_args()
    if args.worker_root:
        worker(args.worker_root, args.worker_output, args.mode)
        return
    args.work.mkdir(parents=True, exist_ok=True)
    args.out.mkdir(parents=True, exist_ok=True)
    manifest_path = args.work / 'prepared.json'
    manifest = json.loads(manifest_path.read_text()) if manifest_path.exists() else prepare(args.train, args.docs, args.work)
    sizes = manifest['tables']['bank_transactions']
    pending = sorted(manifest['groups'], key=lambda g:sizes.get(g,0))
    running = {}
    def stop_workers(signum, frame):
        for proc, log in running.values():
            proc.terminate()
        for proc, log in running.values():
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait()
            log.close()
        raise SystemExit(128 + signum)
    signal.signal(signal.SIGINT, stop_workers)
    signal.signal(signal.SIGTERM, stop_workers)
    while pending or running:
        while pending and len(running) < args.workers:
            g = pending.pop(0)
            target = args.out / (g + '.csv.gz')
            if target.exists() and target.with_name(target.name + '.stats.json').exists():
                print('REUSE',g,flush=True)
                continue
            log = (args.out / (g + '.log')).open('w')
            command = [sys.executable, '-B', str(Path(__file__).resolve()), '--worker-root', str(args.work / g),
                       '--worker-output', str(target), '--mode', args.mode]
            env = {**os.environ, 'PYTHONHASHSEED': '0'}
            proc = subprocess.Popen(command, stdout=log, stderr=subprocess.STDOUT, env=env)
            running[g] = (proc, log)
            print('START',g,'pid',proc.pid,flush=True)
        for g, (proc, log) in list(running.items()):
            if proc.poll() is not None:
                log.close()
                del running[g]
                if proc.returncode:
                    for other, lf in running.values():
                        other.terminate()
                        lf.close()
                    raise RuntimeError(f'{g} failed; inspect {args.out / (g + ".log")}')
                print('DONE',g,flush=True)
        if running:
            time.sleep(1)
    merged = args.out / 'train_predictions.csv.gz'
    def rows(path):
        last = ''
        for r in iter_csv(path):
            if r['bank_txn_id'] < last:
                raise ValueError(f'Unsorted predictions: {path}')
            last = r['bank_txn_id']
            yield r
    with gzip.open(merged, 'wt', newline='') as f:
        w = csv.DictWriter(f, fieldnames=['bank_txn_id','item_id','amount','category','exception'], lineterminator='\n')
        w.writeheader()
        w.writerows(heapq.merge(*(rows(args.out / (g + '.csv.gz')) for g in manifest['groups']), key=lambda r:r['bank_txn_id']))
    print('MERGED',merged,flush=True)


if __name__ == '__main__':
    main()
