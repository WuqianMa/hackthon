#!/usr/bin/env python3
"""Unseen-phase runner: frozen V3 -> V4 ML -> V5 policy -> V6 recovery.

No TRAIN import, fitting, labeled evaluation, new database migration, or LLM API.
Only the phase's operational SQLite catalog is built. Outputs are checkpointed.
"""
from collections import defaultdict,Counter
from concurrent.futures import ProcessPoolExecutor
import argparse,csv,gc,hashlib,importlib.util,json,os,shutil,sqlite3,sys,time
from pathlib import Path

ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT));sys.path.insert(0,str(ROOT/'version-5'));sys.path.insert(0,str(ROOT/'version-4'))
import joblib
from data import load_strategy
from train_live import initialize_live_worker,predict_live_batch,amount_contract_guard,dump_rows
from bankrec.io import FIELDS,EXCEPTIONS,cents,digest,extract,find_folder,rows,table,write_json,is_data_file
from bankrec.cli import merged_masters,reversal_pairs,DATES
from policy import propose as policy_propose,source_supported
from recovery import propose as recovery_propose,pool_category

def module(name,path):
    spec=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m

v5=module('final_v5_runtime',ROOT/'version-5/run.py')
v6=module('final_v6_mechanisms',ROOT/'version-6/mechanisms.py')
MODEL=ROOT/'version-4/models/train_001.joblib'
MODEL_SHA='a883a203fc5bc694812895a14cbd8b125870f435a67bc5e7627ab42e4526eccb'
CACHE=ROOT/'work/cache/pdf_text'


def verify_sources():
    record=json.loads((ROOT/'VENDORED_SOURCES.json').read_text())
    for relative,expected in record['files'].items():
        if digest(ROOT/relative)!=expected:raise ValueError('Frozen source/resource changed: '+relative)


def atomic_joblib(value,path):
    tmp=path.with_suffix(path.suffix+'.tmp');joblib.dump(value,tmp,compress=3);os.replace(tmp,path)


def phase_masters(base,phase,target):
    """Retain old rows; FINAL rows override by official keys, allowing extra columns."""
    overlay=phase/'masters_final'
    if not overlay.is_dir():return base
    target.mkdir(exist_ok=True)
    for kind,keys in {'entities':['entity'],'bank_accounts':['account_id'],'customers':['customer_id'],'suppliers':['supplier_id'],'categories':['category'],'payment_terms':['code'],'fx_rates':['date','currency']}.items():
        records={};fields=[]
        for directory in (base,overlay):
            path=table(directory,kind,required=False)
            if not path:continue
            for row in rows(path):
                for field in row:
                    if field not in fields:fields.append(field)
                key=tuple(row[k] for k in keys);records[key]=dict(records.get(key,{}),**row)
        if not records:raise ValueError('Missing master '+kind)
        with (target/(kind+'.csv')).open('w',encoding='utf-8',newline='') as f:
            writer=csv.DictWriter(f,fieldnames=fields,lineterminator='\n');writer.writeheader();writer.writerows(records[k] for k in sorted(records))
    return target


def prefetch_pdf(task):
    """Native extraction only; atomic content-addressed writes, no OCR."""
    source,cache=map(Path,task);key=digest(source);target=cache/(key+'.txt')
    if target.exists():return 'cached'
    from pypdf import PdfReader
    text='\n'.join(page.extract_text() or '' for page in PdfReader(source).pages)
    tmp=target.with_name(target.name+'.'+str(os.getpid())+'.tmp');tmp.write_text(text,encoding='utf-8');os.replace(tmp,target)
    return 'extracted'


def warm_pdfs(phase,workers):
    files=[]
    for folder in ('pdfs','remittance_advices'):
        index=phase/folder/'index.csv'
        if index.exists():
            files.extend(phase/folder/r['file'] for r in rows(index) if r['file'].lower().endswith('.pdf'))
    counts=Counter();CACHE.mkdir(parents=True,exist_ok=True)
    with ProcessPoolExecutor(max_workers=workers) as pool:
        for n,result in enumerate(pool.map(prefetch_pdf,[(str(p),str(CACHE)) for p in files],chunksize=25),1):
            counts[result]+=1
            if n%2000==0:print(f'PDF cache {n:,}/{len(files):,}',flush=True)
    return dict(counts)


