"""Reproduce v6 from immutable v5 predictions, frozen weights and cached sources."""
from collections import Counter
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import shutil
import sys
import time

ROOT=Path(__file__).resolve().parent.parent
sys.path.insert(0,str(ROOT));sys.path.insert(0,str(ROOT/'version-5'))
spec=importlib.util.spec_from_file_location('v6_v5_runtime',ROOT/'version-5/run.py')
v5=importlib.util.module_from_spec(spec);spec.loader.exec_module(v5)
sys.path.insert(0,str(Path(__file__).parent))
from mechanisms import CatalogView,SourceIndex,propose
from bankrec.io import rows,table,cents,digest,write_json,FIELDS,EXCEPTIONS
from bankrec.validate import validate

WORK=ROOT/'work/version-6';RESULTS=ROOT/'version-6/results'
V5_SHA='2e1e6354334d919d3ffffed42244d4ff3045fded370e2d28572075e7c37bda0b'
MODEL_SHA='a883a203fc5bc694812895a14cbd8b125870f435a67bc5e7627ab42e4526eccb'


def baseline(phase,c):
    banks,_,_,_=v5.load_inputs(phase)
    if phase=='live':
        if digest(ROOT/'v5-submission.csv')!=V5_SHA:raise ValueError('Frozen v5 changed')
        pred=v5.read_predictions(ROOT/'v5-submission.csv')
    else:
        pred=v5.read_predictions(ROOT/'work/version-5/test_overlay.csv')
        packets={p['bank']['bank_txn_id']:p for p in map(json.loads,(ROOT/'work/version-5/llm_packets_test.jsonl').open())}
        decisions=list(map(json.loads,(ROOT/'version-5/llm/development_001.jsonl').open()))
        v5.apply_decisions(pred,packets,decisions,c)
    return banks,pred


def scoring():
    spec=importlib.util.spec_from_file_location('v6_scoring',ROOT/'version-4/run.py');m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
    module,g=m.official(dict(docs=v5.DOCS,phase=ROOT/'work/version-4-train/test_labels'))
    return m,module,g


def build(phase,enabled=None):
    WORK.mkdir(exist_ok=True);RESULTS.mkdir(exist_ok=True);start=time.monotonic()
    if digest(v5.MODEL)!=MODEL_SHA:raise ValueError('Frozen model changed')
    base,_=v5.open_catalog(phase);banks,incumbent=baseline(phase,base)
    print('Loading cached PDF clauses...',flush=True)
    c=CatalogView(base,banks);print('PDF facts',dict(c.stats),flush=True)
    sources=SourceIndex(c,banks);print('Return sources',dict(sources.stats),flush=True)
    ledger=v5.Ledger(c,banks);pred={};audit=[];counts=Counter()
    for n,tid in enumerate(sorted(banks,key=lambda x:(banks[x]['booking_date'],x)),1):
        t=banks[tid];ledger.current_date=t['booking_date']
        if hasattr(base,'as_of'):base.as_of=t['booking_date']
        before=incumbent[tid];out=before;reason='v5_incumbent'
        proposal=propose(t,before,c,ledger,sources,enabled)
        if proposal and not v5.same(proposal[0],before):
            out,reason=proposal
            audit.append(dict(bank_txn_id=tid,reason=reason,before=before,after=out))
        pred[tid]=out;counts[reason]+=1
        # Competition ledger: replay all selected allocations; no label lookup.
        # A later source-linked return reopens the exact source amount.
        ledger.advance(t,out,True)
        if n%25000==0:print(f'{phase}: {n:,}/{len(banks):,}; changed {len(audit):,}',flush=True)
    path=WORK/f'{phase}_overlay.csv';v5.dump_rows(path,pred,banks)
    with (WORK/f'{phase}_audit.jsonl').open('w') as f:
        for r in audit:f.write(json.dumps(r,ensure_ascii=False)+'\n')
    summary=dict(phase=phase,bank_lines=len(banks),changed_vs_v5=len(audit),methods=dict(counts),pdf_facts=dict(c.stats),return_index=dict(sources.stats),
        seconds=round(time.monotonic()-start,2),training_performed=False,new_llm_calls=0,model_sha256=MODEL_SHA,
        enabled=sorted(enabled or {'returns','service','replacement','netting','policy','refund','partial_group','advance','fee','related_net'}))
    if phase=='test':
        m,module,g=scoring();result=m.score(module,g,pred);old=m.score(module,g,incumbent)
        # One-rule ablations use exactly the same before/after candidate rows.
        ablations={}
        for reason in sorted({r['reason'] for r in audit}):
            only=dict(incumbent)
            for r in audit:
                if r['reason']==reason:only[r['bank_txn_id']]=r['after']
            rr=m.score(module,g,only);ablations[reason]=dict(changes=sum(r['reason']==reason for r in audit),score=rr['score'],delta=round(rr['score']-old['score'],2))
        report=dict(v6=result,v5=old,delta=round(result['score']-old['score'],2),ablations=ablations,
            scope='7,500 Jan–May 2025 cached development bank lines. Prior inspected fixture, not a fresh blind test. Calibration examples July–December 2024. No refitting; existing v5 LLM decisions replayed. LIVE score requires website.')
        write_json(RESULTS/'development_score.json',report)
        print('V6 development',result['score'],'vs V5',old['score'],'ablations',ablations,flush=True)
    write_json(RESULTS/f'{phase}_overlay.json',summary);base.db.close();print(summary,flush=True)


