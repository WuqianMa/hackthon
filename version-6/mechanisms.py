"""Source-linked synthetic mechanisms. Inference never reads golden labels.

The organizer's POLICIES sections 2–5 define the arithmetic and month offset.
TRAIN examples supply additional English templates and return signatures.
"""
from collections import defaultdict, Counter
from datetime import date
from decimal import Decimal, ROUND_HALF_UP
from functools import lru_cache
import itertools
import json
from pathlib import Path
import re

from bankrec.io import rows, norm, plain, cents, money, digest
from bankrec.engine import text_of, is_return
from bankrec.catalog import tokens, reference_keys
from recovery import service_period, cash_in, SERVICE_MARKER

ROOT=Path(__file__).resolve().parent.parent
RETURN_AP=re.compile(r'RETURN(?:ED)?\s+(?:AC\d\d|BE\d\d|AM\d\d|TRANSFER|PAYMENT)|DEVOLUCION\s+(?:DE\s+)?TRANSFER|REJET.*VIREMENT')
RETURN_CHEQUE=re.compile(r'RETURNED ITEM\s+(?:CHK|CHEQUE)|CHEQUE\s+(?:IMPAYE|RETURN)|CHK.*(?:NSF|REFER TO MAKER)|CHEQUE.*(?:DEVUEL|IMPAG)')
RETURN_CARD=re.compile(r'CHARGEBACK|RETROCESION.*TARJETA')
SEPA={'ES','FR','DE','IT','PT','NL','BE','LU','AT','IE','FI','GR','MT','CY','EE','LV','LT','SI','SK','HR','BG','RO','PL','CZ','HU','SE','DK','GB','CH','NO','IS','LI','MC','SM','AD','VA'}


def number(value):
    """A PDF amount with either European or English punctuation, in cents."""
    s=value.strip().replace(' ','').replace('\u00a0','')
    if ',' in s and '.' in s:
        decimal=',' if s.rfind(',')>s.rfind('.') else '.'
        s=s.replace('.' if decimal==',' else ',','').replace(decimal,'.')
    elif ',' in s:s=s.replace(',','.')
    return cents(s)


def parse_facts(text):
    tx=plain(text);out={}
    old=re.search(r'(?:CANCELS AND REPLACES (?:INVOICE|BILL)|ANULA Y SUSTITUYE A LA FACTURA)\s+([A-Z0-9/.-]+)',tx)
    if old:out['replaces']=old[1].rstrip('.')
    advance=re.search(r'(?:LESS ADVANCE RECEIVED|DEDUCIR ANTICIPO)[^\n]*',tx)
    if advance:
        out['advance']=True;out['advance_clause']=advance[0]
        net=re.search(r'(?:NET AMOUNT DUE|IMPORTE NETO A PAGAR)\s*[: ]\s*([\d][\d., ]*[.,]\d{2})',advance[0])
        if net:out['advance_net']=number(net[1])
    if re.search(r'RETENCION EN GARANTIA|GUARANTEE RETENTION|RETENTION.*FINAL ACCEPTANCE',tx):out['retention']=True
    month=re.search(r'(?:SERVICE|SERVICIO|MANTENIMIENTO|MAINTENANCE)[^\n]*(?:MONTH|PERIOD|MES|:)[^\n]*',tx)
    if month:out['service_clause']=month[0]
    return out


