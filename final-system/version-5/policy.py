"""V5 item-currency amount/exception repair, without model fitting or state mutation.

Rules come from POLICIES.md sections 2, 3 and 5.  The model's item selection is
retained; evidence and the before-event ledger determine clearing semantics.
"""
from datetime import date
from decimal import Decimal, ROUND_HALF_UP
import json
import re

from bankrec.engine import text_of, is_return
from bankrec.io import cents, money, plain


PARTIAL_MARKER = re.compile(r"A CUENTA|PARTIAL|ON ACCOUNT|AKONTO|ACCONTO|TEILZAHL")
RELEASE_MARKER = re.compile(r"RETENTION RELEASE|RELEASE OF RETENTION|LIBERACION (?:DE )?(?:LA )?RETENCION|FINAL ACCEPTANCE|GARANTIA LIBERADA")
COMPLETION_MARKER = re.compile(r'\b(?:LIBERACION|SETTLEMENT|SALDO|REMAINDER|RESTBETRAG)\b')
TRANCHE_MARKER = re.compile(r"(?:RATE|PAGO|PAYMENT|PLAZO|INSTALMENT)\s*(\d+)\s*(?:/|DE|OF)\s*(\d+)")
SOURCE_METHODS = {
    'v3:partial_container', 'v3:reference_group', 'v3:anchored_residual',
    'v3:incomplete_references', 'v3:partial_reference_set',
    'references:single', 'references:netted',
}


def source_supported(method):
    """A source/reference explanation, not a purely ranked party guess."""
    return method.startswith('structured:') or method in SOURCE_METHODS


def facts_of(item):
    value=item.get('facts') or '{}'
    return value if isinstance(value,dict) else json.loads(value)


def item_cash(t,item):
    """Actual cash in item currency; never approximate a partial with reference FX."""
    if item['currency']==t['currency']:
        return abs(cents(t['amount']))
    if item['currency']==t.get('orig_currency') and t.get('orig_amount'):
        return abs(cents(t['orig_amount']))
    return None


def discount_status(t,item,catalog,paid):
    terms=catalog.terms.get(item.get('terms',''),{})
    pct=Decimal(str(terms.get('early_payment_discount_pct') or '0'))
    if not pct:return None
    expected=int((Decimal(item['total'])*(1-pct/100)).quantize(Decimal('1'),rounding=ROUND_HALF_UP))
    if abs(paid-expected)>1:return None
    age=(date.fromisoformat(t['booking_date'])-date.fromisoformat(item['issue'])).days
    return 'eligible' if age<=int(terms.get('discount_days') or 0)+3 else 'late'


def final_marker(tx,facts):
    if facts.get('retention') and RELEASE_MARKER.search(tx):return True
    for m in TRANCHE_MARKER.finditer(tx):
        number,count=map(int,m.groups())
        if count>=2 and number==count:
            tranches=facts.get('tranches')
            if not tranches or len(tranches)==count:return True
    return False


def _before(ledger,item):
    try:
        value=ledger.balance(item['iid'])
        reliable=bool(ledger.confident(item['iid']))
        if value is None:raise ValueError('unknown before-event balance')
        return int(value),reliable
    except (KeyError,TypeError,ValueError,AttributeError):
        return int(item.get('initial',item['total'])),False


def propose(t,current_rows,static_rows,catalog,ledger,static_method=''):
    """Return (new rows, reason) or None; never change item identity or caller state.

    `ledger.balance(iid)` and `ledger.confident(iid)` refer to the state before
    this bank event.  A static source row is cash evidence for a group only when
    the selected item set agrees; it is not copied across a changed allocation.
    """
    if not current_rows or any(not r[1] for r in current_rows):return None
    if sorted(map(tuple,current_rows))==sorted(map(tuple,static_rows)):return None
    if is_return(t) or any(r[4]=='RETURNED' for r in current_rows):return None
    current={r[1]:r for r in current_rows}
    static={r[1]:r for r in static_rows if r[1]}
    same_items=set(current)==set(static)
    supported=source_supported(static_method)
    tx=plain(text_of(t));result=[list(r) for r in current_rows];reasons=[]
    for row in result:
        iid=row[1]
        if iid.startswith(('ARC','APC')):continue
        item=catalog.item(iid)
        if not item or item['issue']>t['booking_date']:continue
        # Reverse-direction refunds/credit payouts belong to a separate mechanism.
        if (item['side']=='AR')!=(cents(t['amount'])>0):continue
        facts=facts_of(item);before,reliable=_before(ledger,item)
        reference=before if reliable else int(item.get('initial',item['total']))
        old=static.get(iid) if same_items else None
        paid=item_cash(t,item) if len(result)==1 else None
        if paid is None and old and supported and old[4] in ('PARTIAL','SHORT_DISPUTE','DUPLICATE_PAYMENT'):
            paid=cents(old[2])
        if paid is None or paid<=0:continue
        sensitive=bool(facts.get('retention') or facts.get('advance') or facts.get('tranches') or facts.get('instalments'))
        finish=final_marker(tx,facts) or bool(old and old[4]=='' and sensitive and supported and COMPLETION_MARKER.search(tx))
        marker=bool(PARTIAL_MARKER.search(tx))
        status=discount_status(t,item,catalog,paid)
        # A reliable exhausted ledger can establish a duplicate; keep the paid
        # cash amount even if it exceeds document total (POLICIES sections 2/3).
        if old and old[4]=='DUPLICATE_PAYMENT' and reliable and before<=0:
            desired=(paid,'DUPLICATE_PAYMENT');reason='duplicate_before_event_balance'
        elif reliable and before>0 and abs(paid-before)<=1 and (sensitive or row[4]=='PARTIAL' or (old and old[4]=='PARTIAL')):
            desired=(before,'FX_DIFFERENCE' if item['currency']!=t['currency'] else '')
            reason='remaining_balance_fully_paid'
        elif finish and old and old[4]=='' and sensitive:
            # A documented final-plan/release payment clears this cash amount,
            # not the opening invoice total when prior state is incomplete.
            desired=(paid,'FX_DIFFERENCE' if item['currency']!=t['currency'] else '')
            reason='documented_final_tranche_or_release'
        elif status=='eligible' and reference>0 and paid<reference:
            desired=(reference,'FX_DIFFERENCE' if item['currency']!=t['currency'] else 'SHORT_DISCOUNT')
            reason='eligible_discount_full_clearing'
        elif status=='late' and reference>paid+1 and not finish:
            desired=(paid,'PARTIAL');reason='late_discount_stays_open'
        elif sensitive and reference>paid+1 and not finish:
            desired=(paid,'PARTIAL');reason='document_plan_retention_or_advance'
        elif marker and reference>paid+1 and not finish:
            desired=(paid,'PARTIAL');reason='explicit_partial_cash'
        elif old and old[4]=='PARTIAL' and iid.startswith('API') and supported and reference>paid+1 and not finish:
            desired=(paid,'PARTIAL');reason='source_supported_ap_partial'
        else:
            continue
        if cents(row[2])!=desired[0] or row[4]!=desired[1]:
            row[2]=money(desired[0]);row[4]=desired[1];reasons.append(reason)
    if not reasons:return None
    return result,'policy:'+','.join(sorted(set(reasons)))