def open_catalog(folder):
    cm,_,_=load_strategy();c=object.__new__(cm.Catalog);c.__dict__.update(joblib.load(folder/'catalog_state.joblib'))
    c.db=sqlite3.connect(f'file:{folder / "catalog.sqlite"}?mode=ro',uri=True);c.db.row_factory=sqlite3.Row
    c.db.execute('PRAGMA cache_size=-131072');c.db.execute('PRAGMA mmap_size=1073741824')
    return c


def prepare_catalog(folder,phase,masters,workers):
    cm,sm,em=load_strategy()
    if (folder/'catalog_state.joblib').exists() and (folder/'sources.joblib').exists():return open_catalog(folder)
    print('Preparing native PDF cache...',flush=True);pdfs=warm_pdfs(phase,workers)
    if not (folder/'catalog_state.joblib').exists():
        # More page cache avoids tiny-cache random-index thrashing. This is the
        # existing operational catalog, not the stopped historical VV1 import.
        connect=sqlite3.connect
        def cached_connect(*args,**kwargs):
            db=connect(*args,**kwargs);db.execute('PRAGMA cache_size=-524288');db.execute('PRAGMA synchronous=NORMAL');db.execute('PRAGMA temp_store=MEMORY');return db
        dbpath=folder/'catalog.sqlite'
        for suffix in ('','-wal','-shm'):Path(str(dbpath)+suffix).unlink(missing_ok=True)
        print('Building phase items/opening balances and PDF clauses...',flush=True)
        sqlite3.connect=cached_connect
        try:c=cm.Catalog(dbpath,phase,masters,CACHE,True)
        finally:sqlite3.connect=connect
        c.bank_accounts={r['account_id']:r for r in rows(table(masters,'bank_accounts'))}
        atomic_joblib({k:v for k,v in c.__dict__.items() if k!='db'},folder/'catalog_state.joblib');c.db.commit()
    else:c=open_catalog(folder)
    print('Parsing phase payment sources...',flush=True)
    if not (folder/'sources.joblib').exists():
        sources=sm.Sources(phase,CACHE);atomic_joblib(sources,folder/'sources.joblib')
        write_json(folder/'source_inventory.json',dict(groups=dict(sources.counts),issues=sources.issues,pdfs=pdfs));del sources
    return c


def static_pass(folder,c,banks):
    path=folder/'static.csv';methodpath=folder/'static_methods.json'
    if path.exists() and methodpath.exists():return v5.read_predictions(path),json.loads(methodpath.read_text())
    # Reopen writable only for the original V3 ledger; restore opening balances
    # before independent ML candidate generation, as in the frozen LIVE recipe.
    c.db.close();c.db=sqlite3.connect(folder/'catalog.sqlite');c.db.row_factory=sqlite3.Row
    c.db.execute('PRAGMA cache_size=-262144');c.db.execute('UPDATE items SET balance=initial');c.db.commit()
    _,_,em=load_strategy();sources=joblib.load(folder/'sources.joblib');engine=em.Engine(c,sources);engine.speculative=True
    reverse=reversal_pairs(banks);pred={};methods={}
    print('V3 static reconciliation...',flush=True)
    for n,tid in enumerate(sorted(banks,key=lambda t:(banks[t]['booking_date'],t)),1):
        pred[tid],evidence=engine.reconcile(banks[tid],reverse);methods[tid]=evidence['method']
        if n%10000==0:print(f'Static {n:,}/{len(banks):,}',flush=True);c.db.commit()
    c.db.execute('UPDATE items SET balance=initial');c.db.commit()
    dump_rows(path,pred,banks);write_json(methodpath,methods);del engine,sources
    return pred,methods


