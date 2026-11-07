"""Disk-backed TRAIN context and month-scoped sources for bounded v4 fitting.

No golden is read here. All invoice history stays searchable. Bank sampling is
fixed by a hash of the bank ID, before targets are attached.
"""
from collections import defaultdict, Counter
from datetime import date, timedelta
import csv
import hashlib
import json
from pathlib import Path
import re
import sqlite3

import joblib

from data import ROOT, load_strategy
from bankrec.catalog import Catalog as BaseCatalog
from bankrec.sources import Sources as BaseSources, Group
from bankrec.io import rows, table, norm, plain, cents, pdf_text, is_data_file, write_json

V3Catalog, V3Sources, V3Engine = load_strategy()


class Metadata:
    def __init__(self, catalog): self.catalog=catalog
    def get(self, iid, default=None):
        item=self.catalog.item(iid)
        return {'due_date':item['due']} if item else default


class DiskCatalog(V3Catalog.Catalog):
    """Same static interfaces without retaining millions of raw invoice dictionaries."""
    def __init__(self, dbpath, phase, masters, cache):
        print('Indexing complete TRAIN invoice history on disk...',flush=True)
        connect=sqlite3.connect
        def bulk_connection(*args,**kwargs):
            connection=connect(*args,**kwargs)
            connection.execute('PRAGMA cache_size=-524288')
            connection.execute('PRAGMA synchronous=NORMAL')
            connection.execute('PRAGMA temp_store=MEMORY')
            return connection
        # Constructor is synchronous; restore the shared module entry immediately.
        sqlite3.connect=bulk_connection
        try:BaseCatalog.__init__(self,dbpath,phase,masters,cache,False)
        finally:sqlite3.connect=connect
        self.as_of='9999-12-31'
        self.prefixes=defaultdict(set);self.children=defaultdict(set)
        self.group_members=defaultdict(set);self.related=defaultdict(set);self.mandates=defaultdict(set)
        active={r[0] for r in self.db.execute('SELECT DISTINCT party FROM items')}
        for pid,r in self.party_info.items():
            if r.get('sepa_mandate_id'):self.mandates[norm(r['sepa_mandate_id'])].add(pid)
            if r.get('parent_customer_id'):self.children[r['parent_customer_id']].add(pid)
            if r.get('group_id'):self.group_members[r['group_id']].add(pid)
        for alias,pids in self.aliases.items():
            if pids & active:
                for length in range(8,min(len(alias),40)+1):self.prefixes[alias[:length]].update(pids & active)
        for r in rows(table(phase,'credit_notes')):
            if r.get('related_document'):self.related[(r['entity'],norm(r['related_document']))].add(r['item_id'])
        print('Extracting TRAIN PDF policy clauses...',flush=True)
        self.load_facts(cache)
        for n,r in enumerate(rows(table(phase/'pdfs','index')),1):
            found=self.lookup(r['document_number'],entity=r['entity'],parties={r['party_id']})
            if len(found)!=1:continue
            tx=plain(pdf_text(phase/'pdfs'/r['file'],cache));i=found[0];facts=json.loads(i['facts'])
            plan=re.search(r'(?:\d+ INSTALMENTS|\d+ VENCIMIENTOS)[^\n]*?\(([^)]+)\)',tx)
            if plan:facts['tranches']=[cents(a.replace('.','').replace(',','.')) for a in re.findall(r'\d[\d.]*,\d{2}',plan[1])]
            month=re.search(r'(?:SERVICE|SERVICIO|MANTENIMIENTO|MAINTENANCE)[^\n]*(?:PERIOD|MONTH|MES|DE|:)[^\n]*',tx)
            if month:facts['service_clause']=month[0]
            self.db.execute('UPDATE items SET facts=? WHERE iid=?',(json.dumps(facts),i['iid']))
            if n%10000==0:print(f'PDF enhancements {n:,}',flush=True);self.db.commit()
        # Cancellation is effective only once the replacing invoice exists.
        for i in list(self.db.execute("SELECT iid,issue,entity,party,facts FROM items WHERE facts LIKE '%replaces%'")):
            facts=json.loads(i['facts']);old=facts.get('replaces')
            if not old:continue
            for original in self.db.execute('SELECT i.iid,i.facts FROM items i JOIN refs r ON r.iid=i.iid WHERE r.ref=? AND i.entity=? AND i.party=? AND i.iid!=?',(norm(old),i['entity'],i['party'],i['iid'])):
                f=json.loads(original['facts']);f['cancelled_from']=i['issue']
                self.db.execute('UPDATE items SET facts=? WHERE iid=?',(json.dumps(f),original['iid']))
        self.db.commit();self.metadata=Metadata(self)

    def visible(self,r):
        r=dict(r);f=json.loads(r['facts'])
        if getattr(self,'candidate_mode',False):r['balance']=r['initial']
        if f.get('cancelled_from') and f['cancelled_from']>self.as_of:
            f.pop('cancelled',None);r['facts']=json.dumps(f)
        return r

    def item(self,iid):
        r=self.db.execute('SELECT * FROM items WHERE iid=?',(iid,)).fetchone()
        return self.visible(r) if r else None

    def by_party(self,parties,booking):
        return [self.visible(r) for p in sorted(parties) for r in self.db.execute('SELECT * FROM items WHERE party=? AND issue<=? ORDER BY issue,iid',(p,booking))]

    def lookup(self,ref,entity=None,parties=None,side=None,booking='9999'):
        result={}
        for raw in self.db.execute('SELECT i.*,r.kind AS ref_kind FROM refs r JOIN items i ON i.iid=r.iid WHERE r.ref=?',(norm(ref),)):
            if entity and raw['entity']!=entity or parties and raw['party'] not in parties or side and raw['side']!=side:continue
            if raw['issue']>min(booking,self.as_of):continue
            r=self.visible(raw)
            if json.loads(r['facts']).get('cancelled'):continue
            result[r['iid']]=r
        return list(result.values())