class CatalogView:
    """Read-only catalog plus facts from already cached PDF text, including aliases."""
    def __init__(self,base,banks):
        self.base=base;self.extra={};self.replacements=defaultdict(set);self.replacement_refs=defaultdict(set);self.advance_cash=defaultdict(set);self.stats=Counter()
        # Only inspect invoice PDFs available by the experiment's last booking date.
        hi=max(t['booking_date'] for t in banks.values())
        for r in rows(base.phase/'pdfs/index.csv'):
            if r['document_type']!='invoice' or r['document_date']>hi:continue
            p=base.phase/'pdfs'/r['file']
            cached=ROOT/'work/cache/pdf_text'/(digest(p)+'.txt')
            if not cached.exists():self.stats['uncached_skipped']+=1;continue
            f=parse_facts(cached.read_text(encoding='utf-8'))
            if not f:continue
            found=list(base.db.execute('SELECT i.* FROM items i JOIN refs r ON r.iid=i.iid WHERE r.ref=? AND i.entity=? AND i.party=?',
                         (norm(r['document_number']),r['entity'],r['party_id'])))
            found={i['iid']:dict(i) for i in found if norm(i['doc'])==norm(r['document_number'])}
            if len(found)!=1:continue
            iid,i=next(iter(found.items()));f['source']='pdfs/'+r['file'];self.extra[iid]=f
            if f.get('advance_net'):self.advance_cash[(i['entity'],i['currency'],f['advance_net'])].add(iid)
            self.stats.update(k for k in f if k not in ('source','advance_clause'))
            if f.get('replaces'):
                self.replacements[(i['entity'],i['party'],norm(f['replaces']))].add(iid)
                for key in reference_keys(f['replaces']):self.replacement_refs[key].add(iid)
        self.stats['cached_invoice_facts']=len(self.extra)
        self.replacement_parties={party for _,party,_ in self.replacements}
        self.credit_parents=defaultdict(set)
        for key,ids in base.related.items():
            for iid in ids:self.credit_parents[iid].add(key)
        self.credit_parties={r[0] for r in base.db.execute("SELECT DISTINCT party FROM items WHERE iid>='ARC-' AND iid<'ARD'")}

    def __getattr__(self,name):return getattr(self.base,name)
    @lru_cache(maxsize=100000)
    def raw(self,iid):return self.base.item(iid)
    def item(self,iid):
        i=self.raw(iid)
        if not i:return None
        i=dict(i);f=json.loads(i['facts']);f.update(self.extra.get(iid,{}));i['facts']=json.dumps(f)
        return i
    def by_party(self,parties,booking):return [self.item(i['iid']) for i in self.base.by_party(parties,booking)]
    def lookup(self,*args,**kwargs):return [self.item(i['iid']) for i in self.base.lookup(*args,**kwargs)]


def return_kind(t):
    tx=plain(text_of(t))
    if cents(t['amount'])<0 and RETURN_CARD.search(tx):return 'card'
    if cents(t['amount'])<0 and RETURN_CHEQUE.search(tx):return 'cheque'
    if cents(t['amount'])>0 and RETURN_AP.search(tx):return 'ap'
    return 'dd' if is_return(t) else ''


