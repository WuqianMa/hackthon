"""Cached v5 policy/recovery overlay and replayable bounded LLM decisions."""
from collections import defaultdict,Counter
from datetime import date
import argparse
import csv
import hashlib
import importlib.util
import json
from pathlib import Path
import shutil
import sqlite3
import sys

import joblib

ROOT=Path(__file__).resolve().parent.parent
sys.path.insert(0,str(ROOT));sys.path.insert(0,str(ROOT/'version-4'))
from data import load_strategy
from bankrec.io import rows,table,FIELDS,cents,money,norm,plain,digest,write_json,HASHES
from bankrec.engine import text_of,is_return
from bankrec.catalog import tokens
from bankrec.validate import validate
from train_live import amount_contract_guard,dump_rows
from policy import propose as policy_propose,source_supported
from recovery import propose as recovery_propose,pool_category
from review import apply_decisions

WORK=ROOT/'work/version-5';RESULTS=ROOT/'version-5/results'
DOCS=ROOT/'work/archives/docs'
MODEL=ROOT/'version-4/models/train_001.joblib'


def read_predictions(path):
    out=defaultdict(list)
    for r in rows(path):out[r['bank_txn_id']].append([r[k] for k in FIELDS])
    return dict(out)


def same(a,b):return sorted(map(tuple,a))==sorted(map(tuple,b))


def verify_inputs():
    if digest(MODEL)!='a883a203fc5bc694812895a14cbd8b125870f435a67bc5e7627ab42e4526eccb':raise ValueError('Frozen model changed')
    if digest(ROOT/'v4-submission.csv')!='f3f9262153d47c927a96da78d2df9821cdb73738db698fbfb6acc5c7a37113f1':raise ValueError('V4 incumbent changed')


def open_catalog(phase):
    cm,_,em=load_strategy()
    if phase=='live':
        folder=ROOT/'work/version-4-train/live';c=object.__new__(cm.Catalog)
        c.__dict__.update(joblib.load(folder/'catalog_state.joblib'))
    else:
        from production_data import DiskCatalog,Metadata
        folder=ROOT/'work/version-4-train';c=object.__new__(DiskCatalog)
        c.__dict__.update(joblib.load(folder/'catalog_state.joblib'));c.metadata=Metadata(c)
    c.db=sqlite3.connect(f'file:{folder / "catalog.sqlite"}?mode=ro',uri=True);c.db.row_factory=sqlite3.Row
    c.db.execute('PRAGMA cache_size=-131072');c.db.execute('PRAGMA mmap_size=1073741824')
    c.bank_accounts={r['account_id']:r for r in rows(table(DOCS/'masters','bank_accounts'))}
    return c,em


class Ledger:
    def __init__(self,c,banks):
        self.c=c;self.bal={};self.bad=set();self.last={};self.current_date='';self.operations=[]
        self.refs=defaultdict(list);self.pool_pairs=set()
        opposite=defaultdict(list)
        for t in banks.values():opposite[(t['booking_date'],t['currency'],cents(t['amount']))].append(t)
        for t in banks.values():
            own=c.bank_accounts.get(t['account_id'],{});purpose=plain(own.get('purpose',''))
            if not any(k in purpose for k in ('POOL','HEADER','PARTICIPANT','CONCENTR')):continue
            if any(k in plain(text_of(t)) for k in ('FINANCIACION','INTERCOMPANY','FUNDING','LOAN','PRESTAMO')):continue
            for other in opposite[(t['booking_date'],t['currency'],-cents(t['amount']))]:
                if other['account_id']==t['account_id']:continue
                other_purpose=plain(c.bank_accounts.get(other['account_id'],{}).get('purpose',''))
                if any(k in plain(text_of(other)) for k in ('FINANCIACION','INTERCOMPANY','FUNDING','LOAN','PRESTAMO')):continue
                header=any(k in purpose for k in ('CABECERA','HEADER'))
                other_header=any(k in other_purpose for k in ('CABECERA','HEADER'))
                if header!=other_header and any(k in other_purpose for k in ('POOL','HEADER','PARTICIPANT','CONCENTR')):
                    self.pool_pairs.add(t['bank_txn_id']);self.pool_pairs.add(other['bank_txn_id'])

    def balance(self,iid):
        if iid not in self.bal:self.bal[iid]=self.c.item(iid)['initial']
        return self.bal[iid]

    def confident(self,iid):return (self.c.phase.name in ('live','final') or iid in self.last) and iid not in self.bad and self.last.get(iid)!=self.current_date

    def cash_pool_pair(self,t):return t['bank_txn_id'] in self.pool_pairs

    def original_operation(self,t):
        keys={k for k in tokens(text_of(t)) if len(k)>=8 and sum(x.isdigit() for x in k)>=4}
        found={}
        for key in keys:
            for op,rs in self.refs.get((t['account_id'],key),[]):
                age=(date.fromisoformat(t['booking_date'])-date.fromisoformat(op['booking_date'])).days
                if 0<=age<=180 and op['currency']==t['currency'] and cents(op['amount'])*cents(t['amount'])<0 and abs(abs(cents(op['amount']))-abs(cents(t['amount'])))<=1:
                    found[op['bank_txn_id']]=rs
        if len(found)==1:return next(iter(found.values()))
        return None

    def advance(self,t,allocations,strong):
        for r in allocations:
            if not r[1]:continue
            i=self.c.item(r[1]);bal=self.balance(r[1]);amount=cents(r[2])
            if not strong:self.bad.add(r[1]);continue
            if r[4]=='RETURNED':self.bal[r[1]]=min(i['total'],bal+amount)
            elif r[4]!='DUPLICATE_PAYMENT':
                if amount>bal:self.bad.add(r[1])
                self.bal[r[1]]=max(0,bal-amount)
            self.last[r[1]]=t['booking_date']
        if strong and allocations[0][1] and not is_return(t):
            for k in tokens(text_of(t)):
                if len(k)>=8 and sum(x.isdigit() for x in k)>=4:self.refs[(t['account_id'],k)].append((t,allocations))