def model_pass(folder,c,phase,docs,banks,static,workers,budget_minutes):
    order=sorted(banks,key=lambda t:(banks[t]['booking_date'],t));out={};methods=Counter();failures=[];start=time.monotonic()
    (folder/'predictions').mkdir(exist_ok=True)
    # Free large raw metadata maps before starting independent worker processes.
    connection=c.db;categories=c.categories;c.__dict__.clear();c.db=connection;c.categories=categories;gc.collect()
    print('Frozen V4 model inference...',flush=True)
    with ProcessPoolExecutor(max_workers=workers,initializer=initialize_live_worker,initargs=(folder,phase,docs,MODEL)) as pool:
        for wave in range(0,len(order),1000*workers):
            if budget_minutes and time.monotonic()-start>budget_minutes*60:
                print('ML time budget reached; remaining bank lines retain V3 decisions.',flush=True);break
            jobs=[]
            for begin in range(wave,min(wave+1000*workers,len(order)),1000):
                tids=order[begin:begin+1000];cache=folder/'predictions'/f'{begin:06d}.joblib'
                if cache.exists():jobs.append((tids,None,joblib.load(cache)))
                else:jobs.append((tids,pool.submit(predict_live_batch,(begin,{t:banks[t] for t in tids},{t:static[t] for t in tids})),None))
            for tids,future,cached in jobs:
                try:prediction,method=future.result() if future else cached
                except Exception as ex:
                    failures.append(dict(bank_lines=len(tids),first_bank_id=tids[0],reason=str(ex)));print('ML batch retained static decisions:',tids[0],str(ex),flush=True);continue
                out.update(prediction);methods.update(method.values())
                print(f'ML {len(out):,}/{len(banks):,}',flush=True)
    modeled=len(out)
    for tid in order:
        if tid not in out:out[tid]=static[tid]
    repairs=amount_contract_guard(out,static,c)
    return out,dict(modeled_bank_lines=modeled,methods=dict(methods),failed_batches=failures,amount_fallbacks=len(repairs),seconds=round(time.monotonic()-start,2))


def recovery_pass(folder,banks,current,static,methods):
    c=open_catalog(folder);ledger=v5.Ledger(c,banks);intermediate={};counts=Counter();keys=[]
    from bankrec.engine import text_of
    from bankrec.io import plain
    for tid,t in banks.items():
        txt=plain(text_of(t));marker=any(w in txt for w in ('MANT','SERVIC','RETEN','PLAZO','INSTAL','RETURN','DEVOL','CASH','TRASPASO','ZBA'))
        if marker or current[tid][0][3]=='UNIDENTIFIED' or 'credit' in methods[tid]:keys.append((-int(marker),hashlib.sha256(tid.encode()).hexdigest(),tid))
    recover={x[-1] for x in sorted(keys)[:6000]}
    print('V5 policy and recovery...',flush=True)
    for tid in sorted(banks,key=lambda t:(banks[t]['booking_date'],t)):
        t=banks[tid];ledger.current_date=t['booking_date'];out=current[tid];reason='v4_incumbent'
        proposal=policy_propose(t,out,static[tid],c,ledger,methods[tid])
        if proposal:out,reason=proposal
        if out[0][3] in ('','UNIDENTIFIED','INTERNAL_TRANSFER','CASH_POOL'):
            proposal=pool_category(t,c,ledger)
            if proposal:out,reason=proposal
        if tid in recover:
            proposal=recovery_propose(t,out,static[tid],c,ledger,None)
            if proposal:out,reason=proposal
        intermediate[tid]=out;counts[reason]+=1
        ledger.advance(t,out,reason!='v4_incumbent' or (v5.same(out,static[tid]) and source_supported(methods[tid])))
    amount_contract_guard(intermediate,static,c)
    print('V6 source, month, credit and document recovery...',flush=True)
    view=v6.CatalogView(c,banks);sources=v6.SourceIndex(view,banks);ledger=v5.Ledger(view,banks);pred={};changed=Counter()
    for n,tid in enumerate(sorted(banks,key=lambda t:(banks[t]['booking_date'],t)),1):
        t=banks[tid];ledger.current_date=t['booking_date'];out=intermediate[tid]
        proposal=v6.propose(t,out,view,ledger,sources)
        if proposal and not v5.same(out,proposal[0]):out,reason=proposal;changed[reason]+=1
        pred[tid]=out;ledger.advance(t,out,True)
        if n%25000==0:print(f'V6 {n:,}/{len(banks):,}',flush=True)
    repairs=amount_contract_guard(pred,static,c)
    report=dict(v5_methods=dict(counts),v6_changes=dict(changed),pdf_facts=dict(view.stats),return_sources=dict(sources.stats),final_amount_fallbacks=len(repairs),llm_calls=0)
    return pred,c,report


