from collections import defaultdict
from datetime import date
import json
import re

from bankrec.engine import Engine as BaseEngine, text_of, is_return
from bankrec.catalog import tokens
from bankrec.io import cents, norm, plain


class Engine(BaseEngine):
    speculative=False

    def reconcile(self,t,reversal_ids=()):
        rows,evidence=self._reconcile(t,reversal_ids)
        rows.sort(key=lambda row:(row[1],row[2],row[3],row[4]))
        return rows,evidence

    def _reconcile(self,t,reversal_ids=()):
        # Incoming supplier credits and outgoing customer credit notes reverse usual direction.
        if t['bank_txn_id'] not in reversal_ids and not is_return(t):
            side='AP' if cents(t['amount'])>0 else 'AR'
            parties=self.c.identify(t.get('counterparty_name','') or text_of(t),entity=t['entity'],side=side,iban=t.get('counterparty_account',''))
            credits=[i for i in self.c.by_party(parties,t['booking_date']) if i['iid'].startswith(('ARC','APC')) and i['balance']>0]
            matches=[i for i in credits if self.cash_matches(t,i['currency'],i['balance'])]
            if matches:
                i=sorted(matches,key=lambda i:(i['issue'],i['iid']))[0]
                self.c.apply(i['iid'],i['balance'],'')
                from bankrec.io import money
                return [[t['bank_txn_id'],i['iid'],money(i['balance']),'','']],{'method':'v3:credit_payout'}
        if not self.speculative:
            return super().reconcile(t,reversal_ids)
        apply=self.c.apply
        events=[]
        self.c.apply=lambda *event:events.append(event)
        try:
            result=super().reconcile(t,reversal_ids)
        finally:
            self.c.apply=apply
        if result[1]['method'] not in ('v3:speculative_prefix','v3:party_ranked'):
            for event in events:
                apply(*event)
        return result

    def policy(self, item, paid, t, reason='', force_return=False):
        result = super().policy(item, paid, t, reason, force_return)
        if force_return or item['iid'].startswith(('ARC','APC')):
            return result
        tx = plain(text_of(t))
        facts = json.loads(item['facts'])
        markers = re.search(r'(?:RATE|PAGO|PAYMENT|PLAZO|INSTALMENT)\s*(\d)\s*(?:/|DE|OF)\s*(\d)',tx)
        if result[1]=='PARTIAL' and markers and markers[1]==markers[2]:
            return paid, ''
        if result[1]=='PARTIAL' and re.search(r'RETENTION RELEASE|LIBERACION|SETTLEMENT|SALDO|REMAINDER|RESTBETRAG',tx):
            return paid, ''
        if result[1]=='PARTIAL' and facts.get('tranches') and abs(paid-facts['tranches'][-1])<=1:
            due = self.c.metadata.get(item['iid'],{}).get('due_date')
            count = len(facts['tranches'])
            if due and (date.fromisoformat(t['booking_date'])-date.fromisoformat(due)).days >= 30*(count-1)-3:
                return paid, ''
        return result

    def structured(self, t):
        result = super().structured(t)
        if result:
            return result
        ret = is_return(t)
        proposals = []
        for g in self.sources.candidates(t):
            if g.account and g.account!=t['account_id'] or not g.account and g.entity!=t['entity']:
                continue
            if g.kind in ('receipt','cheque') and not ret:
                continue
            if not ret and (g.cash<0)!=(cents(t['amount'])<0):
                continue
            if not self.cash_matches(t,g.currency or t['currency'],g.cash):
                continue
            group = {}
            for e in g.entries:
                i = self.resolve_entry(e,g,t)
                if i:
                    a,x = self.policy(i,e['paid'],t,e.get('reason',''),ret)
                    if i['iid'] in group:
                        old = group[i['iid']]
                        group[i['iid']] = (old[0],min(i['total'],old[1]+a),x)
                    else:
                        group[i['iid']] = (i['iid'],a,x)
            if group:
                proposals.append((len(group)/len(g.entries),len(group),g.key,list(group.values()),g.source))
        if proposals:
            best = sorted(proposals,key=lambda p:(-p[0],-p[1],p[2]))[0]
            return best[3], {'method':'v3:partial_container','group':best[2],'source':best[4],'resolved_fraction':best[0]}

    def reference_match(self,t):
        tx=text_of(t); booking=t['booking_date']; ret=is_return(t)
        side='AR' if cents(t['amount'])>0 else 'AP'
        if ret:
            side='AP' if side=='AR' else 'AR'
        parties=self.c.identify(t.get('counterparty_name',''),entity=t['entity'],side=side,iban=t.get('counterparty_account',''))
        if not parties:
            parties=self.c.identify(tx,entity=t['entity'],side=side,iban=t.get('counterparty_account',''))
        if ret:
            for mandate in re.findall(r'VTM[- ]?[A-Z]{2}[- ]?\d+',plain(tx)):
                parties.update(self.c.mandates.get(norm(mandate),()))
        pool=self.c.by_party(parties,booking) if parties else []
        pool=[i for i in pool if not json.loads(i['facts']).get('cancelled')]
        if ret:
            exact=[i for i in pool if self.cash_matches(t,i['currency'],i['total']) and not i['iid'].startswith(('ARC','APC'))]
            if exact:
                i=sorted(exact,key=lambda i:(-int(i['balance']==0),i['issue'],i['iid']))[0]
                return [(i['iid'],i['total'],'RETURNED')],{'method':'v3:mandate_return'}
        ts=tokens(tx)
        hits={}
        for token in ts:
            for i in self.c.lookup(token,entity=t['entity'],parties=parties,booking=booking):
                if i['side']==side:
                    hits[i['iid']]=i
        strong_hits=dict(hits)
        # Broader party-scoped prefix and suffix retrieval for truncated printed references.
        for i in pool:
            doc=norm(i['doc']); digits=''.join(re.findall(r'\d',doc))
            if any((len(k)>=5 and (doc.startswith(k) or doc.endswith(k) or digits.endswith(k))) for k in ts):
                hits[i['iid']]=i
        inv=[i for i in hits.values() if not i['iid'].startswith(('ARC','APC')) and i['balance']>0]
        credits={i['iid']:i for i in hits.values() if i['iid'].startswith(('ARC','APC')) and i['balance']>0}
        for i in inv:
            for cid in self.c.related.get((i['entity'],norm(i['doc'])),()):
                c=self.c.item(cid)
                if c and c['balance']>0 and c['issue']<=booking and c['currency']==i['currency']:
                    credits[cid]=c
        if inv:
            for include_credits in (True,False):
                group=inv+list(credits.values()) if include_credits else inv
                if len({i['currency'] for i in group})==1:
                    net=sum((-1 if i['iid'].startswith(('ARC','APC')) else 1)*i['balance'] for i in group)
                    if self.cash_matches(t,group[0]['currency'],net):
                        return [(i['iid'],*self.policy(i,i['balance'],t,force_return=ret)) for i in group],{'method':'v3:reference_group','items':len(group)}
        baseline=super().reference_match(t)
        if baseline and not any(r[2]=='OVERPAYMENT' for r in baseline[0]):
            return baseline
        # Complete an explicitly referenced set with a small residual, inside its party scope.
        anchors=[i for i in inv if i['iid'] in strong_hits and i['currency']==t['currency']]
        if anchors and not ret:
            anchor_parties={i['party'] for i in anchors}
            anchor_ids={i['iid'] for i in anchors}
            related=[i for i in credits.values() if i['party'] in anchor_parties and i['currency']==t['currency']]
            for cn in (related,[]):
                net=sum(i['balance'] for i in anchors)-sum(i['balance'] for i in cn)
                residual=abs(cents(t['amount']))-net
                candidates=[i for i in pool if i['iid'] not in anchor_ids and i['party'] in anchor_parties
                            and i['currency']==t['currency'] and 0<i['balance']<=residual and not i['iid'].startswith(('ARC','APC'))]
                if residual>0 and len(candidates)<=60:
                    added=self.small_residual(candidates,residual)
                    if added:
                        group=anchors+added+cn
                        return [(i['iid'],*self.policy(i,i['balance'],t)) for i in group],{'method':'v3:anchored_residual'}
        # Recover missing members through bounded same-party cash combinations.
        for pid in sorted(parties):
            candidates=[i for i in pool if i['party']==pid and i['balance']>0 and i['currency']==t['currency']
                        and not i['iid'].startswith(('ARC','APC'))]
            if 1<len(candidates)<=32:
                chosen=self.subset(candidates,abs(cents(t['amount'])))
                if chosen:
                    return [(i['iid'],*self.policy(i,i['balance'],t,force_return=ret)) for i in chosen],{'method':'v3:party_subset'}
        if baseline:
            # Credible individual allocations retain pair credit even when the group is incomplete.
            alloc,evidence=baseline
            certain=[i for i in inv if i['iid'] in strong_hits]
            if self.speculative and len(inv)>len(certain):
                alloc=[(i['iid'],*self.policy(i,i['balance'],t,force_return=ret)) for i in inv]
                evidence={'method':'v3:speculative_prefix','known_items':len(inv)}
            elif len(certain)>1:
                alloc=[(i['iid'],*self.policy(i,i['balance'],t,force_return=ret)) for i in certain]
                evidence={'method':'v3:incomplete_references','known_items':len(certain)}
            return alloc,evidence
        # Aggressive party-scoped single-item hypothesis, ranked by amount and clause compatibility.
        options=[]
        for i in pool:
            paid=self.item_cash(i,t)
            if paid is None or paid<=0 or i['iid'].startswith(('ARC','APC')):
                continue
            ratio=paid/max(i['balance'] or i['total'],1)
            facts=json.loads(i['facts'])
            if ratio>1.05 or ratio<0.1:
                continue
            a,x=self.policy(i,paid,t,force_return=ret)
            rank=100*(abs(paid-i['balance'])<=1)+50*(x in ('SHORT_DISCOUNT','SHORT_WITHHOLDING','SHORT_BANK_CHARGES'))
            rank+=25*bool(facts.get('tranches') or facts.get('retention') or facts.get('advance'))
            rank+=10*(i['iid'] in hits)+5*(i['balance']>0)
            options.append((rank,abs(1-ratio),i['issue'],i['iid'],a,x))
        if options:
            best=sorted(options,key=lambda p:(-p[0],p[1],p[2],p[3]))[0]
            return [(best[3],best[4],best[5])],{'method':'v3:party_ranked','rank':best[0]}
        certain=[i for i in inv if i['iid'] in strong_hits]
        if certain:
            return [(i['iid'],*self.policy(i,i['balance'],t,force_return=ret)) for i in certain],{'method':'v3:partial_reference_set'}
        if self.speculative and inv:
            return [(i['iid'],*self.policy(i,i['balance'],t,force_return=ret)) for i in inv],{'method':'v3:speculative_prefix'}

    @staticmethod
    def small_residual(items,target):
        by_amount=defaultdict(list)
        for i in items:
            by_amount[i['balance']].append(i)
        solutions=[]
        for i in items:
            if i['balance']==target:
                solutions.append([i])
        for a,i in enumerate(items):
            for j in by_amount.get(target-i['balance'],()):
                if i['iid']<j['iid']:
                    solutions.append([i,j])
            for j in items[a+1:]:
                for k in by_amount.get(target-i['balance']-j['balance'],()):
                    if j['iid']<k['iid'] and k['iid']!=i['iid']:
                        solutions.append([i,j,k])
        if solutions:
            return sorted(solutions,key=lambda sol:(len(sol),tuple(sorted(i['iid'] for i in sol))))[0]
