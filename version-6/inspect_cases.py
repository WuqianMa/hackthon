"""Small prior-period TRAIN casebook for mechanism discovery, never LIVE inference."""
from collections import defaultdict
import hashlib,json,sqlite3,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parent.parent;sys.path.insert(0,str(ROOT))
from bankrec.io import rows,cents,write_json

TARGETS=['ar_card_chargeback','ap_returned_transfer','ar_cheque_returned','ar_short_bank_charges',
         'ar_n_to_m','ar_1toN_credit_note','ar_same_amount_month','ar_advance_deduction','ar_replaced_invoice','ap_duplicate_refund']

def main():
    folder=ROOT/'work/version-4-train/calibration_labels';banks={r['bank_txn_id']:r for r in rows(folder/'bank_transactions.csv')}
    allocations=defaultdict(list);groups=defaultdict(list)
    for r in rows(folder/'golden_allocations.csv'):allocations[r['bank_txn_id']].append(r)
    for tid,rs in allocations.items():
        if rs[0]['segment'] in TARGETS:groups[rs[0]['segment']].append(tid)
    db=sqlite3.connect(f'file:{ROOT / "work/version-4-train/catalog.sqlite"}?mode=ro',uri=True);db.row_factory=sqlite3.Row
    db.execute('PRAGMA mmap_size=1073741824');out=[]
    for segment in TARGETS:
        for tid in sorted(groups[segment],key=lambda x:hashlib.sha256(x.encode()).hexdigest())[:8]:
            items=[]
            for r in allocations[tid]:
                if not r['item_id']:continue
                i=dict(db.execute('SELECT * FROM items WHERE iid=?',(r['item_id'],)).fetchone())
                items.append(dict(golden=r,item=i))
            out.append(dict(segment=segment,bank=banks[tid],golden=allocations[tid],items=items))
    dest=ROOT/'work/version-6';dest.mkdir(exist_ok=True)
    write_json(dest/'train_casebook.json',dict(scope='July–December 2024 calibration examples only; diagnostic supervision, not inference',available={s:len(groups[s]) for s in TARGETS},cases=out))
    for segment in TARGETS:
        print('\n'+segment, 'available',len(groups[segment]))
        for r in [x for x in out if x['segment']==segment][:3]:
            print(json.dumps(dict(bank=r['bank'],allocations=[dict(doc=x['item']['doc'],party=x['item']['party'],total=x['item']['total'],issue=x['item']['issue'],amount=x['golden']['amount'],exception=x['golden']['exception'],facts=x['item']['facts']) for x in r['items'][:6]],rows=len(r['golden'])),ensure_ascii=False))

if __name__=='__main__':main()