def cached_excerpt(item,phase_folder):
    source=json.loads(item['facts']).get('source','')
    if not source:return ''
    path=Path(phase_folder)/source
    if not path.exists():return ''
    p=ROOT/'work/cache/pdf_text'/(digest(path)+'.txt')
    return p.read_text(encoding='utf-8')[:1800] if p.exists() else ''


def review_packet(t,current,static,incumbent,c,ledger,engine,force=False):
    text=plain(text_of(t));tid=t['bank_txn_id'];items={r[1] for r in current+static+incumbent if r[1]}
    marker=any(w in text for w in ('MANT','SERVIC','RETEN','PLAZO','INSTAL','REMAINDER','ADVANCE','A CUENTA'))
    disagree=not same(current,static)
    if not force and not (disagree or marker or current[0][3]=='UNIDENTIFIED'):return None
    party=set()
    for iid in items:party.add(c.item(iid)['party'])
    if not party:party=c.identify(t.get('counterparty_name') or text_of(t),entity=t['entity'],iban=t.get('counterparty_account',''))
    pool=[i for i in c.by_party(party,t['booking_date']) if i['currency']==(t.get('orig_currency') or t['currency']) and not json.loads(i['facts']).get('cancelled')]
    cash=abs(cents(t.get('orig_amount') or t['amount']))
    pool=sorted(pool,key=lambda i:(abs(i['initial']-cash),-date.fromisoformat(i['issue']).toordinal(),i['iid']))[:8]
    options=[];seen=set()
    def add(label,rs):
        key=tuple(sorted(map(tuple,rs)))
        if key in seen:return
        seen.add(key);options.append(dict(id=f'C{len(options)}',origin=label,rows=rs))
    add('v5_incumbent',incumbent);add('v4',current);add('v3',static)
    add('no_supported_item',[[tid,'','','UNIDENTIFIED','UNIDENTIFIED']])
    for i in pool:
        j=dict(i);j['balance']=ledger.balance(i['iid'])
        if j['balance']<=0:continue
        paid=engine.item_cash(j,t)
        if paid is not None and abs(paid-j['balance'])<=max(1,int(j['balance']*.04)):
            a,e=engine.policy(j,paid,t,force_return=is_return(t))
            add('retrieved_item',[[tid,i['iid'],money(a),'',e]])
    for op in options:
        for r in op['rows']:
            if r[1]:items.add(r[1])
    evidence=[]
    for iid in sorted(items):
        i=c.item(iid);evidence.append(dict(item_id=iid,document=i['doc'],party=i['party'],currency=i['currency'],issue=i['issue'],due=i['due'],total=money(i['total']),balance_before=money(ledger.balance(iid)),balance_confident=ledger.confident(iid),facts=json.loads(i['facts']),cached_text=cached_excerpt(i,c.phase)))
    packet=dict(bank=t,candidates=options,items=evidence,priority=3*marker+2*disagree+(current[0][3]=='UNIDENTIFIED'),
        allowed_actions=['KEEP','CHOOSE','EXTRACT_FACT','ABSTAIN'],golden_supplied=False)
    packet['packet_sha256']=hashlib.sha256(json.dumps(packet,sort_keys=True).encode()).hexdigest()
    return packet