class SourceIndex:
    """Bounded structured source indexing for observed return references only."""
    def __init__(self,c,banks):
        self.c=c;self.ap=defaultdict(list);self.cheques=defaultdict(list);self.cards=defaultdict(list);self.stats=Counter()
        aprefs=set();cheques=set();cards=set();accounts=set();dates=[]
        for t in banks.values():
            kind=return_kind(t);tx=plain(text_of(t));accounts.add(t['account_id'])
            if kind=='ap':aprefs.update(norm(x) for x in re.findall(r'\bPR\d[\d-]{6,}',tx))
            if kind=='cheque':cheques.update(re.findall(r'\b\d{6,9}\b',tx))
            if kind=='card':
                m=re.search(r'\*+(\d{4})',tx)
                if m:cards.add(m[1])
            if kind in ('ap','cheque','card'):dates.append(t['booking_date'])
        if not dates:return
        lo=date.fromordinal(date.fromisoformat(min(dates)).toordinal()-120).isoformat();hi=max(dates)
        for kind,needed in (('payment_runs',aprefs),('cheque_deposits',cheques),('card_settlements',cards)):
            if not needed:continue
            for path in sorted((c.phase/kind).glob('*.csv')):
                if path.name.startswith('._'):continue
                # Filename date is only an IO partition, never a matching feature.
                match=re.search(r'_(20\d{4})(?:_|\.)',path.name)
                if match and not lo[:7].replace('-','')<=match[1]<=hi[:7].replace('-',''):continue
                for r in rows(path):
                    if kind=='payment_runs':
                        if norm(r['end_to_end_id']) in needed and lo<=r['execution_date']<=hi:
                            self.ap[(r['debtor_account_id'],norm(r['end_to_end_id']))].append(r)
                    elif kind=='cheque_deposits':
                        if r['cheque_number'] in needed and lo<=r['deposit_date']<=hi:
                            self.cheques[(r['account_id'],r['cheque_number'])].append(r)
                    else:
                        last=re.sub(r'\D','',r['card'])[-4:]
                        if last in needed and lo<=r['settlement_date']<=hi:
                            self.cards[(r['account_id'],last)].append(r)
        self.stats.update(ap_transfers=len(self.ap),cheque_numbers=len(self.cheques),card_orders=sum(map(len,self.cards.values())))

    def resolve(self,doc,name,t,side,currency,amount):
        c=self.c
        parties=c.identify(name,side=side)
        found=c.lookup(doc,parties=parties or None,side=side,booking=t['booking_date'])
        found=[i for i in found if norm(i['doc'])==norm(doc) and i['currency']==currency and amount<=i['total']+1]
        if not found and len(norm(doc))<5 and parties:
            found=[i for i in c.by_party(parties,t['booking_date']) if norm(i['doc'])==norm(doc) and i['currency']==currency and amount<=i['total']+1]
        return found[0] if len(found)==1 else None

    def returned(self,t):
        kind=return_kind(t);tx=plain(text_of(t));out=[];candidates=[]
        if kind=='ap':
            for ref in re.findall(r'\bPR\d[\d-]{6,}',tx):
                rs=self.ap.get((t['account_id'],norm(ref)),[])
                if not rs or any(r['execution_date']>t['booking_date'] for r in rs):continue
                curr=rs[0]['currency'];cash=cash_in(t,curr)
                if cash is None or abs(sum(cents(r['document_amount']) for r in rs)-cash)>1:continue
                result=[]
                for r in rs:
                    amount=abs(cents(r['document_amount']));i=self.resolve(r['document_number'],r['beneficiary'],t,'AP',curr,amount)
                    if not i:break
                    result.append([t['bank_txn_id'],i['iid'],money(amount),'','RETURNED'])
                else:candidates.append(result)
        elif kind=='cheque':
            for ref in re.findall(r'\b\d{6,9}\b',tx):
                for r in self.cheques.get((t['account_id'],ref),[]):
                    amount=cents(r['amount'])
                    if r['deposit_date']>t['booking_date'] or cash_in(t,r['currency'])!=amount:continue
                    i=self.resolve(r['stub_reference'],r['drawer'],t,'AR',r['currency'],amount)
                    # A stub may omit the printed-number prefix; party scopes it.
                    if not i:
                        p=self.c.identify(r['drawer'],entity=t['entity'],side='AR')
                        found=[j for j in self.c.lookup(r['stub_reference'],entity=t['entity'],parties=p or None,side='AR',booking=t['booking_date']) if j['total']==amount]
                        if len(found)==1:i=found[0]
                    if i:candidates.append([[t['bank_txn_id'],i['iid'],money(amount),'','RETURNED']])
        elif kind=='card':
            card=re.search(r'\*+(\d{4})',tx);merchant=re.search(r'\bMID\s+(\d+)',tx)
            if card:
                for r in self.cards.get((t['account_id'],card[1]),[]):
                    if merchant and norm(r['merchant_id'])!=merchant[1]:continue
                    amount=cents(r['gross'])
                    if r['settlement_date']>t['booking_date'] or cash_in(t,r['currency'])!=amount:continue
                    i=self.resolve(r['order_number'],'',t,'AR',r['currency'],amount)
                    if i:candidates.append([[t['bank_txn_id'],i['iid'],money(amount),'','RETURNED']])
        unique={tuple(sorted(map(tuple,rs))):rs for rs in candidates if len({r[1] for r in rs})==len(rs)}
        if len(unique)==1:return next(iter(unique.values())),'v6:source_return_'+kind
        return None


def facts(i):return json.loads(i.get('facts') or '{}')
def row(t,i,a,exc=''):
    if not exc and i['currency']!=t['currency'] and not i['iid'].startswith(('ARC','APC')):exc='FX_DIFFERENCE'
    return [t['bank_txn_id'],i['iid'],money(a),'',exc]


def parties_for(t,current,c,side='AR'):
    ps=c.identify(t.get('counterparty_name') or text_of(t),entity=t['entity'],side=side,iban=t.get('counterparty_account',''))
    for r in current:
        if r[1]:
            i=c.item(r[1])
            if i['side']==side:ps.add(i['party'])
    return ps


