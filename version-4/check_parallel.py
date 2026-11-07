"""Integration check: starter serial decisions equal two independent workers."""
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
import joblib
from data import ROOT,load_strategy,generate
from train_live import infer,initialize_live_worker,predict_live_batch
from bankrec.io import write_json


def main():
    work=ROOT/'work/version-4-parallel-check';work.mkdir(exist_ok=True)
    (work/'predictions').mkdir(exist_ok=True)
    docs=ROOT/'work/archives/docs';phase=docs/'sample'
    cm,sm,_=load_strategy();db=work/'catalog.sqlite'
    for suffix in ('','-wal','-shm'):Path(str(db)+suffix).unlink(missing_ok=True)
    c=cm.Catalog(db,phase,docs/'masters',ROOT/'work/cache/pdf_text',True)
    joblib.dump({k:v for k,v in c.__dict__.items() if k!='db'},work/'catalog_state.joblib',compress=3)
    sources=sm.Sources(phase,ROOT/'work/cache/pdf_text');joblib.dump(sources,work/'sources.joblib',compress=3)
    original=joblib.load(ROOT/'work/version-4/candidates.joblib')
    model=joblib.load(ROOT/'work/version-4/models/fold_0.joblib');model['features']=original['feature_names']
    joblib.dump(model,work/'model.joblib',compress=3)
    tids=list(original['banks'])[:1000];banks={t:original['banks'][t] for t in tids};static={t:original['static'][t] for t in tids}
    expected=infer(generate(c,sources,banks,static,phase,docs),model)
    actual={};methods={}
    with ProcessPoolExecutor(max_workers=2,initializer=initialize_live_worker,initargs=(work,phase,docs,work/'model.joblib')) as pool:
        futures=[]
        for start in (0,500):
            subset=tids[start:start+500]
            futures.append(pool.submit(predict_live_batch,(start,{t:banks[t] for t in subset},{t:static[t] for t in subset})))
        for future in futures:
            a,b=future.result();actual.update(a);methods.update(b)
    assert (actual,methods)==expected,'Independent worker results differ from serial inference'
    c.db.close()
    report=dict(ok=True,transactions=1000,workers=2,comparison='Exact allocation-row and method equality against serial inference on starter')
    write_json(ROOT/'version-4/training-results/parallel_adapter_validation.json',report)
    print(report,flush=True)


if __name__=='__main__':main()