def publish():
    banks={r['bank_txn_id']:r for r in rows(table(ROOT/'work/archives/live/live','bank_transactions'))}
    target=WORK/'live_overlay.csv';c,_=v5.open_catalog('live');pred=v5.read_predictions(target)
    validation=validate(target,banks,c)
    soft=[e for e in validation['errors'] if e['message']=='aggregate allocation exceeds remaining balance']
    validation['errors']=[e for e in validation['errors'] if e not in soft]
    validation['warnings'].extend(soft);validation['ok']=not validation['errors']
    validation['competition_note']='Aggregate-ledger conflicts remain diagnostics as in v3–v5. All schema, membership, row amount, chronology and coverage checks block publication.'
    if target.stat().st_size>60000000:raise ValueError('File exceeds conservative 60 MB limit')
    # Full ledger diagnostics, rather than the display-capped validator list.
    def conflicts(path):
        balance={};count=0
        for r in rows(path):
            if not r['item_id']:continue
            i=c.item(r['item_id']);b=balance.get(i['iid'],i['initial']);a=cents(r['amount'])
            if r['exception']=='RETURNED':balance[i['iid']]=min(i['total'],b+a)
            elif r['exception']!='DUPLICATE_PAYMENT':
                count+=a>b;balance[i['iid']]=max(0,b-a)
        return count
    validation['aggregate_conflict_rows']=conflicts(target)
    validation['v5_aggregate_conflict_rows']=conflicts(ROOT/'v5-submission.csv')
    write_json(RESULTS/'live_validation.json',validation)
    if not validation['ok']:raise ValueError(validation['errors'])
    spec=importlib.util.spec_from_file_location('v6_official_schema',v5.DOCS/'starter/bankrec_score.py');m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
    registry=m.Golden();registry.txns={tid:({},'','','validation_only') for tid in banks};registry.weight={tid:1. for tid in banks}
    registry.exceptions=sorted(EXCEPTIONS);registry.categories=sorted(c.categories)
    parsed=m.score_submission(registry,target.read_bytes(),'submission.csv')
    schema=dict(ok=parsed['ok'],errors=parsed['errors'],scope='Official parser with LIVE bank registry only. No LIVE golden or score. Synthetic score discarded.')
    write_json(RESULTS/'official_schema.json',schema)
    if not parsed['ok']:raise ValueError(parsed['errors'])
    folder=ROOT/'submission/v6-strategy';folder.mkdir(exist_ok=True)
    dests=[ROOT/'v6-submission.csv',ROOT/'submission/submission_v6_live_001.csv',folder/'submission_v6_live_001.csv']
    for dest in dests:
        if dest.exists() and digest(dest)!=digest(target):raise ValueError('Immutable v6 edition exists')
        shutil.copyfile(target,dest)
    record=dict(edition='001',phase='LIVE',sha256=digest(target),bytes=target.stat().st_size,rows=validation['rows'],bank_lines=len(banks),
        model_sha256=MODEL_SHA,input_v5_sha256=V5_SHA,training_performed=False,new_llm_calls=0,
        files=[str(d.relative_to(ROOT)) for d in dests],website_score=None,
        source_sha256={p.name:digest(p) for p in Path(__file__).parent.glob('*.py')})
    write_json(ROOT/'version-6/editions/live_001.json',record);write_json(folder/'live_001.json',record)
    c.db.close();print('UPLOAD FILE:',dests[0],flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--phase',choices=['test','live'],default='test');p.add_argument('--publish',action='store_true')
    p.add_argument('--rules',help='Comma-separated rule families for an ablation; omitted means all')
    args=p.parse_args()
    if args.publish:publish()
    else:build(args.phase,set(args.rules.split(',')) if args.rules else None)