def service_month(t,current,c,ledger):
    text=plain(text_of(t))
    if cents(t['amount'])<=0 or not SERVICE_MARKER.search(text):return None
    # Compact MONTHYYYY is emitted by some bank formats.
    period=service_period(re.sub(r'([A-Z])(?=20\d{2}\b)',r'\1 ',text),t['booking_date'])
    if not period:return None
    year,month=period;following=(year+int(month==12),month%12+1)
    ps=parties_for(t,current,c)
    if not ps or len(ps)>8:return None
    matches=[]
    for i in c.by_party(ps,t['booking_date']):
        if not i['iid'].startswith('ARI') or facts(i).get('cancelled') or cash_in(t,i['currency'])!=i['total']:continue
        issue=date.fromisoformat(i['issue']);clause=facts(i).get('service_clause') or facts(i).get('service_month')
        if clause:
            if service_period(clause,i['issue'])!=period:continue
        elif (issue.year,issue.month)!=following or issue.day>5:continue
        if ledger.balance(i['iid'])<=0:continue
        matches.append(i)
    if len(matches)==1:return [row(t,matches[0],matches[0]['total'])],'v6:service_month_following_invoice'
    return None


def replacement(t,current,c,ledger):
    text=text_of(t);tx=norm(text);ids=set();hits=[]
    for token in tokens(text):ids.update(c.replacement_refs.get(token,()))
    if not ids:return None
    ps=parties_for(t,current,c)&c.replacement_parties
    for i in (c.item(iid) for iid in ids):
        if i['entity']!=t['entity'] or i['issue']>t['booking_date'] or (ps and i['party'] not in ps):continue
        old=facts(i).get('replaces')
        if not old or norm(old) not in tx or facts(i).get('cancelled'):continue
        if cash_in(t,i['currency'])==i['total']:hits.append(i)
    if len(hits)==1:return [row(t,hits[0],hits[0]['total'])],'v6:english_or_spanish_replacement'
    return None


def reference_strength(doc,tx,ts):
    d=norm(doc);digits=''.join(re.findall(r'\d',d))
    if d and d in norm(tx):return 4
    if any(len(k)>=5 and (d.endswith(k) or digits.endswith(k)) for k in ts):return 3
    if any(len(k)>=6 and (d.startswith(k) or digits.startswith(k)) for k in ts):return 2
    # One transposition/substitution in a long full printed reference, within a known party.
    for k in ts:
        if len(k)!=len(d) or len(k)<9:continue
        diffs=[n for n,(a,b) in enumerate(zip(k,d)) if a!=b]
        if len(diffs)==1 or (len(diffs)==2 and diffs[1]==diffs[0]+1 and k[diffs[0]]==d[diffs[1]] and k[diffs[1]]==d[diffs[0]]):return 1
    return 0


def netting(t,current,c,ledger):
    tx=text_of(t);text=plain(tx)
    if cents(t['amount'])<=0 or not re.search(r'\bCN\b|CREDIT (?:NOTE|MEMO)|ABONO|\bAV\d|\bNC\d|\bCM\d',text):return None
    ps=parties_for(t,current,c)
    if not ps or len(ps)>8:return None
    ts=tokens(tx);items=[]
    for i in c.by_party(ps,t['booking_date']):
        if i['side']!='AR' or facts(i).get('cancelled'):continue
        s=reference_strength(i['doc'],tx,ts)
        if not s:continue
        amount=ledger.balance(i['iid'])
        if amount<=0:continue
        items.append((i,amount,s))
    if len(items)>22:return None
    invoices=[x for x in items if x[0]['iid'].startswith('ARI')];credits=[x for x in items if x[0]['iid'].startswith('ARC')]
    if not invoices or not credits or len(invoices)>16 or len(credits)>6:return None
    solutions=[]
    for currency in sorted({i['currency'] for i,_,_ in items}):
        cash=cash_in(t,currency)
        if cash is None:continue
        inv=[x for x in invoices if x[0]['currency']==currency];cn=[x for x in credits if x[0]['currency']==currency]
        if len(inv)>14:continue
        credit_sums=defaultdict(list)
        for mask in range(1,1<<len(cn)):
            chosen=[cn[j] for j in range(len(cn)) if mask>>j&1];credit_sums[sum(x[1] for x in chosen)].append(chosen)
        for mask in range(1,1<<len(inv)):
            selected=[inv[j] for j in range(len(inv)) if mask>>j&1];need=sum(x[1] for x in selected)-cash
            for chosen in credit_sums.get(need,[]):solutions.append(selected+chosen)
            if len(solutions)>1:return None
    if len(solutions)==1:return [row(t,i,a) for i,a,_ in solutions[0]],'v6:referenced_signed_credit_net'
    return None