def load_inputs(phase):
    if phase=='live':
        banks={r['bank_txn_id']:r for r in rows(table(ROOT/'work/archives/live/live','bank_transactions'))}
        current=read_predictions(ROOT/'v4-submission.csv');static=read_predictions(ROOT/'submission/static-strategy/submission_v3_live_001.csv')
        methods={}
        for r in (json.loads(line) for line in (ROOT/'work/version-3/artifacts/live/evidence.jsonl').open()):methods[r['bank_txn_id']]=r['method']
    else:
        banks={r['bank_txn_id']:r for r in rows(ROOT/'work/version-4-train/test_labels/bank_transactions.csv')}
        current=read_predictions(ROOT/'work/version-4-train/held_out_predictions.csv');static={};methods={}
        for p in sorted((ROOT/'work/version-4-train/shards').glob('2025-0[1-5].joblib')):
            d=joblib.load(p);static.update(d['static'])
    return banks,current,static,methods


def build(phase,packet_limit=48):
    WORK.mkdir(exist_ok=True);RESULTS.mkdir(exist_ok=True)
    verify_inputs()
    banks,current,static,methods=load_inputs(phase);c,em=open_catalog(phase);engine=em.Engine(c,None)
    recovery_keys=[];review_keys=[];controls=[]
    for tid,t in banks.items():
        txt=plain(text_of(t));h=hashlib.sha256(tid.encode()).hexdigest()
        marker=any(w in txt for w in ('MANT','SERVIC','RETEN','PLAZO','INSTAL','RETURN','DEVOL','CASH','TRASPASO','ZBA'))
        changed=not same(current[tid],static[tid])
        if marker or current[tid][0][3]=='UNIDENTIFIED' or 'credit' in methods.get(tid,''):
            recovery_keys.append((-int(marker),h,tid))
        if changed or marker:review_keys.append((-(3*marker+2*changed),h,tid))
        else:controls.append((h,tid))
    recovery_set={x[-1] for x in sorted(recovery_keys)[:6000]}
    review_set={x[-1] for x in sorted(review_keys)[:max(0,packet_limit-8)]}|{x[-1] for x in sorted(controls)[:8]}
    ledger=Ledger(c,banks);pred={};audit=[];packets=[];counts=Counter();recoveries=0
    for n,tid in enumerate(sorted(banks,key=lambda x:(banks[x]['booking_date'],x)),1):
        t=banks[tid];ledger.current_date=t['booking_date']
        if hasattr(c,'as_of'):c.as_of=t['booking_date']
        original=current[tid];out=original;reason='v4_incumbent';method=methods.get(tid,'sampled_static')
        proposal=policy_propose(t,out,static[tid],c,ledger,method)
        if proposal:out,reason=proposal
        if out[0][3] in ('','UNIDENTIFIED','INTERNAL_TRANSFER','CASH_POOL'):
            pool=pool_category(t,c,ledger)
            if pool and not same(pool[0],out):out,reason=pool
        # Targeted retrieval only; generic easy bank lines do not query broad pools.
        txt=plain(text_of(t));trigger=out[0][3]=='UNIDENTIFIED' or any(w in txt for w in ('MANT','SERVIC','RETURN','DEVOL','R-TRAN','CASH','TRASPASO','ZBA')) or 'credit' in method
        if tid in recovery_set:
            recoveries+=1;proposal=recovery_propose(t,out,static[tid],c,ledger,None)
            if proposal:out,reason=proposal
        pred[tid]=out;counts[reason]+=1
        if not same(out,original):audit.append(dict(bank_txn_id=tid,reason=reason,before=original,after=out))
        if tid in review_set:
            # Preserve only a bounded priority queue; packets contain no labels.
            packet=review_packet(t,original,static[tid],out,c,ledger,engine,force=True)
            if packet:
                packets.append(packet)
                if len(packets)>packet_limit*2:packets=sorted(packets,key=lambda p:(-p['priority'],hashlib.sha256(p['bank']['bank_txn_id'].encode()).hexdigest()))[:packet_limit]
        strong=reason!='v4_incumbent' or (same(out,static[tid]) and source_supported(method))
        ledger.advance(t,out,strong)
        if n%25000==0:print(f'{phase}: {n:,}/{len(banks):,}; changes {len(audit):,}',flush=True)
    repairs=amount_contract_guard(pred,static,c)
    target=WORK/f'{phase}_overlay.csv';dump_rows(target,pred,banks)
    with (WORK/f'{phase}_audit.jsonl').open('w') as f:
        for r in audit:f.write(json.dumps(r)+'\n')
    packets=sorted(packets,key=lambda p:(-p['priority'],hashlib.sha256(p['bank']['bank_txn_id'].encode()).hexdigest()))[:packet_limit]
    with (WORK/f'llm_packets_{phase}.jsonl').open('w') as f:
        for r in packets:f.write(json.dumps(r,ensure_ascii=False)+'\n')
    if phase=='live':shutil.copyfile(WORK/'llm_packets_live.jsonl',WORK/'llm_packets.jsonl')
    summary=dict(phase=phase,bank_lines=len(banks),changes=sum(not same(pred[t],current[t]) for t in banks),methods=dict(counts),recovery_queries=recoveries,contract_repairs=len(repairs),llm_queue=len(packets),model_sha256=digest(MODEL),training_performed=False)
    c.db.close();write_json(RESULTS/f'{phase}_overlay.json',summary)
    return summary