def write_submission(path,pred,banks,c):
    """Single-pass upload checks, not an evaluation/validation experiment."""
    if set(pred)!=set(banks):raise ValueError('Bank coverage mismatch')
    path.parent.mkdir(parents=True,exist_ok=True);tmp=path.with_suffix('.csv.tmp');count=0;total_cache={}
    with tmp.open('w',encoding='utf-8',newline='') as f:
        writer=csv.writer(f,lineterminator='\n');writer.writerow(FIELDS)
        for tid in sorted(banks,key=lambda x:(banks[x]['booking_date'],x)):
            rs=pred[tid];seen=set()
            if not rs:raise ValueError('Empty bank allocation')
            for row in sorted(rs,key=lambda r:tuple(r[1:])):
                t,i,a,cat,exc=row
                if t!=tid or i in seen or exc not in EXCEPTIONS|{''}:raise ValueError('Invalid/duplicate row')
                seen.add(i)
                if i:
                    if cat or not a or cents(a)<0:raise ValueError('Invalid item row')
                    if i not in total_cache:
                        item=c.item(i)
                        if not item:raise ValueError('Unknown item '+i)
                        total_cache[i]=(item['total'],item['issue'])
                    total,issued=total_cache[i]
                    if issued>banks[tid]['booking_date'] or (cents(a)>total and exc!='DUPLICATE_PAYMENT'):raise ValueError('Invalid item amount/date')
                elif len(rs)!=1 or a or cat not in c.categories:raise ValueError('Invalid no-item category row')
                writer.writerow(row);count+=1
    if count>3000000 or tmp.stat().st_size>60000000:raise ValueError('Submission size/row limit exceeded')
    os.replace(tmp,path);return dict(bank_lines=len(banks),rows=count,bytes=path.stat().st_size,missing_bank_lines=0,sha256=digest(path),checks='Single-pass schema, IDs, dates, amounts, duplicates, coverage and limits; no labeled scoring')