def related_netting(t,current,c,ledger):
    """Recover linked credit/invoice nets even when the bank omitted CN wording."""
    if cents(t['amount'])<=0:return None
    if current[0][3] not in ('','UNIDENTIFIED'):return None
    if any(r[4] in ('RETURNED','DUPLICATE_PAYMENT','SHORT_DISPUTE','SHORT_DISCOUNT','SHORT_WITHHOLDING') for r in current):return None
    if current and all(r[1] and not r[4] for r in current):
        ii=[c.item(r[1]) for r in current];curr=ii[0]['currency'];cash=cash_in(t,curr)
        if cash is not None and all(i['currency']==curr for i in ii):
            expected=sum((-1 if i['iid'].startswith('ARC') else 1)*cents(r[2]) for i,r in zip(ii,current))
            if abs(expected-cash)<=1:return None
    ps=parties_for(t,current,c)&c.credit_parties
    if not ps or len(ps)>4:return None
    existing=[c.item(r[1]) for r in current if r[1]]
    inv=[i for i in existing if i['iid'].startswith('ARI')]
    solutions={}
    for party in sorted(ps):
        credits=[c.item(r[0]) for r in c.db.execute("SELECT iid FROM items WHERE party=? AND issue<=? AND iid LIKE 'ARC-%'",(party,t['booking_date']))]
        for credit in credits:
            ca=ledger.balance(credit['iid']);curr=credit['currency'];cash=cash_in(t,curr)
            if cash is None or ca<=0 or facts(credit).get('cancelled'):continue
            parents=[]
            for entity,doc in c.credit_parents.get(credit['iid'],()):
                replacing=c.replacements.get((entity,party,doc),())
                if any(c.item(iid)['issue']<=t['booking_date'] for iid in replacing):continue
                parents.extend(i for i in c.lookup(doc,entity=entity,parties={party},side='AR',booking=t['booking_date']) if norm(i['doc'])==doc)
            # All rows of an incumbent may have been truncated or missed; at a
            # minimum the documented parent gives an independent exact-net proposal.
            pools=[parents]
            if inv and len(inv)<=16 and any(i['iid'] in {j['iid'] for j in parents} for i in inv):pools.append(inv)
            for pool in pools:
                if not pool or len({i['iid'] for i in pool})!=len(pool):continue
                if any(i['currency']!=curr or i['party']!=party or facts(i).get('cancelled') for i in pool):continue
                amounts=[ledger.balance(i['iid']) for i in pool]
                if any(a<=0 for a in amounts) or abs(sum(amounts)-ca-cash)>1:continue
                result=[row(t,i,a) for i,a in zip(pool,amounts)]+[row(t,credit,ca)]
                solutions[tuple(sorted(map(tuple,result)))]=result
    if len(solutions)==1:return next(iter(solutions.values())),'v6:related_credit_cash_identity'
    return None


def single_policy(t,current,c,ledger):
    if len(current)!=1 or not current[0][1] or return_kind(t):return None
    i=c.item(current[0][1]);iid=i['iid'];tx=plain(text_of(t))
    if not iid.startswith(('ARI','API')) or (i['side']=='AR')!=(cents(t['amount'])>0):return None
    paid=cash_in(t,i['currency'])
    if paid is None or paid<=0:return None
    f=facts(i);before=ledger.balance(iid)
    # A prior prediction is useful ledger evidence, but cannot invent a duplicate
    # from an exhausted or incorrectly chosen item without a reference/cash mirror.
    full=i['initial'];short=full-paid;desired=None;why=''
    if f.get('advance') and paid<full-1:
        if not f.get('advance_net') or abs(paid-f['advance_net'])<=1:
            desired=(paid,'PARTIAL');why='documented_advance_net'
    if short>0 and current[0][4] not in ('RETURNED','DUPLICATE_PAYMENT','SHORT_DISPUTE'):
        country=c.party_info.get(i['party'],{}).get('country','')
        if country in {'MX','BR','MA'}:
            for pct in ('1.25','1.5','10'):
                expected=int((Decimal(i['total'])*(1-Decimal(pct)/100)).quantize(Decimal('1'),rounding=ROUND_HALF_UP))
                if abs(paid-expected)<=1:desired=(full,'SHORT_WITHHOLDING');why='fixed_rate_withholding'
        fee_marker=re.search(r'CHGS|GASTOS SHA|\bSHA\b|\bBEN\b|BANK CHARGE',tx)
        cross_code='XBCT' in t.get('bank_code','')
        if (country and country not in SEPA and (fee_marker or cross_code) and short*100<=i['total']*2
                and Decimal(short)/c.rate(i['currency'],t['booking_date'])<=6000):
            desired=(full,'SHORT_BANK_CHARGES');why='crossborder_fee_tolerance'
    if desired:
        a,e=desired
        if i['currency']!=t['currency'] and e!='PARTIAL':e='FX_DIFFERENCE'
        result=[row(t,i,a,e)]
        if result!=current:return result,'v6:'+why
    return None