def evaluate():
    sys.path.insert(0,str(ROOT/'version-4'))
    spec=importlib.util.spec_from_file_location('v5_scoring',ROOT/'version-4/run.py');m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
    module,g=m.official(dict(docs=DOCS,phase=ROOT/'work/version-4-train/test_labels'))
    result=m.score(module,g,read_predictions(WORK/'test_overlay.csv'))
    baseline=m.score(module,g,read_predictions(ROOT/'work/version-4-train/held_out_predictions.csv'))
    write_json(RESULTS/'development_score.json',dict(v5=result,v4=baseline,scope='Existing inspected 7,500-case cached temporal development fixture; no retraining',delta=round(result['score']-baseline['score'],2)))
    print('V5 development score',result['score'],'vs',baseline['score'],flush=True)


def evaluate_llm():
    spec=importlib.util.spec_from_file_location('v5_scoring',ROOT/'version-4/run.py');m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
    packets={p['bank']['bank_txn_id']:p for p in map(json.loads,(WORK/'llm_packets_test.jsonl').open())}
    decisions=[]
    for name in ('llm_test_routed.jsonl','llm_test_controls.jsonl'):
        decisions.extend(map(json.loads,(WORK/name).open()))
    c,_=open_catalog('test');pred=read_predictions(WORK/'test_overlay.csv')
    audit=apply_decisions(pred,packets,decisions,c);c.db.close()
    module,g=m.official(dict(docs=DOCS,phase=ROOT/'work/version-4-train/test_labels'))
    result=m.score(module,g,pred)
    base=m.score(module,g,read_predictions(WORK/'test_overlay.csv'))
    write_json(RESULTS/'llm_development_score.json',dict(result=result,without_llm=base,reviewed=len(audit),changed=sum(d['changed'] for d in audit),delta=round(result['score']-base['score'],2),audit=audit,
        scope='Frozen inference-routed 24-case LLM pilot including eight agreement controls; full 7,500-case development composite, no refit'))
    print('LLM pilot',result['score'],'vs',base['score'],'changed',sum(d['changed'] for d in audit),flush=True)


