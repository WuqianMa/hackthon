"""TRAIN-fitted v4 -> LIVE CSV. No LLM execution path or provider dependency.

Run from the repository root: python3 version-4/train_live.py
"""
from collections import Counter,defaultdict
import argparse
import csv
import gc
import json
from pathlib import Path
import shutil
import sqlite3
import time

import joblib
import numpy as np
from threadpoolctl import threadpool_limits

from data import ROOT,generate,load_strategy
from production_data import catalog,MonthSources,month_view,sample_banks,role
from run import load_labels,complete,fit_model,predict,hypotheses,official,score,select,HYPOTHESIS_FEATURES
from bankrec.io import extract,HASHES,find_folder,rows,table,write_json,digest,FIELDS
from bankrec.cli import reversal_pairs
from bankrec.validate import validate

WORK=ROOT/'work/version-4-train'
RESULTS=ROOT/'version-4/training-results'
ROLE_ORDER={'pair_fit':0,'hypothesis_fit':1,'calibration':2,'test':3}


def dump_rows(path,predictions,banks):
    with path.open('w',encoding='utf-8',newline='') as f:
        w=csv.writer(f,lineterminator='\n');w.writerow(FIELDS)
        for tid in sorted(predictions,key=lambda t:(banks[t]['booking_date'],t)):
            w.writerows(sorted(predictions[tid],key=lambda r:tuple(r[1:])))


def prepare_train(phase,docs,per_month):
    manifest=WORK/'sample_manifest.json'
    identity=dict(per_month=per_month,train_sha256=HASHES['train'],docs_sha256=HASHES['docs'],
        generation_sha256={name:digest(Path(__file__).parent/name) for name in ('data.py','production_data.py')})
    if manifest.exists():
        old=json.loads(manifest.read_text())
        if old['per_month']!=per_month:raise ValueError('Use a new work directory for changed sampling')
        if old.get('cache_identity')!=identity and any((WORK/'shards').glob('*.joblib')):
            raise ValueError('TRAIN shards belong to different candidate code/settings; rebuild derived shards and ledger')
    selected,counts=sample_banks(phase,per_month)
    write_json(manifest,dict(cache_identity=identity,per_month=per_month,bank_counts=counts,selected={m:list(t) for m,t in selected.items()},
        roles={m:role(m+'-01') for m in selected},labels_used_for_sampling=False,
        input_archive_sha256=HASHES['train'],sampling='Lowest SHA256(v4-train-42:bank_txn_id) per month',
        history='Static bank ledger replays selected transactions only; all invoice history searchable; no golden balance inputs.'))
    pending=[m for m in selected if not (WORK/'shards'/f'{m}.joblib').exists()]
    if not pending:return
    c=catalog(WORK,phase,docs/'masters');_,_,em=load_strategy()
    (WORK/'shards').mkdir(exist_ok=True)
    for month in pending:
        started=time.monotonic();banks=selected[month]
        print(f'TRAIN {month}: {len(banks):,} selected bank lines; sources...',flush=True)
        c.as_of='9999-12-31'
        sources=MonthSources(month_view(phase,WORK,month),ROOT/'work/cache/pdf_text',c)
        engine=em.Engine(c,sources);engine.speculative=True
        static={};reversed_ids=reversal_pairs(banks)
        for tid,t in banks.items():
            c.as_of=t['booking_date'];static[tid]=engine.reconcile(t,reversed_ids)[0]
        dataset=generate(c,sources,banks,static,phase,docs)
        joblib.dump(dataset,WORK/'shards'/f'{month}.joblib',compress=3)
        c.db.commit()
        print(f'TRAIN {month}: {len(dataset["pair_rows"]):,} pairs, {time.monotonic()-started:.1f}s',flush=True)
        del dataset,sources,static,engine;gc.collect()
    c.db.close()