def documented_advance(t,current,c,ledger):
    if cents(t['amount'])<=0:return None
    ids=set()
    for curr in {t['currency'],t.get('orig_currency','')}:
        cash=cash_in(t,curr) if curr else None
        if cash is not None:
            for delta in (-1,0,1):ids.update(c.advance_cash.get((t['entity'],curr,cash+delta),()))
    if not ids:return None
    ps=parties_for(t,current,c);matches=[]
    for iid in ids:
        i=c.item(iid)
        if i['issue']>t['booking_date'] or i['party'] not in ps or facts(i).get('cancelled'):continue
        cash=cash_in(t,i['currency'])
        if cash and cash<ledger.balance(iid):matches.append(row(t,i,cash,'PARTIAL'))
    if len(matches)==1:return matches,'v6:retrieved_document_advance_net'
    return None


def retrieved_fee(t,current,c,ledger):
    """A missing near-full invoice can be retrieved before classifying its fee.

    Exact cash arithmetic and a known payer are required; bank family/narrative
    supplies the cross-border evidence. Never reinterpret a structured group.
    """
    if cents(t['amount'])<=0:return None
    if current[0][3] not in ('','UNIDENTIFIED'):return None
    if len(current)>1:return None
    if current[0][4] not in ('','UNIDENTIFIED','PARTIAL','OVERPAYMENT'):return None
    if current[0][1] and not current[0][4]:
        existing=c.item(current[0][1])
        if cash_in(t,existing['currency'])==cents(current[0][2]):return None
    tx=plain(text_of(t));marker=re.search(r'CHGS|GASTOS SHA|\bSHA\b|BANK CHARGE',tx)
    if re.search(r'EXPTE|SETTLEMENT|REMAINDER|RETENTION|RETENCION',tx):return None
    international=bool(marker or 'XBCT' in t.get('bank_code',''))
    if not international and not (current[0][1] and current[0][4]=='PARTIAL'):return None
    ps=parties_for(t,current,c)
    if not ps or len(ps)>4:return None
    options=[];ts=tokens(tx)
    for currency in {t['currency'],t.get('orig_currency','')}:
        if not currency:continue
        cash=cash_in(t,currency)
        if cash is None:continue
        upper=min(int(Decimal(cash)/Decimal('.98'))+1,cash+int(Decimal(6000)*c.rate(currency,t['booking_date'])))
        for party in sorted(ps):
            country=c.party_info.get(party,{}).get('country','')
            for raw in c.db.execute("SELECT * FROM items WHERE party=? AND currency=? AND total>? AND total<=? AND issue<=? AND iid LIKE 'ARI-%'",(party,currency,cash,upper,t['booking_date'])):
                i=c.item(raw['iid']);f=facts(i);short=i['total']-cash
                if f.get('cancelled') or f.get('advance') or f.get('retention') or f.get('instalments') or short<=1:continue
                if ledger.balance(i['iid'])!=i['initial'] or i['initial']!=i['total']:continue
                ref=reference_strength(i['doc'],tx,ts)
                if not ref and (date.fromisoformat(t['booking_date'])-date.fromisoformat(i['issue'])).days>180:continue
                if not ref and c.party_info.get(party,{}).get('invoice_currency',currency)!=currency:continue
                # A round fee with a direct document reference is supported even
                # when a SEPA-country payer chose a cross-border payment route.
                round_fee=(short%500==0)
                if not (marker or (international and country and country not in SEPA) or (ref>=3 and round_fee)):continue
                if short*100>i['total']*2 or Decimal(short)/c.rate(currency,t['booking_date'])>6000:continue
                # Do not relabel an exact payment-term discount as bank charges.
                terms=c.terms.get(i.get('terms',''),{})
                discount=Decimal(str(terms.get('early_payment_discount_pct') or 0))
                if discount and abs(Decimal(i['total'])*discount/100-short)<=1:continue
                options.append(row(t,i,i['initial'],'SHORT_BANK_CHARGES' if currency==t['currency'] else 'FX_DIFFERENCE'))
    if len(options)==1:return options,'v6:retrieved_crossborder_fee_invoice'
    return None