def publish():
    verify_inputs()
    banks,current,static,methods=load_inputs('live');c,em=open_catalog('live')
    pred=read_predictions(WORK/'live_overlay.csv')
    packets={p['bank']['bank_txn_id']:p for p in map(json.loads,(WORK/'llm_packets.jsonl').open())}
    llm=[];decision_file=WORK/'llm_decisions.jsonl'
    if decision_file.exists():
        llm=apply_decisions(pred,packets,map(json.loads,decision_file.open()),c)
    # Revisit downstream affected item episodes without treating an ambiguous
    # LLM choice as confirmed historical clearing.
    reviewed={x['bank_txn_id']:x for x in llm if x['changed']}
    affected={r[1] for x in reviewed.values() for r in x['before']+x['after'] if r[1]}
    automatic={json.loads(line)['bank_txn_id'] for line in (WORK/'live_audit.jsonl').open()}
    ledger=Ledger(c,banks);replayed=[]
    for tid in sorted(banks,key=lambda x:(banks[x]['booking_date'],x)):
        t=banks[tid];ledger.current_date=t['booking_date']
        if tid in reviewed:
            ledger.bad.update(r[1] for r in reviewed[tid]['before']+reviewed[tid]['after'] if r[1])
        elif any(r[1] in affected for r in pred[tid]):
            proposed=policy_propose(t,pred[tid],static[tid],c,ledger,methods.get(tid,''))
            if proposed and not same(proposed[0],pred[tid]):
                replayed.append(dict(bank_txn_id=tid,before=pred[tid],after=proposed[0],reason=proposed[1]));pred[tid]=proposed[0]
        strong=tid not in reviewed and (tid in automatic or (same(pred[tid],static[tid]) and source_supported(methods.get(tid,''))))
        ledger.advance(t,pred[tid],strong)
    write_json(RESULTS/'episode_replay.json',dict(affected_items=len(affected),downstream_changes=replayed,scope='LLM decisions remain uncertain; prior source-based ledger is replayed without hidden labels'))
    repairs=amount_contract_guard(pred,static,c)
    target=WORK/'submission_v5_live_001.csv';dump_rows(target,pred,banks)
    validation=validate(target,banks,c)
    soft=[e for e in validation['errors'] if e['message']=='aggregate allocation exceeds remaining balance']
    validation['errors']=[e for e in validation['errors'] if e not in soft];validation['warnings'].extend(soft);validation['ok']=not validation['errors']
    validation['competition_note']='Same disclosed diagnostic aggregate-balance profile as v3/v4; hard schema/membership/coverage rules remain blocking.'
    write_json(RESULTS/'live_validation.json',validation)
    if not validation['ok']:raise ValueError('V5 validation failed')
    spec=importlib.util.spec_from_file_location('v5_official_schema',DOCS/'starter/bankrec_score.py');m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
    registry=m.Golden();registry.txns={t:({},'','','validation_only') for t in banks};registry.weight={t:1. for t in banks}
    from bankrec.io import EXCEPTIONS
    registry.exceptions=sorted(EXCEPTIONS);registry.categories=sorted(c.categories)
    parsed=m.score_submission(registry,target.read_bytes(),'submission.csv')
    write_json(RESULTS/'official_schema.json',dict(ok=parsed['ok'],errors=parsed['errors'],scope='Bank registry only; no LIVE golden or score'))
    if not parsed['ok']:raise ValueError('Official schema rejected V5')
    directory=ROOT/'submission/v5-strategy';directory.mkdir(exist_ok=True)
    destinations=[ROOT/'v5-submission.csv',ROOT/'submission/submission_v5_live_001.csv',directory/target.name]
    for dest in destinations:
        if dest.exists() and digest(dest)!=digest(target):raise ValueError('Immutable V5 edition already exists')
        shutil.copyfile(target,dest)
    write_json(RESULTS/'llm_audit.json',dict(reviewed=len(llm),changed=sum(x['changed'] for x in llm),runtime='Codex collaboration LLM review; cached explicit decisions',decisions=llm))
    record=dict(phase='live',edition='001',bank_lines=len(banks),rows=validation['rows'],bytes=target.stat().st_size,sha256=digest(target),model_sha256=digest(MODEL),training_performed=False,
        changed_vs_v4=sum(not same(pred[t],current[t]) for t in banks),llm_reviewed=len(llm),llm_changed=sum(x['changed'] for x in llm),contract_fallbacks=len(repairs),
        files=[str(p.relative_to(ROOT)) for p in destinations],validation=validation,website_score=None,
        input_v4_sha256=digest(ROOT/'v4-submission.csv'),input_v3_sha256=digest(ROOT/'submission/static-strategy/submission_v3_live_001.csv'),archive_hashes=HASHES,
        source_sha256={p.name:digest(p) for p in Path(__file__).parent.glob('*.py')})
    write_json(ROOT/'version-5/editions/live_001.json',record);write_json(directory/'live_001.json',record)
    c.db.close();print('UPLOAD FILE:',destinations[0],flush=True)


def main():
    p=argparse.ArgumentParser();p.add_argument('--phase',choices=['test','live'],default='test');p.add_argument('--publish',action='store_true');p.add_argument('--evaluate-llm',action='store_true');p.add_argument('--packet-limit',type=int,default=48);args=p.parse_args()
    if args.evaluate_llm:evaluate_llm();return
    if args.publish:publish();return
    print(build(args.phase,args.packet_limit),flush=True)
    if args.phase=='test':evaluate()


if __name__=='__main__':main()
