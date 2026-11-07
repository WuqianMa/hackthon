"""Label-free candidate generation from the starter archive and frozen static output."""
from collections import defaultdict
from datetime import date
from difflib import SequenceMatcher
import importlib.util
import json
import math
from pathlib import Path
import re
import subprocess
import sys

ROOT=Path(__file__).resolve().parent.parent
sys.path.insert(0,str(ROOT))
from bankrec.io import rows,table,norm,plain,cents,money,extract,HASHES,digest,write_json
from bankrec.engine import text_of,is_return
from bankrec.catalog import tokens

FEATURES=['log_cash','log_amount','log_total','amount_total_ratio','cash_amount_ratio','relative_cash_gap',
 'allocated_fraction','invoice_age','due_gap','currency_match','original_currency_match','negative_cash',
 'printed_ref_full','printed_ref_suffix','reference_prefix_fraction','party_name_similarity',
 'known_party','discount_eligible','plan','retention','advance','return_marker','partial_marker','final_marker',
 'dispute_marker','unknown_payer_short','baseline_pair','kind_static','kind_full','kind_cash','kind_tranche',
 'format_n43','format_mt940','format_camt','side_ar','credit','pool_size_log','discount_pct']
EXCEPTIONS=['','PARTIAL','OVERPAYMENT','SHORT_DISCOUNT','SHORT_BANK_CHARGES','SHORT_WITHHOLDING',
 'SHORT_DISPUTE','DUPLICATE_PAYMENT','UNIDENTIFIED','RETURNED','FX_DIFFERENCE']


def load_strategy():
    folder=ROOT/'version-3'
    spec=importlib.util.spec_from_file_location('v4_static',folder/'__init__.py',submodule_search_locations=[str(folder)])
    package=importlib.util.module_from_spec(spec);sys.modules['v4_static']=package;spec.loader.exec_module(package)
    from importlib import import_module
    return tuple(import_module('v4_static.'+n) for n in ('catalog','sources','engine'))


def prepare(work):
    import numpy as np
    work=Path(work);work.mkdir(parents=True,exist_ok=True)
    docs,_=extract(ROOT/'bankrec-docs-and-masters.zip',work/'archives/docs',HASHES['docs'])
    phase=docs/'sample';masters=docs/'masters'
    baseline=ROOT/'work/version-3/artifacts/sample/submission.csv'
    if not baseline.exists():
        subprocess.run([sys.executable,str(ROOT/'version-3/run.py'),'--phase','sample'],check=True,cwd=ROOT)
    static=defaultdict(list)
    for r in rows(baseline):static[r['bank_txn_id']].append([r[k] for k in ['bank_txn_id','item_id','amount','category','exception']])
    banks={r['bank_txn_id']:r for r in rows(table(phase,'bank_transactions'))}
    cm,sm,em=load_strategy()
    db=work/'candidates.sqlite'
    for suffix in ('','-wal','-shm'):Path(str(db)+suffix).unlink(missing_ok=True)
    c=cm.Catalog(db,phase,masters,ROOT/'work/cache/pdf_text',True)
    sources=sm.Sources(phase,ROOT/'work/cache/pdf_text')
    engine=em.Engine(c,sources)
    result=generate(c,sources,banks,static,phase,docs)
    c.db.close()
    write_json(work/'candidate_manifest.json',dict(input_archive_sha256=HASHES['docs'],baseline_sha256=digest(baseline),
        bank_lines=len(banks),pairs=len(result['pair_rows']),features=result['feature_names'],labels_read=False,
        candidate_code_sha256=digest(Path(__file__))))
    return result


