"""Five-fold, group-disjoint, two-head GBDT experiment on the starter only."""
from collections import Counter,defaultdict
import csv
import io
import importlib.util
import json
import math
from pathlib import Path
import sys
import time

import joblib
import numpy as np
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.model_selection import GroupKFold
from sklearn.metrics import average_precision_score,roc_auc_score
from threadpoolctl import threadpool_limits

from data import ROOT,prepare,EXCEPTIONS
from bankrec.io import rows,table,cents,digest,write_json,FIELDS
from tier3 import ambiguity_packet

WORK=ROOT/'work/version-4'
RESULTS=ROOT/'version-4/results'
KINDS=['static','unidentified','source','probset','top','static_blank']
HYPOTHESIS_FEATURES=['log_items','log_cash','log_allocated_sum','relative_net_cash_gap','net_cash_ratio',
 'min_pair_probability','max_pair_probability','mean_pair_probability','sum_pair_probability',
 'expected_item_count','selected_pool_fraction','static_row_agreement','static_item_count','candidate_variant_count',
 'format_n43','format_mt940','format_camt','negative_cash','static_was_unidentified','counterparty_name_length',
 'log_original_amount','has_original_currency']+['exception_share_'+e for e in EXCEPTIONS]+['kind_'+k for k in KINDS]+[
 'category_unidentified','category_bank_fees','category_cash_pool','reserved_other_category']


def amount_ok(a,b):
    return abs(float(a)-float(b))<=max(.01,.005*abs(float(b)))+1e-9


def load_labels(dataset):
    by_tx=defaultdict(dict); noitem={};segments={}
    for r in rows(table(dataset['phase'],'golden_allocations')):
        tid=r['bank_txn_id'];segments[tid]=r['segment']
        if r['item_id']:by_tx[tid][r['item_id']]=r
        else:noitem[tid]=r
    y=np.array([int(iid in by_tx[tid] and amount_ok(a,by_tx[tid][iid]['amount']))
                for tid,iid,a,_,_ in dataset['pair_rows']],dtype=np.int8)
    return by_tx,noitem,segments,y


def complete(rows_,gold,noitem):
    tid=rows_[0][0]
    if rows_[0][1]:
        ids=[r[1] for r in rows_]
        if len(ids)!=len(set(ids)) or set(ids)!=set(gold.get(tid,{})):return 0
        return int(all(amount_ok(r[2],gold[tid][r[1]]['amount']) and r[4]==gold[tid][r[1]]['exception'] for r in rows_))
    g=noitem.get(tid)
    return int(len(rows_)==1 and g is not None and rows_[0][3]==g['category'] and rows_[0][4]==g['exception'])


class Union:
    def __init__(self,keys):self.parent={k:k for k in keys}
    def root(self,k):
        while self.parent[k]!=k:
            self.parent[k]=self.parent[self.parent[k]];k=self.parent[k]
        return k
    def join(self,a,b):
        a,b=self.root(a),self.root(b)
        if a!=b:self.parent[max(a,b)]=min(a,b)


def partition(dataset,gold):
    keys=sorted(dataset['banks']);u=Union(keys);seen={}
    for tid in keys:
        for iid in gold.get(tid,{}):
            if iid in seen:u.join(tid,seen[iid])
            else:seen[iid]=tid
    groups=[u.root(tid) for tid in keys]
    if len(set(groups))<5:raise ValueError('Insufficient independent item episodes for five folds')
    assignment={}
    for fold,(_,idx) in enumerate(GroupKFold(n_splits=5).split(np.zeros(len(keys)),groups=groups)):
        for n in idx:assignment[keys[n]]=fold
    assert all(assignment[a]==assignment[b] for a,b in ((tid,seen[i]) for tid in keys for i in gold.get(tid,{})))
    return assignment,Counter(groups)


def fit_model(X,y):
    if len(np.unique(y))<2:
        return float(np.mean(y)) if len(y) else 0.0
    model=HistGradientBoostingClassifier(learning_rate=.08,max_iter=100,max_leaf_nodes=15,
        min_samples_leaf=30,l2_regularization=2.0,early_stopping=False,random_state=42)
    model.fit(X,y)
    return model


def predict(model,X):
    if isinstance(model,float):return np.full(len(X),model)
    return model.predict_proba(X)[:,1]