def attach_targets(phase,selected):
    """Targets enter only after independent candidates. Purge cross-role item episodes."""
    golden=defaultdict(dict);noitem={};segments={};highest={}
    for r in rows(table(phase,'golden_allocations')):
        tid=r['bank_txn_id']
        if tid not in selected:continue
        segments[tid]=r['segment']
        if r['item_id']:
            golden[tid][r['item_id']]=r
            highest[r['item_id']]=max(highest.get(r['item_id'],-1),ROLE_ORDER[selected[tid]])
        else:noitem[tid]=r
    purged={t for t,gi in golden.items() if any(highest[i]>ROLE_ORDER[selected[t]] for i in gi)}
    missing=set(selected)-set(golden)-set(noitem)
    if missing:raise ValueError(f'{len(missing)} selected TRAIN transactions missing golden')
    return golden,noitem,segments,purged


def train_models(phase,docs):
    bundle=WORK/'model.joblib'
    if bundle.exists() and (RESULTS/'held_out.json').exists():
        if json.loads((RESULTS/'held_out.json').read_text())['model_sha256']!=digest(bundle):
            raise ValueError('Saved holdout report does not describe the model bundle')
        return joblib.load(bundle)
    manifest=json.loads((WORK/'sample_manifest.json').read_text())
    roles={t:manifest['roles'][m] for m,ts in manifest['selected'].items() for t in ts}
    gold,noitem,segments,purged=attach_targets(phase,roles)
    write_json(RESULTS/'split.json',dict(roles=dict(Counter(roles[t] for t in roles if t not in purged)),
        selected=len(roles),purged=len(purged),purged_transactions=sorted(purged),
        rule='Earlier role transactions sharing any true item with a later role are purged before fitting/calibration.',
        llm_enabled=False))
    X=[];Y=[];features=None
    for shard in sorted((WORK/'shards').glob('*.joblib')):
        if manifest['roles'][shard.stem]!='pair_fit':continue
        d=joblib.load(shard);_,_,_,y=load_labels_subset(d,gold)
        keep=np.array([r[0] not in purged for r in d['pair_rows']]);X.append(d['X'][keep]);Y.append(y[keep]);features=d['feature_names']
    X=np.concatenate(X);Y=np.concatenate(Y)
    print(f'Fitting allocation model: {len(Y):,} rows, {sum(Y):,} positives',flush=True)
    with threadpool_limits(limits=4):pair=fit_model(X,Y)
    pair_count=len(Y);del X,Y;gc.collect()
    Hs=[];ys=[]
    for shard in sorted((WORK/'shards').glob('*.joblib')):
        if manifest['roles'][shard.stem]!='hypothesis_fit':continue
        d=joblib.load(shard)
        with threadpool_limits(limits=4):pp=predict(pair,d['X'])
        hyps,H,_=hypotheses(d,pp)
        keep=np.array([h['tid'] not in purged for h in hyps]);Hs.append(H[keep])
        ys.append(np.array([complete(h['rows'],gold,noitem) for h in hyps],dtype=np.int8)[keep])
    H=np.concatenate(Hs);hy=np.concatenate(ys)
    print(f'Fitting payment model: {len(hy):,} hypotheses, {sum(hy):,} positives',flush=True)
    with threadpool_limits(limits=4):head=fit_model(H,hy)
    hypothesis_count=len(hy);del H,hy,Hs,ys,d;gc.collect()
    # Official scorer receives only the sampled bank/golden rows (not 1.49M unpredicted cases).
    calibration={};calstatic={};cbanks={};choices={k:{} for k in [(a,b) for a in (.25,.5,.75,1.) for b in (0,.1,.2,1.)]}
    for shard in sorted((WORK/'shards').glob('*.joblib')):
        if manifest['roles'][shard.stem]!='calibration':continue
        d=joblib.load(shard)
        tids=[t for t in d['banks'] if t not in purged];cbanks.update({t:d['banks'][t] for t in tids});calstatic.update({t:d['static'][t] for t in tids})
        with threadpool_limits(limits=4):
            hyps,H,by_tx=hypotheses(d,predict(pair,d['X']));hp=predict(head,H)
        for a,b in choices:choices[a,b].update(select(hyps,by_tx,hp,tids,a,b)[0])
    module,golden=scorer_subset(phase,docs,cbanks,WORK/'calibration_labels')
    scores=[];best=None
    for (a,b),prediction in choices.items():
        result=score(module,golden,prediction);scores.append(dict(alpha=a,static_bonus=b,score=result['score']))
        key=(result['score'],b,a)
        if best is None or key>best[0]:best=(key,a,b,result)
    _,alpha,bonus,calibration_score=best
    write_json(RESULTS/'calibration.json',dict(grid=scores,selected=dict(alpha=alpha,static_bonus=bonus),
        result=calibration_score,static=score(module,golden,calstatic)))
    model=dict(pair=pair,hypothesis=head,alpha=alpha,static_bonus=bonus,features=features,
        hypothesis_features=HYPOTHESIS_FEATURES+['mean_'+f for f in features[:38]],
        llm_enabled=False,pair_training_rows=pair_count,hypothesis_training_rows=hypothesis_count,
        train_archive_sha256=HASHES['train'],per_month=manifest['per_month'])
    joblib.dump(model,bundle,compress=3)
    # Freeze before the first evaluation read. Held-out test cannot alter this bundle.
    model_sha=digest(bundle)
    test={};static={};banks={};coverage=set();correct=regressed=0
    for shard in sorted((WORK/'shards').glob('*.joblib')):
        if manifest['roles'][shard.stem]!='test':continue
        d=joblib.load(shard);pred,methods=infer(d,model)
        test.update(pred);static.update(d['static']);banks.update(d['banks'])
        for tid,iid,a,_,_ in d['pair_rows']:
            if iid in gold.get(tid,{}) and amount_ok(a,gold[tid][iid]['amount']):coverage.add((tid,iid))
    module,golden=scorer_subset(phase,docs,banks,WORK/'test_labels')
    result=score(module,golden,test);base=score(module,golden,static)
    dump_rows(WORK/'held_out_predictions.csv',test,banks)
    for tid in banks:
        before=complete(static[tid],gold,noitem);after=complete(test[tid],gold,noitem)
        correct+=bool(after and not before);regressed+=bool(before and not after)
    report=dict(score=result['score'],baseline_score=base['score'],delta=round(result['score']-base['score'],2),
        result=result,baseline=base,transactions=len(banks),newly_correct=correct,regressed=regressed,
        candidate_pair_recall=len(coverage)/max(1,sum(len(gold.get(t,{})) for t in banks)),
        model_sha256=model_sha,llm_calls=0,
        scope='Deterministic 1,500/month TRAIN sample; January–May 2025 locked temporal holdout. Static ledger history is sampled, not complete.',
        limitations=['Current master snapshot; not a historical master reconstruction.','Whole customer/group entities are not independently held out.','June 2025 inspected starter excluded.','No LIVE labels used.'])
    assert digest(bundle)==model_sha
    if not result['ok']:raise ValueError('Official scorer rejected held-out predictions')
    write_json(RESULTS/'held_out.json',report)
    print(f'LOCKED TRAIN HOLDOUT: v4 {result["score"]}; static {base["score"]}',flush=True)
    return model