def generate(c,sources,banks,static,phase,docs):
    """Reusable bounded-batch generator; takes no labels and performs no model/provider calls."""
    import numpy as np
    _,_,em=load_strategy()
    engine=em.Engine(c,sources)
    pair_rows=[];pair_x=[];per_tx={};baseline_pairs={};base_hyps={};item_parties={}
    for index,(tid,t) in enumerate(banks.items(),1):
        if hasattr(c,'as_of'):c.as_of=t['booking_date']
        tx=text_of(t);nt=norm(tx);tt=plain(tx);ts=tokens(tx);cash=abs(cents(t['amount']))
        side='AR' if cents(t['amount'])>0 else 'AP'
        if is_return(t):side='AP' if side=='AR' else 'AR'
        parties=c.identify(t.get('counterparty_name',''),entity=t['entity'],side=side,iban=t.get('counterparty_account',''))
        if not parties:parties=c.identify(tx,entity=t['entity'],side=side,iban=t.get('counterparty_account',''))
        if is_return(t):
            for mandate in re.findall(r'VTM[- ]?[A-Z]{2}[- ]?\d+',tt):parties.update(c.mandates.get(norm(mandate),()))
        pool=c.by_party(parties,t['booking_date'])
        pool=[i for i in pool if not json.loads(i['facts']).get('cancelled')]
        candidates={i['iid']:i for i in pool}
        for row in static[tid]:
            if row[1]:candidates[row[1]]=c.item(row[1])
        for token in ts:
            for i in c.lookup(token,entity=t['entity'],booking=t['booking_date']):
                if i['side']==side:candidates[i['iid']]=i
        # Capacity controls are independent of labels; keep source-supported baseline rows.
        def retrieval(i):
            doc=norm(i['doc']);ref=doc in nt or any(len(k)>=5 and doc.endswith(k) for k in ts)
            ratio=abs(math.log((cash+1)/(i['total']+1)))
            return (-int(ref),-int(i['party'] in parties),ratio,i['issue'],i['iid'])
        ranked=sorted(candidates.values(),key=retrieval)
        keep={i['iid']:i for i in ranked[:36]}
        for r in static[tid]:
            if r[1]:keep[r[1]]=candidates[r[1]]
        per_tx[tid]=[];local={};base_keys={(r[1],r[2]) for r in static[tid] if r[1]}
        baseline_pairs[tid]=[];base_hyps[tid]=[]
        def add(i,amount,exception,kind):
            if amount<0:return None
            row=[tid,i['iid'],money(amount),'',exception]
            key=tuple(row[1:])
            if key in local:return local[key]
            facts=json.loads(i['facts']);doc=norm(i['doc']);digits=''.join(re.findall(r'\d',doc))
            total=i['total'];cur=i['currency'];issue=date.fromisoformat(i['issue']);book=date.fromisoformat(t['booking_date'])
            age=(book-issue).days;due=(book-date.fromisoformat(i['due'])).days if i['due'] else 0
            name=c.party_info.get(i['party'],{}).get('name',i['name'])
            payer=t.get('counterparty_name') or tx.split('|')[0]
            prefix=max((len(k)/max(len(doc),1) for k in ts if doc.startswith(k) and len(k)>=5),default=0)
            terms=c.terms.get(i['terms'],{});pct=float(terms.get('early_payment_discount_pct') or 0)
            eligible=bool(pct and age<=int(terms.get('discount_days') or 0)+3)
            x=[math.log1p(cash),math.log1p(amount),math.log1p(total),amount/max(total,1),cash/max(amount,1),
                abs(cash-amount)/max(cash,amount,1),amount/max(i['initial'],1),min(age,2000),max(-365,min(due,2000)),
                cur==t['currency'],cur==t.get('orig_currency'),cents(t['amount'])<0,doc in nt,
                any(len(k)>=5 and (doc.endswith(k) or digits.endswith(k)) for k in ts),prefix,
                SequenceMatcher(None,norm(payer),norm(name)).ratio(),i['party'] in parties,eligible,
                bool(facts.get('tranches')),bool(facts.get('retention')),bool(facts.get('advance')),is_return(t),
                bool(re.search(r'A CUENTA|PARTIAL|PLAZO|INSTALMENT|RATE',tt)),
                bool(re.search(r'3/3|2/2|RELEASE|SETTLEMENT|REMAINDER',tt)),
                bool(re.search(r'DISPUT|DEDUC|DAMAGED|PRICE DIFF',tt)),len(norm(payer))<8,
                (i['iid'],money(amount)) in base_keys,kind=='static',kind=='full',kind=='cash',kind=='tranche',
                t['statement_format']=='n43',t['statement_format']=='mt940',t['statement_format']=='camt053',
                i['side']=='AR',i['iid'].startswith(('ARC','APC')),math.log1p(len(pool)),pct]
            assert len(x)==len(FEATURES)
            x.extend(exception==e for e in EXCEPTIONS)
            pair_id=len(pair_rows);pair_rows.append(row);pair_x.append(x);per_tx[tid].append(pair_id);local[key]=pair_id
            item_parties[i['iid']]=i['party']
            return pair_id
        for row in static[tid]:
            if row[1]:baseline_pairs[tid].append(add(candidates[row[1]],cents(row[2]),row[4],'static'))
        base_hyps[tid].append({'kind':'static','pair_ids':baseline_pairs[tid],'rows':static[tid]})
        base_hyps[tid].append({'kind':'unidentified','pair_ids':[],'rows':[[tid,'','','UNIDENTIFIED','UNIDENTIFIED']]})
        for i in keep.values():
            if i['issue']>t['booking_date']:continue
            for paid,kind in [(i['initial'],'full')]:
                amount,exc=engine.policy(i,paid,t,force_return=is_return(t));add(i,amount,exc,kind)
            paid=engine.item_cash(i,t)
            if paid is not None and paid>0:
                amount,exc=engine.policy(i,paid,t,force_return=is_return(t));add(i,amount,exc,'cash')
            facts=json.loads(i['facts'])
            for amount in sorted(set(facts.get('tranches',[]))):
                if abs(amount-cash)<=max(1,.005*amount):
                    add(i,amount,'','tranche');add(i,amount,'PARTIAL','tranche')
            if i['iid'] in {r[1] for r in static[tid]}:
                for r in static[tid]:
                    if r[1]==i['iid'] and r[4] in ('PARTIAL','DUPLICATE_PAYMENT','OVERPAYMENT'):
                        add(i,cents(r[2]),'','static')
        # Entire alternative source groups are retained rather than flattened to top-N items.
        for g in sources.candidates(t):
            if g.account and g.account!=t['account_id'] or not g.account and g.entity!=t['entity']:continue
            if not engine.cash_matches(t,g.currency or t['currency'],g.cash):continue
            if not is_return(t) and (g.cash<0)!=(cents(t['amount'])<0):continue
            ids=[];seen=set()
            for e in g.entries:
                i=engine.resolve_entry(e,g,t)
                if i and i['iid'] not in seen:
                    amount,exc=engine.policy(i,e['paid'],t,e.get('reason',''),is_return(t))
                    ids.append(add(i,amount,exc,'full'));seen.add(i['iid'])
            if ids:
                base_hyps[tid].append({'kind':'source','pair_ids':ids,'rows':[pair_rows[j] for j in ids]})
        if index%1000==0:print(f'Candidates {index:,}/{len(banks):,}; pairs {len(pair_rows):,}',flush=True)
    feature_names=FEATURES+['exception_'+e for e in EXCEPTIONS]
    return dict(banks=banks,static=dict(static),pair_rows=pair_rows,X=np.asarray(pair_x,dtype=np.float32),
                per_tx=per_tx,base_hyps=base_hyps,phase=phase,docs=docs,feature_names=feature_names,
                item_parties=item_parties)
