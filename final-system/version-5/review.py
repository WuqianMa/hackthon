"""Validate cached LLM choices and regenerate service-period fact candidates."""
from datetime import date
from decimal import Decimal
from bankrec.io import cents,money
from bankrec.engine import text_of
from recovery import service_period


def apply_decisions(predictions,packets,decisions,catalog):
    audit=[];seen=set()
    for d in decisions:
        tid=d['bank_txn_id']
        if tid in seen:raise ValueError('Duplicate LLM decision')
        seen.add(tid);p=packets[tid]
        if d.get('packet_sha256')!=p['packet_sha256']:raise ValueError('Stale LLM packet')
        action=d.get('action')
        if action not in ('KEEP','ABSTAIN','CHOOSE','EXTRACT_FACT') or not d.get('reason'):raise ValueError('Invalid LLM decision')
        before=predictions[tid];after=before;regenerated=False
        if action=='CHOOSE':
            choice=next((x for x in p['candidates'] if x['id']==d.get('candidate_id')),None)
            if choice is None:raise ValueError('Unknown LLM candidate')
            after=choice['rows']
        elif action=='EXTRACT_FACT':
            fact=d.get('fact',{});i=next((x for x in p['items'] if x['item_id']==fact.get('item_id')),None)
            if i is None or not fact.get('quote') or fact['quote'] not in i['cached_text']:raise ValueError('Unverifiable fact span')
            if fact.get('kind')!='service_period':raise ValueError('Only service_period fact regeneration is implemented')
            period=date.fromisoformat(fact['value']+'-01');bank=p['bank']
            if service_period(text_of(bank),bank['booking_date'])!=(period.year,period.month):raise ValueError('Fact does not match bank service period')
            source_period=service_period(fact['quote'],i['issue'])
            if source_period!=(period.year,period.month):raise ValueError('Fact period not established by source span')
            item=catalog.item(i['item_id']);amount=cents(i['balance_before'])
            cash=abs(cents(bank['amount'])) if item['currency']==bank['currency'] else abs(cents(bank.get('orig_amount'))) if item['currency']==bank.get('orig_currency') else None
            if amount<=0 or cash!=amount or amount>item['total']:raise ValueError('Regenerated period candidate has unsupported amount')
            after=[[tid,item['iid'],money(amount),'','FX_DIFFERENCE' if item['currency']!=bank['currency'] else '']];regenerated=True
        for r in after:
            if r[0]!=tid:raise ValueError('Cross-bank LLM choice')
            if r[1]:
                item=catalog.item(r[1])
                if not item or item['issue']>p['bank']['booking_date']:raise ValueError('Invalid LLM item/date')
                if cents(r[2])>item['total'] and r[4]!='DUPLICATE_PAYMENT':raise ValueError('LLM choice exceeds document total')
        predictions[tid]=after
        audit.append(dict(**d,changed=sorted(map(tuple,before))!=sorted(map(tuple,after)),regenerated=regenerated,before=before,after=after))
    return audit