def referenced_partial_group(t,current,c,ledger):
    """A multi-document transfer may fully clear older rows and part-pay the newest.

    Require at least two distinct reference-resolved invoices, a unique ordering,
    and a generator-style 40/50/60% residual (cent rounding allowed). A known
    remaining balance takes precedence. This is not an arbitrary residual fit.
    """
    if cents(t['amount'])<=0:return None
    if current and current[0][3] not in ('','UNIDENTIFIED'):return None
    if current and all(r[1] and not r[4] for r in current):
        ii=[c.item(r[1]) for r in current];cash=cash_in(t,ii[0]['currency'])
        if cash is not None and all(i['currency']==ii[0]['currency'] for i in ii):
            expected=sum((-1 if i['iid'].startswith('ARC') else 1)*cents(r[2]) for i,r in zip(ii,current))
            if abs(expected-cash)<=1:return None
    tx=text_of(t);ts=tokens(tx)
    usable=[k for k in ts if sum(ch.isdigit() for ch in k)>=5]
    if len(usable)<2:return None
    ps=parties_for(t,current,c)
    if not ps or len(ps)>8:return None
    found={}
    for token in usable:
        matches=[i for i in c.lookup(token,entity=t['entity'],parties=ps,side='AR',booking=t['booking_date']) if i['iid'].startswith('ARI') and not facts(i).get('cancelled')]
        if len(matches)==1:found[matches[0]['iid']]=matches[0]
    if not 2<=len(found)<=10 or len({i['currency'] for i in found.values()})!=1:return None
    items=sorted(found.values(),key=lambda i:(i['issue'],i['iid']))
    cash=cash_in(t,items[0]['currency'])
    if cash is None:return None
    # Require explicit reference coverage; unrelated incumbent items are not inserted.
    amounts={i['iid']:ledger.balance(i['iid']) for i in items}
    if any(a<=0 for a in amounts.values()):return None
    if abs(sum(amounts.values())-cash)<=1:
        return [row(t,i,amounts[i['iid']]) for i in items],'v6:referenced_group_remaining_balance'
    latest=items[-1]
    if len(items)>1 and items[-2]['issue']==latest['issue']:return None
    residue=cash-sum(amounts[i['iid']] for i in items[:-1])
    if not 0<residue<amounts[latest['iid']]-1:return None
    if not any(abs(residue*100-latest['total']*pct)<=100 for pct in (40,50,60)):return None
    result=[row(t,i,amounts[i['iid']]) for i in items[:-1]]+[row(t,latest,residue,'PARTIAL')]
    return result,'v6:referenced_newest_partial_group'


def duplicate_refund(t,current,c):
    if cents(t['amount'])<=0 or return_kind(t):return None
    tx=plain(text_of(t))
    # Do not confuse an actual supplier credit-note refund with reimbursement of a duplicate.
    if not re.search(r'DUPLIC|DOUBLE|DOBLE|DOPPIO|PAGAMENTO DOPPIO|PAGO DUP',tx):return None
    ps=c.identify(t.get('counterparty_name') or tx,entity=t['entity'],side='AP',iban=t.get('counterparty_account',''))
    if not ps:return None
    return [[t['bank_txn_id'],'','','SUPPLIER_REFUND','']],'v6:duplicate_supplier_refund'


def propose(t,current,c,ledger,sources,enabled=None):
    enabled=enabled or {'returns','service','replacement','netting','policy','refund','partial_group','advance','fee','related_net'}
    if 'returns' in enabled:
        result=sources.returned(t)
        if result:return result
    if return_kind(t):return None
    for name,fn in (('refund',lambda:duplicate_refund(t,current,c)),('service',lambda:service_month(t,current,c,ledger)),
                    ('replacement',lambda:replacement(t,current,c,ledger)),('netting',lambda:netting(t,current,c,ledger)),
                    ('related_net',lambda:related_netting(t,current,c,ledger)),
                    ('advance',lambda:documented_advance(t,current,c,ledger)),('fee',lambda:retrieved_fee(t,current,c,ledger)),
                    ('partial_group',lambda:referenced_partial_group(t,current,c,ledger)),
                    ('policy',lambda:single_policy(t,current,c,ledger))):
        if name in enabled:
            result=fn()
            if result:return result
    return None