def hypotheses(dataset,prob):
    hyps=[];features=[];by_tx={};expected={}
    for tid,t in dataset['banks'].items():
        ids=dataset['per_tx'][tid];best={}
        for j in ids:
            iid=dataset['pair_rows'][j][1]
            if iid not in best or prob[j]>prob[best[iid]]:best[iid]=j
        ordered=sorted(best.values(),key=lambda j:(-prob[j],j))
        expected[tid]=sum(prob[j] for j in ordered)
        options=list(dataset['base_hyps'][tid])
        for threshold in (.2,.5,.8):
            chosen=[j for j in ordered if prob[j]>=threshold]
            if chosen:options.append(dict(kind='probset',pair_ids=chosen,rows=[dataset['pair_rows'][j] for j in chosen]))
        for n in (1,2,3,5):
            chosen=ordered[:n]
            if chosen:options.append(dict(kind='top',pair_ids=chosen,rows=[dataset['pair_rows'][j] for j in chosen]))
        # Alternative blank exceptions, retaining the exact static item/amount set.
        blank=[]
        for j in dataset['base_hyps'][tid][0]['pair_ids']:
            row=dataset['pair_rows'][j]
            matches=[k for k in ids if dataset['pair_rows'][k][1:4]==row[1:4] and dataset['pair_rows'][k][4]=='']
            blank.append(matches[0] if matches else j)
        if blank:options.append(dict(kind='static_blank',pair_ids=blank,rows=[dataset['pair_rows'][j] for j in blank]))
        seen=set();by_tx[tid]=[]
        base=dataset['static'][tid];basekeys={(r[1],r[2],r[4]) for r in base if r[1]}
        cash=abs(cents(t['amount']))
        for h in options:
            key=tuple(sorted(tuple(row) for row in h['rows']))
            if key in seen:continue
            seen.add(key);js=h['pair_ids'];ps=[prob[j] for j in js]
            amounts=[cents(r[2]) for r in h['rows'] if r[1]]
            net=sum((-1 if r[1].startswith(('ARC','APC')) else 1)*cents(r[2]) for r in h['rows'] if r[1])
            x=[math.log1p(len(js)),math.log1p(cash),math.log1p(sum(amounts)),
               abs(cash-net)/max(cash,abs(net),1),net/max(cash,1),min(ps,default=0),max(ps,default=0),
               np.mean(ps) if ps else 0,sum(ps),expected[tid],len(js)/max(len(best),1),
               sum((r[1],r[2],r[4]) in basekeys for r in h['rows'])/max(len(js),1),
               len(basekeys),len(ids),t['statement_format']=='n43',t['statement_format']=='mt940',
               t['statement_format']=='camt053',cents(t['amount'])<0,
               base[0][3]=='UNIDENTIFIED',len(t.get('counterparty_name','')),
               math.log1p(abs(cents(t.get('orig_amount') or 0))),bool(t.get('orig_currency'))]
            x.extend(sum(r[4]==exc for r in h['rows'])/max(len(h['rows']),1) for exc in EXCEPTIONS)
            x.extend(h['kind']==kind for kind in KINDS)
            x.extend(h['rows'][0][3]==category for category in ['UNIDENTIFIED','BANK_FEES','CASH_POOL','OTHER'])
            if js:
                x.extend(np.mean(dataset['X'][js,:38],axis=0).tolist())
            else:x.extend([0]*38)
            number=len(hyps);by_tx[tid].append(number)
            h=dict(h,tid=tid,estimated_pair_f1=2*sum(ps)/max(len(js)+expected[tid],1))
            hyps.append(h);features.append(x)
    return hyps,np.asarray(features,dtype=np.float32),by_tx


def official(dataset):
    spec=importlib.util.spec_from_file_location('v4_official',dataset['docs']/'starter/bankrec_score.py')
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    cats=[r['category'] for r in rows(table(dataset['docs']/'masters','categories'))]
    g=module.load_golden(str(table(dataset['phase'],'golden_allocations')),str(table(dataset['phase'],'bank_transactions')),EXCEPTIONS[1:],cats)
    return module,g


def score(module,golden,predictions):
    subset=module.Golden();subset.exceptions=golden.exceptions;subset.categories=golden.categories
    subset.txns={tid:golden.txns[tid] for tid in predictions};subset.weight={tid:golden.weight[tid] for tid in predictions}
    subset.n_pairs=sum(len(v[0]) for v in subset.txns.values())
    text=io.StringIO();w=csv.writer(text,lineterminator='\n');w.writerow(FIELDS)
    for tid in sorted(predictions):w.writerows(sorted(predictions[tid],key=lambda r:tuple(r[1:])))
    return module.score_submission(subset,text.getvalue().encode(),'submission.csv')


def select(hyps,by_tx,full_prob,tids,alpha,bonus):
    selected={};chosen={}
    for tid in tids:
        def utility(j):
            h=hyps[j]
            return alpha*full_prob[j]+(1-alpha)*h['estimated_pair_f1']+bonus*(h['kind']=='static')
        j=max(by_tx[tid],key=lambda j:(utility(j),-j))
        selected[tid]=hyps[j]['rows'];chosen[tid]=hyps[j]['kind']
    return selected,chosen