def main():
    p=argparse.ArgumentParser(description=__doc__)
    source=p.add_mutually_exclusive_group();source.add_argument('--archive',type=Path);source.add_argument('--phase-dir',type=Path)
    p.add_argument('--phase',choices=['final','live'],default='final');p.add_argument('--expected-sha256')
    p.add_argument('--workers',type=int,default=3,choices=range(1,5));p.add_argument('--ml-budget-minutes',type=float,default=0)
    p.add_argument('--pdf-cache',type=Path,help='Optional existing content-hash text cache to reuse')
    p.add_argument('--output',type=Path);p.add_argument('--check-environment',action='store_true')
    a=p.parse_args()
    verify_sources()
    if digest(MODEL)!=MODEL_SHA:raise ValueError('Frozen trained model checksum mismatch')
    if a.check_environment:
        import sklearn,numpy,pypdf
        m=joblib.load(MODEL)
        print(json.dumps(dict(ok=True,python=sys.version,sklearn=sklearn.__version__,numpy=numpy.__version__,pypdf=pypdf.__version__,model_sha256=MODEL_SHA,models=list(k for k in ('pair','hypothesis') if k in m)),indent=2));return
    if not a.archive and not a.phase_dir:p.error('Provide --archive or --phase-dir when the dataset arrives')
    start=time.monotonic();work=ROOT/'work';work.mkdir(exist_ok=True)
    shared=a.pdf_cache or ROOT.parent/'work/cache/pdf_text'
    if shared.is_dir() and shared.resolve()!=CACHE.resolve() and not CACHE.exists():
        CACHE.parent.mkdir(parents=True,exist_ok=True);CACHE.symlink_to(shared.resolve(),target_is_directory=True)
    if a.archive:
        archive_sha=digest(a.archive)
        if a.expected_sha256 and archive_sha!=a.expected_sha256:raise ValueError('Official archive SHA-256 mismatch')
        extracted,_=extract(a.archive,work/'archives'/archive_sha[:16],a.expected_sha256 or archive_sha)
        try:raw=find_folder(extracted,a.phase)
        except ValueError:
            candidates=[p.parent for p in extracted.rglob('bank_transactions.csv*') if is_data_file(p)]
            if len(candidates)!=1:raise ValueError('Cannot identify a unique phase input folder')
            raw=candidates[0]
    else:raw=a.phase_dir.resolve();archive_sha=None
    inputs={name:digest(table(raw,name)) for name in ('bank_transactions','ar_invoices','ap_invoices','credit_notes','open_items_at_start')}
    overlay=raw/'masters_final'
    if overlay.exists():inputs['masters_final']={f.name:digest(f) for f in sorted(overlay.glob('*')) if is_data_file(f)}
    identity=dict(phase=a.phase,archive_sha256=archive_sha,input_hashes=inputs,model_sha256=MODEL_SHA,vendored_sha256=digest(ROOT/'VENDORED_SOURCES.json'))
    run_id=hashlib.sha256(json.dumps(identity,sort_keys=True).encode()).hexdigest()[:16];folder=work/'runs'/f'{a.phase}_{run_id}';folder.mkdir(parents=True,exist_ok=True)
    link=folder/a.phase
    if not link.exists():link.symlink_to(raw,target_is_directory=True)
    phase=link;masters=phase_masters(ROOT/'resources/masters',phase,folder/'masters')
    write_json(folder/'identity.json',identity);write_json(folder/'run_status.json',dict(status='running',phase=a.phase))
    banks={};lo,hi=DATES[a.phase]
    for t in rows(table(phase,'bank_transactions')):
        if t['bank_txn_id'] in banks or not lo<=t['booking_date']<=hi:raise ValueError('Duplicate/cross-phase bank input')
        banks[t['bank_txn_id']]=t
    if not banks:raise ValueError('Empty bank input')
    print(f'{a.phase.upper()}: {len(banks):,} bank lines; work {folder}',flush=True)
    c=prepare_catalog(folder,phase,masters,a.workers);static,methods=static_pass(folder,c,banks)
    current,ml=model_pass(folder,c,phase,ROOT/'resources',banks,static,a.workers,a.ml_budget_minutes);c.db.close()
    pred,c,recovery=recovery_pass(folder,banks,current,static,methods)
    output=a.output or ROOT/'output'/f'{a.phase}-submission.csv';result=write_submission(output,pred,banks,c);c.db.close()
    root_copy=ROOT.parent/f'{a.phase}-submission.csv'
    if output.resolve()!=root_copy.resolve():shutil.copyfile(output,root_copy)
    record=dict(identity,**result,output=str(output.resolve()),root_copy=str(root_copy),seconds=round(time.monotonic()-start,2),ml=ml,recovery=recovery,runner_sha256=digest(Path(__file__)),new_training=False,labeled_evaluation=False,website_score=None)
    write_json(folder/'manifest.json',record);write_json(output.with_suffix('.json'),record)
    write_json(folder/'run_status.json',dict(status='complete',phase=a.phase,sha256=result['sha256']))
    print('UPLOAD FILE:',output.resolve(),flush=True);print('ROOT COPY:',root_copy,flush=True);print(json.dumps({k:result[k] for k in ('bank_lines','rows','missing_bank_lines','sha256')},indent=2),flush=True)


if __name__=='__main__':main()
