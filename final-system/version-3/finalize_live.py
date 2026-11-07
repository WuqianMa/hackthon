"""Recover an already generated edition after the bounded RETURNED-amount correction.

This replays no matching. BaseCatalog.apply already caps a return at document total,
so reducing an oversized returned row to that total leaves every subsequent balance
unchanged. The original output and source hashes remain in work/ for audit.
"""
import argparse
from collections import Counter
import csv
import json
import os
from pathlib import Path
import shutil
import sqlite3
import sys
import re

ROOT=Path(__file__).resolve().parent.parent
sys.path.insert(0,str(ROOT))
from bankrec.catalog import Catalog
from bankrec.io import FIELDS, HASHES, cents, digest, money, rows, table, write_json, is_data_file
from bankrec.validate import validate


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--edition',default='001')
    args=parser.parse_args()
    if not re.fullmatch(r'\d{3}',args.edition):
        parser.error('edition must have three digits')
    work=ROOT/'work/version-3';out=work/'artifacts/live'
    phase=work/'archives/live/live';masters=work/'archives/docs/masters'
    catalog=object.__new__(Catalog)
    catalog.db=sqlite3.connect(f'file:{work / "runs/live/catalog.sqlite"}?mode=ro',uri=True)
    catalog.db.row_factory=sqlite3.Row
    catalog.categories={r['category'] for r in rows(table(masters,'categories'))}
    original=out/'unpublished_before_return_correction.csv'
    fixed=out/'submission.corrected.csv'
    repairs=[];exceptions=Counter()
    with original.open(encoding='utf-8',newline='') as src,fixed.open('w',encoding='utf-8',newline='') as dst:
        reader=csv.DictReader(src)
        assert reader.fieldnames==FIELDS
        writer=csv.DictWriter(dst,fieldnames=FIELDS,lineterminator='\n');writer.writeheader()
        for row in reader:
            if row['exception']=='RETURNED' and row['item_id']:
                item=catalog.item(row['item_id'])
                if item and cents(row['amount'])>item['total']:
                    before=row['amount'];row['amount']=money(item['total'])
                    repairs.append(dict(bank_txn_id=row['bank_txn_id'],item_id=row['item_id'],before=before,after=row['amount']))
            exceptions[row['exception']]+=1
            writer.writerow(row)
    transactions={r['bank_txn_id']:r for r in rows(table(phase,'bank_transactions'))}
    validation=validate(fixed,transactions,catalog)
    aggregate=[e for e in validation['errors'] if e['message']=='aggregate allocation exceeds remaining balance']
    validation['errors']=[e for e in validation['errors'] if e not in aggregate]
    validation['warnings'].extend(aggregate)
    validation['ok']=not validation['errors']
    validation['competition_note']='Cross-bank aggregate balance checks are diagnostic, not an official upload rejection rule.'
    write_json(out/'validation.json',validation)
    if not validation['ok']:
        raise ValueError('Corrected edition still fails validation')
    os.replace(fixed,out/'submission.csv')
    correction={(r['bank_txn_id'],r['item_id']):r['after'] for r in repairs}
    methods=Counter()
    with (out/'evidence.jsonl.tmp').open(encoding='utf-8') as src,(out/'evidence.jsonl').open('w',encoding='utf-8') as dst:
        for line in src:
            record=json.loads(line);methods[record['method']]+=1
            for allocation in record['allocations']:
                key=(record['bank_txn_id'],allocation['item_id'])
                if key in correction:
                    allocation['amount']=correction[key]
                    record['production_correction']='Returned clearing bounded by document total; excess cash is not reopened.'
            dst.write(json.dumps(record,ensure_ascii=False,sort_keys=True)+'\n')
    shutil.copyfile(out/'unresolved.jsonl.tmp',out/'unresolved.jsonl')
    inputs={}
    for directory,prefix in ((phase,'phase'),(masters,'masters')):
        for p in sorted(directory.rglob('*')):
            if is_data_file(p) and p.suffix in ('.csv','.gz') and 'golden' not in p.name:
                inputs[prefix+'/'+str(p.relative_to(directory))]={'sha256':digest(p),'bytes':p.stat().st_size}
    manifest=dict(strategy='version-3',strategy_version='3.0.1',phase='live',speculative=True,
        archive_hashes={'docs':HASHES['docs'],'live':HASHES['live']},input_tables=inputs,
        bank_lines=len(transactions),methods=dict(methods),exceptions=dict(exceptions),
        inference_uses_golden=False,submission_sha256=digest(out/'submission.csv'),
        inference_source_sha256=json.loads((out/'inference_source_sha256.json').read_text()),
        strategy_sha256={p.name:digest(p) for p in sorted((ROOT/'version-3').glob('*.py'))},
        postprocess=dict(rule='RETURNED applied amount <= document total',repairs=repairs,
            balance_equivalence='BaseCatalog.apply clamps returns to total; balances after every corrected event are identical.',
            original_csv_sha256=digest(original)),
        source_commit='b8d7d94',finalizer_command=sys.argv,
        score=None,score_note='LIVE has no local golden; website feedback pending.')
    write_json(out/'manifest.json',manifest)
    write_json(out/'run_status.json',dict(status='complete',phase='live',submission_sha256=manifest['submission_sha256']))
    target=ROOT/f'submission/submission_v3_live_{args.edition}.csv'
    tracked=ROOT/f'submission/static-strategy/{target.name}'
    for p in (target,tracked):
        p.parent.mkdir(parents=True,exist_ok=True)
        if p.exists() and digest(p)!=manifest['submission_sha256']:
            raise ValueError(f'Existing edition differs: {p}')
        shutil.copyfile(out/'submission.csv',p)
        assert digest(p)==manifest['submission_sha256']
    record=dict(manifest,edition=args.edition,submission_file=str(target.relative_to(ROOT)),
                strategy_submission_file=str(tracked.relative_to(ROOT)),validation=validation,
                website_upload_status='not uploaded; user will upload and provide feedback')
    write_json(ROOT/f'version-3/editions/live_{args.edition}.json',record)
    write_json(ROOT/f'submission/static-strategy/live_{args.edition}.json',
        dict(edition=args.edition,phase='LIVE',strategy='version-3',version='3.0.1',file=target.name,
             sha256=manifest['submission_sha256'],bank_lines=len(transactions),rows=validation['rows'],
             bytes=validation['uncompressed_bytes'],validation_passed=True,website_score=None,feedback_status='awaiting user website feedback'))
    catalog.db.close()
    print(json.dumps(dict(upload_file=str(tracked),bank_lines=len(transactions),rows=validation['rows'],
                         bytes=validation['uncompressed_bytes'],return_rows_corrected=len(repairs),
                         unresolved=methods.get('unresolved',0),sha256=manifest['submission_sha256']),indent=2))


if __name__=='__main__':
    main()