def main():
    start=time.monotonic();WORK.mkdir(exist_ok=True);RESULTS.mkdir(exist_ok=True)
    path=WORK/'candidates.joblib'
    if path.exists():dataset=joblib.load(path)
    else:
        dataset=prepare(WORK);joblib.dump(dataset,path,compress=3)
    gold,noitem,segments,y=load_labels(dataset)
    folds,group_counts=partition(dataset,gold)
    write_json(RESULTS/'split_manifest.json',dict(folds=folds,groups=len(group_counts),largest_group=max(group_counts.values()),
        rule='Repeated golden item keys define episodes, used only for partitioning, never features.',
        roles='For test fold k: calibration k+1, hypothesis fit k+2, allocation fit k+3 and k+4 (mod 5).'))
    write_json(RESULTS/'features.json',dict(allocation_features=dataset['feature_names'],
        hypothesis_features=HYPOTHESIS_FEATURES+['mean_'+f for f in dataset['feature_names'][:38]]))
    module,golden=official(dataset)
    pair_folds=np.array([folds[r[0]] for r in dataset['pair_rows']]);all_predictions={};all_methods={};reports=[];revision_queue=[]
    coverage=set((r[0],r[1]) for r,label in zip(dataset['pair_rows'],y) if label)
    goldkeys={(tid,i) for tid,gi in gold.items() for i in gi}
    print(f'Candidates: {len(y):,}; covered gold pairs {len(coverage):,}/{len(goldkeys):,}; groups {len(group_counts):,}',flush=True)
    for fold in range(5):
        pair_roles={(fold+3)%5,(fold+4)%5};hyp_role=(fold+2)%5;cal_role=(fold+1)%5
        fit=np.isin(pair_folds,list(pair_roles))
        print(f'Fold {fold}: allocation fit {fit.sum():,} rows',flush=True)
        with threadpool_limits(limits=4):
            pair_model=fit_model(dataset['X'][fit],y[fit]);pp=predict(pair_model,dataset['X'])
        hyps,H,by_tx=hypotheses(dataset,pp)
        assert H.shape[1]==len(HYPOTHESIS_FEATURES)+38
        hy=np.array([complete(h['rows'],gold,noitem) for h in hyps],dtype=np.int8)
        hf=np.array([folds[h['tid']] for h in hyps]);hfit=hf==hyp_role
        print(f'Fold {fold}: hypothesis fit {hfit.sum():,}, positives {hy[hfit].sum():,}',flush=True)
        with threadpool_limits(limits=4):
            hypothesis_model=fit_model(H[hfit],hy[hfit]);hp=predict(hypothesis_model,H)
        cal_tids=[tid for tid in folds if folds[tid]==cal_role];test_tids=[tid for tid in folds if folds[tid]==fold]
        best=None
        # All calibration cases participate, including genuinely unidentified transactions.
        for alpha in (.25,.5,.75,1.0):
            for bonus in (0,.1,.2):
                prediction,_=select(hyps,by_tx,hp,cal_tids,alpha,bonus)
                result=score(module,golden,prediction)
                key=(result['score'],bonus,alpha)
                if best is None or key>best[0]:best=(key,alpha,bonus,result)
        _,alpha,bonus,cal_score=best
        pred,methods=select(hyps,by_tx,hp,test_tids,alpha,bonus)
        for tid in test_tids:
            ranked=sorted(by_tx[tid],key=lambda j:-(alpha*hp[j]+(1-alpha)*hyps[j]['estimated_pair_f1']+bonus*(hyps[j]['kind']=='static')))
            options=[dict(id=j,kind=hyps[j]['kind'],rows=hyps[j]['rows'],full_probability=float(hp[j]),
                utility=float(alpha*hp[j]+(1-alpha)*hyps[j]['estimated_pair_f1']+bonus*(hyps[j]['kind']=='static'))) for j in ranked[:3]]
            packet=ambiguity_packet(tid,dataset['banks'][tid],options,ranked[0],dataset['static'][tid],fold)
            if packet:revision_queue.append(packet)
        result=score(module,golden,pred);base=score(module,golden,{tid:dataset['static'][tid] for tid in test_tids})
        test_pair=pair_folds==fold
        report=dict(fold=fold,alpha=alpha,static_bonus=bonus,calibration_score=cal_score['score'],
            held_out_score=result['score'],baseline_score=base['score'],transactions=len(test_tids),
            metrics=result['metrics'],method_counts=dict(Counter(methods.values())),
            pair_average_precision=float(average_precision_score(y[test_pair],pp[test_pair])),
            pair_roc_auc=float(roc_auc_score(y[test_pair],pp[test_pair])) if len(np.unique(y[test_pair]))==2 else None,
            complete_hypothesis_coverage=sum(any(hy[j] for j in by_tx[tid]) for tid in test_tids)/len(test_tids))
        assert not (all_predictions.keys() & pred.keys()),'A transaction was predicted in more than one test fold'
        reports.append(report);all_predictions.update(pred);all_methods.update(methods)
        modeldir=WORK/'models';modeldir.mkdir(exist_ok=True)
        joblib.dump(dict(pair=pair_model,hypothesis=hypothesis_model,alpha=alpha,static_bonus=bonus),modeldir/f'fold_{fold}.joblib',compress=3)
        write_json(RESULTS/f'fold_{fold}.json',report)
        print(f'Fold {fold}: held-out {result["score"]}, static {base["score"]}; calibration {cal_score["score"]}',flush=True)
    assert set(all_predictions)==set(dataset['banks'])
    final=score(module,golden,all_predictions);base=score(module,golden,dataset['static'])
    output=WORK/'submission_v4_sample_oof.csv'
    with output.open('w',encoding='utf-8',newline='') as f:
        w=csv.writer(f,lineterminator='\n');w.writerow(FIELDS)
        for tid in sorted(all_predictions):w.writerows(sorted(all_predictions[tid],key=lambda r:tuple(r[1:])))
    # Strict contract validation remains separate from the competition's soft ledger audit.
    import sqlite3
    from bankrec.catalog import Catalog
    from bankrec.validate import validate
    catalog=object.__new__(Catalog)
    catalog.db=sqlite3.connect(f'file:{WORK / "candidates.sqlite"}?mode=ro',uri=True)
    catalog.db.row_factory=sqlite3.Row;catalog.categories=set(golden.categories)
    validation=validate(output,dataset['banks'],catalog);catalog.db.close()
    aggregate=[e for e in validation['errors'] if e['message']=='aggregate allocation exceeds remaining balance']
    validation['errors']=[e for e in validation['errors'] if e not in aggregate]
    validation['warnings'].extend(aggregate);validation['ok']=not validation['errors']
    validation['scope']='Sample model experiment, not a LIVE upload; cross-bank balance checks are diagnostic.'
    write_json(RESULTS/'validation.json',validation)
    if not validation['ok']:raise ValueError('Model output failed local contract validation')
    write_json(RESULTS/'score.json',final);write_json(RESULTS/'baseline_score.json',base)
    queue=sorted(revision_queue,key=lambda p:(-p['priority'],p['bank_txn_id']))[:200]
    # Attach only raw item metadata and source facts, never target labels.
    connection=sqlite3.connect(f'file:{WORK / "candidates.sqlite"}?mode=ro',uri=True);connection.row_factory=sqlite3.Row
    for packet in queue:
        items={r[1] for candidate in packet['candidates'] for r in candidate['rows'] if r[1]}
        packet['item_evidence']=[dict(connection.execute('SELECT iid,entity,party,name,doc,issue,due,currency,total,initial,facts FROM items WHERE iid=?',(iid,)).fetchone()) for iid in sorted(items)]
    connection.close()
    with (WORK/'tier3_review_queue.jsonl').open('w',encoding='utf-8') as f:
        for packet in queue:f.write(json.dumps(packet,ensure_ascii=False)+'\n')
    summary=dict(score=final['score'],baseline_score=base['score'],delta=round(final['score']-base['score'],2),
        metrics=final['metrics'],folds=reports,candidate_pairs=len(y),candidate_gold_pair_recall=len(coverage)/len(goldkeys),
        transactions=len(all_predictions),method_counts=dict(Counter(all_methods.values())),
        split='Pooled held-out predictions; pair fit, hypothesis fit, calibration and test episodes are disjoint in each fold.',
        elapsed_seconds=round(time.monotonic()-start,3),submission_sha256=digest(output),
        caveat='Inspected starter development experiment; not a future-period holdout. No TRAIN/LIVE input read.',
        sklearn_version=__import__('sklearn').__version__,source_sha256={p.name:digest(p) for p in Path(__file__).parent.glob('*.py')},
        candidate_manifest=json.loads((WORK/'candidate_manifest.json').read_text()),
        changes=dict(newly_correct=sum(complete(all_predictions[t],gold,noitem) and not complete(dataset['static'][t],gold,noitem) for t in all_predictions),
                     regressed=sum(complete(dataset['static'][t],gold,noitem) and not complete(all_predictions[t],gold,noitem) for t in all_predictions)),
        model_hashes={p.name:digest(p) for p in (WORK/'models').glob('*.joblib')})
    summary['tier3']=dict(allowed=True,eligible=len(revision_queue),exported=len(queue),provider_calls=0,
        path='work/version-4/tier3_review_queue.jsonl',note='Score above is static + ML only; no LLM revisions are included.')
    write_json(RESULTS/'summary.json',summary)
    print(json.dumps({k:summary[k] for k in ['score','baseline_score','delta','metrics','candidate_gold_pair_recall','elapsed_seconds']},indent=2),flush=True)


if __name__=='__main__':main()