def load_labels_subset(d,gold):
    from run import amount_ok
    y=np.array([int(iid in gold.get(tid,{}) and amount_ok(a,gold[tid][iid]['amount'])) for tid,iid,a,_,_ in d['pair_rows']],dtype=np.int8)
    return None,None,None,y


def scorer_subset(phase,docs,banks,folder):
    folder.mkdir(exist_ok=True)
    for name in ('bank_transactions','golden_allocations'):
        inp=table(phase,name)
        with (folder/f'{name}.csv').open('w',newline='') as f:
            reader=rows(inp);first=next(reader);w=csv.DictWriter(f,fieldnames=list(first));w.writeheader()
            if first['bank_txn_id'] in banks:w.writerow(first)
            for r in reader:
                if r['bank_txn_id'] in banks:w.writerow(r)
    return official(dict(docs=docs,phase=folder))


def infer(d,model):
    if d['feature_names']!=model['features']:raise ValueError('Feature schema differs from fitted model')
    with threadpool_limits(limits=4):
        pp=predict(model['pair'],d['X']);hyps,H,by_tx=hypotheses(d,pp);hp=predict(model['hypothesis'],H)
    return select(hyps,by_tx,hp,list(d['banks']),model['alpha'],model['static_bonus'])


def live(docs,model,edition):
    # Verified LIVE-only input; use the already validated immutable static edition as a candidate.
    root,_=extract(ROOT/'bankrec-live.tar.gz',ROOT/'work/archives/live',HASHES['live']);phase=find_folder(root,'live')
    static_path=ROOT/'submission/static-strategy/submission_v3_live_001.csv'
    expected='3927ffc1f7f81c234844fbaeb68b97d2f53c4fc85d8bc8c33cc7253a261d8d05'
    if digest(static_path)!=expected:raise ValueError('Frozen static LIVE candidate hash changed')
    cm,sm,_=load_strategy();livework=WORK/'live';livework.mkdir(exist_ok=True)
    identity=dict(model_sha256=digest(WORK/'model.joblib'),live_archive_sha256=HASHES['live'],
                  candidate_code_sha256=digest(Path(__file__).parent/'data.py'))
    identity_path=livework/'run_identity.json'
    if identity_path.exists() and json.loads(identity_path.read_text())!=identity:
        raise ValueError('LIVE cache belongs to a different model/input/code; use a new work directory')
    write_json(identity_path,identity)
    db=livework/'catalog.sqlite'
    # Reuse the same source-catalog schema but reset its ledger to the opening snapshot.
    if not db.exists():
        print('Indexing LIVE catalog and PDF clauses...',flush=True)
        c=cm.Catalog(db,phase,docs/'masters',ROOT/'work/cache/pdf_text',True)
        state={k:v for k,v in c.__dict__.items() if k!='db'};joblib.dump(state,livework/'catalog_state.joblib',compress=3)
    else:
        c=object.__new__(cm.Catalog);c.__dict__.update(joblib.load(livework/'catalog_state.joblib'))
        c.db=sqlite3.connect(db);c.db.row_factory=sqlite3.Row
    print('Parsing LIVE source groups...',flush=True)
    sources=sm.Sources(phase,ROOT/'work/cache/pdf_text')
    banks={r['bank_txn_id']:r for r in rows(table(phase,'bank_transactions'))};static=defaultdict(list)
    for r in rows(static_path):static[r['bank_txn_id']].append([r[k] for k in FIELDS])
    if set(banks)!=set(static):raise ValueError('Static LIVE candidate coverage differs from bank input')
    predictions={};methods=Counter();order=sorted(banks,key=lambda t:(banks[t]['booking_date'],t));changed=0
    sharddir=livework/'predictions';sharddir.mkdir(exist_ok=True)
    for start in range(0,len(order),1000):
        file=sharddir/f'{start:06d}.joblib';tids=order[start:start+1000]
        if file.exists():out,method=joblib.load(file)
        else:
            batch={t:banks[t] for t in tids};d=generate(c,sources,batch,static,phase,docs)
            out,method=infer(d,model);joblib.dump((out,method),file,compress=3)
            del d;gc.collect()
        predictions.update(out);methods.update(method.values())
        changed+=sum(sorted(out[t])!=sorted(static[t]) for t in tids)
        print(f'LIVE {min(start+1000,len(order)):,}/{len(order):,}; changed {changed:,}',flush=True)
    target=livework/'submission.csv';dump_rows(target,predictions,banks)
    validation=validate(target,banks,c)
    aggregate=[e for e in validation['errors'] if e['message']=='aggregate allocation exceeds remaining balance']
    validation['errors']=[e for e in validation['errors'] if e not in aggregate];validation['warnings'].extend(aggregate)
    validation['ok']=not validation['errors'];validation['competition_note']='Aggregate cross-bank ledger checks are diagnostic, as in static v3; official schema rules remain strict.'
    write_json(RESULTS/'live_validation.json',validation)
    c.db.close()
    if not validation['ok']:raise ValueError('LIVE validation failed; no edition published')
    # Check the unchanged official parser with bank membership/coverage supplied independently above.
    import importlib.util
    spec=importlib.util.spec_from_file_location('live_official',docs/'starter/bankrec_score.py');mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod)
    # The scorer exposes no separate parser. A schema-only bank registry allows
    # validation; discard all metric fields because LIVE has no golden labels.
    registry=mod.Golden();registry.txns={t:({},'', '', 'validation_only') for t in banks}
    registry.weight={t:1. for t in banks};registry.categories=sorted(c.categories)
    registry.exceptions=sorted(__import__('bankrec.io',fromlist=['EXCEPTIONS']).EXCEPTIONS)
    parsed=mod.score_submission(registry,target.read_bytes(),'submission.csv')
    write_json(RESULTS/'live_official_schema.json',dict(ok=parsed['ok'],errors=parsed['errors'],
        scope='Schema-only bank registry, no golden and no score; metrics intentionally discarded.'))
    if not parsed['ok']:raise ValueError(f'Official LIVE parser rejected output: {parsed["errors"][:5]}')
    submission=ROOT/'submission';tracked=submission/'v4-strategy';tracked.mkdir(exist_ok=True)
    filename=f'submission_v4_live_{edition}.csv';published=submission/filename
    for dest in (published,tracked/filename):
        if dest.exists() and digest(dest)!=digest(target):raise ValueError(f'Immutable edition differs: {dest}')
        shutil.copyfile(target,dest)
    record=dict(phase='live',strategy='v4-static-ml',edition=edition,llm_enabled=False,llm_calls=0,
        bank_lines=len(banks),rows=validation['rows'],bytes=target.stat().st_size,
        submission_file=str(published.relative_to(ROOT)),tracking_file=str((tracked/filename).relative_to(ROOT)),
        sha256=digest(target),model_sha256=digest(WORK/'model.joblib'),train_archive_sha256=HASHES['train'],
        docs_archive_sha256=HASHES['docs'],live_archive_sha256=HASHES['live'],static_candidate_sha256=expected,changed_vs_static=changed,
        methods=dict(methods),validation=validation,website_score=None,website_status='Awaiting user upload and feedback',
        source_sha256={str(p.relative_to(ROOT)):digest(p) for p in Path(__file__).parent.glob('*.py')})
    write_json(ROOT/f'version-4/editions/live_{edition}.json',record)
    print(f'UPLOAD FILE: {published}',flush=True)


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--per-month',type=int,default=1500)
    parser.add_argument('--edition',default='001');parser.add_argument('--prepare-only',action='store_true')
    parser.add_argument('--mode',choices=['all','train','live'],default='all')
    args=parser.parse_args()
    if not args.edition.isdigit() or len(args.edition)!=3:parser.error('edition must have three digits')
    if args.per_month<1:parser.error('per-month must be positive')
    WORK.mkdir(exist_ok=True);RESULTS.mkdir(exist_ok=True)
    docs,_=extract(ROOT/'bankrec-docs-and-masters.zip',ROOT/'work/archives/docs',HASHES['docs'])
    portable=ROOT/'version-4/models/train_001.joblib'
    if args.mode=='live':
        metadata=json.loads((portable.with_suffix('.json')).read_text())
        if digest(portable)!=metadata['sha256']:raise ValueError('Published model checksum differs')
        model=joblib.load(portable)
        if not (WORK/'model.joblib').exists():shutil.copyfile(portable,WORK/'model.joblib')
        if digest(WORK/'model.joblib')!=metadata['sha256']:raise ValueError('Local model differs from published model')
        live(docs,model,args.edition);return
    root,_=extract(ROOT/'bankrec-train.tar.gz',ROOT/'work/archives/train',HASHES['train']);phase=find_folder(root,'train')
    prepare_train(phase,docs,args.per_month)
    if args.prepare_only:return
    model=train_models(phase,docs)
    portable.parent.mkdir(exist_ok=True)
    if portable.exists() and digest(portable)!=digest(WORK/'model.joblib'):raise ValueError('Immutable published model differs')
    shutil.copyfile(WORK/'model.joblib',portable)
    inventory=joblib.load(WORK/'catalog_state.joblib')
    write_json(portable.with_suffix('.json'),dict(sha256=digest(portable),sklearn_version=__import__('sklearn').__version__,
        numpy_version=np.__version__,train_archive_sha256=HASHES['train'],llm_enabled=False,llm_calls=0,
        pair_training_rows=model['pair_training_rows'],hypothesis_training_rows=model['hypothesis_training_rows'],
        alpha=model['alpha'],static_bonus=model['static_bonus'],features=model['features'],
        hypothesis_features=model['hypothesis_features'],catalog=dict(inventory['counts']),
        source_sha256={p.name:digest(p) for p in Path(__file__).parent.glob('*.py')}))
    if args.mode=='all':live(docs,model,args.edition)


from run import amount_ok
if __name__=='__main__':main()