def catalog(work,phase,masters):
    state=work/'catalog_state.joblib';db=work/'catalog.sqlite'
    if state.exists():
        c=object.__new__(DiskCatalog);c.__dict__.update(joblib.load(state))
        c.db=sqlite3.connect(db);c.db.row_factory=sqlite3.Row;c.metadata=Metadata(c)
        c.db.execute('PRAGMA cache_size=-131072')
    else:
        for suffix in ('','-wal','-shm'):Path(str(db)+suffix).unlink(missing_ok=True)
        c=DiskCatalog(db,phase,masters,ROOT/'work/cache/pdf_text')
        joblib.dump({k:v for k,v in c.__dict__.items() if k not in ('db','metadata')},state,compress=3)
    return c


class MonthSources(V3Sources.Sources):
    def __init__(self,phase,cache,catalog):
        self.catalog=catalog
        # The ordinary printed-reference index deliberately omits <5-character
        # keys. Due-date grouping must still support those short supplier numbers.
        if not catalog.db.execute("SELECT 1 FROM sqlite_master WHERE name='short_ap_due'").fetchone():
            catalog.db.execute('CREATE TABLE short_ap_due(doc TEXT,name TEXT,currency TEXT,due TEXT)')
            for r in catalog.db.execute("SELECT doc,name,currency,due FROM items WHERE side='AP' AND iid LIKE 'API-%'"):
                key=norm(r['doc'])
                if len(key)<5:catalog.db.execute('INSERT INTO short_ap_due VALUES(?,?,?,?)',(key,norm(r['name']),r['currency'],r['due']))
            catalog.db.execute('CREATE INDEX short_ap_lookup ON short_ap_due(doc,name,currency)')
            catalog.db.commit()
        super().__init__(phase,cache)

    def load_batches(self,phase):
        BaseSources.load_batches(self,phase)
        groups={}
        for f in sorted((phase/'payment_runs').glob('*.csv')):
            if not is_data_file(f):continue
            for n,r in enumerate(rows(f),2):
                if r['run_type']=='transfers':continue
                key='transfer-unit:'+r['debtor_account_id']+':'+r['end_to_end_id']
                if key not in groups:
                    groups[key]=Group(key,'payment_runs',str(f.relative_to(phase)),r['execution_date'],r['currency'],-cents(r['transfer_amount']),r['debtor_account_id'],r['debtor_account_id'].split('-')[0],[],{r['run_id'],r['end_to_end_id']})
                groups[key].entries.append(dict(doc=r['document_number'],paid=abs(cents(r['document_amount'])),credit=cents(r['document_amount'])<0,name=r['beneficiary'],iban=r['beneficiary_iban'],side='AP',reason='',source=str(f.relative_to(phase)),line=n))
        for g in groups.values():self.add(g)
        maturities={}
        for g in groups.values():
            dates=[]
            for e in g.entries:
                if e['credit']:continue
                # Direct SQL preserves invoice due-date lookup without a full raw AP dict.
                if len(norm(e['doc']))<5:
                    known={r['due'] for r in self.catalog.db.execute('SELECT due FROM short_ap_due WHERE doc=? AND name=? AND currency=?',(norm(e['doc']),norm(e['name']),g.currency))}
                else:
                    known={r['due'] for r in self.catalog.db.execute("SELECT i.due,i.name,i.doc FROM items i JOIN refs r ON r.iid=i.iid WHERE r.ref=? AND i.currency=? AND i.iid LIKE 'API-%'",(norm(e['doc']),g.currency)) if norm(r['name'])==norm(e['name']) and norm(r['doc'])==norm(e['doc'])}
                if len(known)==1:dates.extend(known)
            if not dates:continue
            maturity=max(dates);run=sorted(r for r in g.refs if '-' not in r)[0]
            key='maturity:'+g.account+':'+run+':'+maturity
            if key not in maturities:maturities[key]=Group(key,'payment_runs',g.source,maturity,g.currency,0,g.account,g.entity,[],{run})
            maturities[key].cash+=g.cash;maturities[key].entries.extend(g.entries)
        for g in maturities.values():self.add(g)


def month_view(phase,work,month):
    """Source files in a +/-45-day window; never link golden into inference views."""
    view=work/'source_views'/month
    if (view/'.complete').exists():return view
    start=date.fromisoformat(month+'-01');lo=(start-timedelta(days=45)).isoformat();hi=(start+timedelta(days=76)).isoformat()
    months={(start+timedelta(days=d)).strftime('%Y%m') for d in range(-45,77)}
    for kind in ('direct_debit_batches','card_settlements','cheque_deposits','payment_runs'):
        dest=view/kind;dest.mkdir(parents=True,exist_ok=True)
        for f in (phase/kind).glob('*.csv'):
            if is_data_file(f) and any(m in f.name for m in months):(dest/f.name).symlink_to(f.resolve())
    folder=view/'remittance_advices';folder.mkdir(parents=True,exist_ok=True)
    selected=[]
    for r in rows(table(phase/'remittance_advices','index')):
        if lo<=r['received_date']<=hi:
            selected.append(r);dest=folder/r['file'];dest.parent.mkdir(parents=True,exist_ok=True)
            if not dest.exists():dest.symlink_to((phase/'remittance_advices'/r['file']).resolve())
    with (folder/'index.csv').open('w',newline='') as f:
        w=csv.DictWriter(f,fieldnames=['file','entity','payer_name','received_date','format']);w.writeheader();w.writerows(selected)
    (view/'.complete').write_text('label-free source window\n')
    return view


def role(date_):
    if date_<'2024-01-01':return 'pair_fit'
    if date_<'2024-07-01':return 'hypothesis_fit'
    if date_<'2025-01-01':return 'calibration'
    if date_<'2025-06-01':return 'test'
    return 'inspected_starter_excluded'


def sample_banks(phase,per_month=1500):
    import heapq
    samples=defaultdict(list);counts=Counter()
    for t in rows(table(phase,'bank_transactions')):
        month=t['booking_date'][:7];counts[month]+=1
        if role(t['booking_date'])=='inspected_starter_excluded':continue
        key=int.from_bytes(hashlib.sha256(('v4-train-42:'+t['bank_txn_id']).encode()).digest()[:8],'big')
        heap=samples[month];entry=(-key,t['bank_txn_id'],t)
        if len(heap)<per_month:heapq.heappush(heap,entry)
        elif entry>heap[0]:heapq.heapreplace(heap,entry)
    return {m:{t['bank_txn_id']:t for _,_,t in sorted(h,key=lambda x:(x[2]['booking_date'],x[1]))} for m,h in sorted(samples.items())},dict(counts)
