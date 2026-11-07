"""Targeted source/period/relationship recovery using existing read-only caches.

No learned weights, golden labels or PDF extraction are used. Monetary policy
for ambiguous partial/discount events remains with policy.py/the reviewer.
"""
from datetime import date
import itertools
import json
import re

from bankrec.engine import text_of, is_return
from bankrec.catalog import tokens
from bankrec.io import cents, money, norm, plain


MONTHS = {
    1: 'ENERO JANUARY JAN JANVIER JANUAR JANEIRO GENNAIO',
    2: 'FEBRERO FEBRUARY FEB FEVRIER FEBRUAR FEVEREIRO FEBBRAIO',
    3: 'MARZO MARCH MAR MARS MARZ MARCO',
    4: 'ABRIL APRIL APR AVRIL APRILE',
    5: 'MAYO MAY MAI MAIO MAGGIO',
    6: 'JUNIO JUNE JUN JUIN JUNI JUNHO GIUGNO',
    7: 'JULIO JULY JUL JUILLET JULI JULHO LUGLIO',
    8: 'AGOSTO AUGUST AUG AOUT',
    9: 'SEPTIEMBRE SEPTEMBER SEPT SEP SEPTEMBRE SETEMBRO SETTEMBRE',
    10: 'OCTUBRE OCTOBER OCT OCTOBRE OKTOBER OUTUBRO OTTOBRE',
    11: 'NOVIEMBRE NOVEMBER NOV NOVEMBRE NOVEMBRO',
    12: 'DICIEMBRE DECEMBER DEC DECEMBRE DEZEMBER DEZEMBRO DICEMBRE',
}
MONTH_LOOKUP = {word: number for number, names in MONTHS.items() for word in names.split()}
MONTH_PATTERN = re.compile(r'\b(' + '|'.join(sorted(MONTH_LOOKUP, key=lambda x: (-len(x), x))) + r')\b(?:\s*[./-]?\s*(20\d{2}|\d{2}))?')
SERVICE_MARKER = re.compile(r'MANT|MAINT|SERVIC|MONTH|MONAT|MANUTEN|PERIOD|PERIODO')


class _CatalogView:
    """Per-transaction read cache; never alters catalog state or item dictionaries."""
    def __init__(self, catalog):
        self.catalog = catalog; self.items = {}
    def __getattr__(self, name): return getattr(self.catalog, name)
    def item(self, iid):
        if iid not in self.items:self.items[iid] = self.catalog.item(iid)
        return self.items[iid]


def facts(item):
    value = item.get('facts') or '{}'
    return json.loads(value) if isinstance(value, str) else value


def service_period(text, reference):
    """Return the named month, inferring an omitted year as the latest past month."""
    match = MONTH_PATTERN.search(plain(text))
    if not match:
        return None
    month = MONTH_LOOKUP[match[1]]
    anchor = date.fromisoformat(reference)
    if match[2]:
        year = int(match[2]); year = year + 2000 if year < 100 else year
    else:
        year = anchor.year - (month > anchor.month)
    return year, month


def cash_in(t, currency):
    if currency == t['currency']:
        return abs(cents(t['amount']))
    if t.get('orig_currency') == currency and t.get('orig_amount'):
        return abs(cents(t['orig_amount']))
    return None


def balance(item, ledger):
    if ledger.confident(item['iid']):
        return max(0, min(item['total'], ledger.balance(item['iid'])))
    return max(0, min(item['total'], item['initial']))


def regular_row(t, item, amount):
    exception = 'FX_DIFFERENCE' if item['currency'] != t['currency'] and not item['iid'].startswith(('ARC', 'APC')) else ''
    return [t['bank_txn_id'], item['iid'], money(amount), '', exception]


def changed(proposed, current):
    return sorted(map(tuple, proposed)) != sorted(map(tuple, current))


def pool_category(t, catalog, ledger):
    accounts = getattr(catalog, 'bank_accounts', {})
    own = accounts.get(t.get('account_id'), {})
    purpose = plain(own.get('purpose', ''))
    if 'CASH POOL' not in purpose:
        return None
    tx = plain(text_of(t))
    # Observed ISO bank-family code is zero balancing, not a bank-fee code.
    code = (t.get('bank_code') or '').upper()
    scoped_zba = (t.get('bank') == 'RHEI' and t.get('statement_format') in ('camt053', 'camt.053')
                  and code == 'CAMT/ACCB/ZABA')
    paired = (not re.search(r'FINANCIACION|FINANCING|INTERCOMPANY|FUNDING|PRESTAMO|LOAN', tx)
              and getattr(ledger, 'cash_pool_pair', lambda _: False)(t))
    header_wording = 'CABECERA' in purpose and bool(re.search(r'CASH CONCENTRATION|ZERO BALANC|NIVELACION SALDO', tx))
    if scoped_zba or paired or header_wording:
        return [[t['bank_txn_id'], '', '', 'CASH_POOL', '']], 'recovery:cash_pool_account_code_or_pair'
    return None


def returned_operation(t, catalog, ledger):
    original = getattr(ledger, 'original_operation', lambda _: None)(t)
    if not original:
        return None
    if isinstance(original, dict):
        original = original.get('rows', [])
    result = []
    for row in original:
        if not row[1]:
            return None
        item = catalog.item(row[1])
        if not item or item['issue'] > t['booking_date']:
            return None
        amount = min(cents(row[2]), item['total'])
        if amount <= 0:
            return None
        result.append([t['bank_txn_id'], item['iid'], money(amount), '', 'RETURNED'])
    if result and len({r[1] for r in result}) == len(result):
        return result, 'recovery:linked_original_return'
    return None


def named_service_month(t, current, catalog, ledger):
    tx = plain(text_of(t))
    if not SERVICE_MARKER.search(tx):
        return None
    period = service_period(tx, t['booking_date'])
    if not period:
        return None
    side = 'AR' if cents(t['amount']) > 0 else 'AP'
    parties = catalog.identify(t.get('counterparty_name', '') or tx, entity=t['entity'], side=side,
                               iban=t.get('counterparty_account', ''))
    # An incumbent single-item identity supplies a party anchor for truncated formats.
    incumbent = [catalog.item(r[1]) for r in current if r[1]]
    if len(incumbent) == 1 and incumbent[0]:
        parties.add(incumbent[0]['party'])
    if not parties or len(parties) > 8:
        return None
    matches = []
    for item in catalog.by_party(parties, t['booking_date']):
        if item['side'] != side or item['iid'].startswith(('ARC', 'APC')):
            continue
        f = facts(item)
        clause = f.get('service_month') or f.get('service_clause')
        if not clause or f.get('cancelled') or service_period(clause, item['issue']) != period:
            continue
        amount = balance(item, ledger)
        if amount > 0 and cash_in(t, item['currency']) == amount:
            matches.append((item, amount))
        if len(matches) > 1:
            return None
    if len(matches) == 1:
        item, amount = matches[0]
        return [regular_row(t, item, amount)], 'recovery:cached_document_service_period'
    return None


def replaced_reference(t, current, catalog, ledger):
    tx = norm(text_of(t))
    seeds = {r[1]: catalog.item(r[1]) for r in current if r[1]}
    seeds = {iid: item for iid, item in seeds.items() if item}
    cancelled = [i for i in seeds.values() if facts(i).get('cancelled')]
    # Directly cited old numbers may resolve to a replacement through existing aliases.
    hits = {}
    for token in sorted(tokens(text_of(t))):
        for item in catalog.lookup(token, entity=t['entity'], booking=t['booking_date']):
            if facts(item).get('replaces'):
                hits[item['iid']] = item
    for old in cancelled:
        for item in catalog.lookup(old['doc'], entity=old['entity'], parties={old['party']}, booking=t['booking_date']):
            if facts(item).get('replaces'):
                hits[item['iid']] = item
    matches = []
    for item in hits.values():
        f = facts(item)
        if f.get('cancelled') or item['issue'] > t['booking_date']:
            continue
        old_number = norm(f['replaces'])
        cited = old_number in tx or any(norm(i['doc']) == old_number for i in cancelled)
        amount = balance(item, ledger)
        if cited and amount > 0 and cash_in(t, item['currency']) == amount:
            matches.append((item, amount))
    if len(matches) == 1:
        item, amount = matches[0]
        return [regular_row(t, item, amount)], 'recovery:replacement_reference'
    return None


def credit_netting(t, current, static, catalog, ledger):
    if not any(row[1] for row in current):
        return None
    # Do not turn a specifically explained deduction or duplicate into netting
    # merely because an unrelated credit happens to have the same amount.
    if any(r[4] in {'SHORT_DISCOUNT','SHORT_BANK_CHARGES','SHORT_WITHHOLDING',
                    'SHORT_DISPUTE','DUPLICATE_PAYMENT','RETURNED','FX_DIFFERENCE'} for r in current):
        return None
    all_solutions = {}
    for incumbent in (current, static):
        if not incumbent or not all(row[1] for row in incumbent) or len(incumbent) > 12:
            continue
        items = [catalog.item(row[1]) for row in incumbent]
        if any(not i or facts(i).get('cancelled') for i in items):
            continue
        invoices = [i for i in items if not i['iid'].startswith(('ARC', 'APC'))]
        fixed_credits = [i for i in items if i['iid'].startswith(('ARC', 'APC'))]
        if not invoices or len(invoices) > 8 or len({i['currency'] for i in items}) != 1:
            continue
        currency = items[0]['currency']; cash = cash_in(t, currency)
        if cash is None:
            continue
        amounts = {i['iid']: balance(i, ledger) for i in items}
        if any(value <= 0 for value in amounts.values()):
            continue
        deficit = sum(amounts[i['iid']] for i in invoices) - sum(amounts[i['iid']] for i in fixed_credits) - cash
        if deficit <= 0:
            continue
        fixed = {i['iid'] for i in fixed_credits}; options = {}
        for invoice in invoices:
            for iid in sorted(getattr(catalog, 'related', {}).get((invoice['entity'], norm(invoice['doc'])), ())):
                if iid in fixed:
                    continue
                item = catalog.item(iid)
                if (not item or not iid.startswith(('ARC', 'APC')) or item['issue'] > t['booking_date']
                        or item['currency'] != currency or item['party'] != invoice['party']
                        or item['side'] != invoice['side'] or facts(item).get('cancelled')):
                    continue
                reason = plain(getattr(catalog, 'metadata', {}).get(iid, {}).get('reason', ''))
                if re.search(r'ANULA|CANCEL|REPLAC', reason):
                    continue
                amount = balance(item, ledger)
                if 0 < amount <= deficit:
                    options[iid] = (item, amount)
        if not options or len(options) > 12:
            continue
        choices = []
        entries = sorted(options.values(), key=lambda x: x[0]['iid'])
        for size in range(1, min(4, len(entries)) + 1):
            for selected in itertools.combinations(entries, size):
                if sum(a for _, a in selected) == deficit:
                    choices.append(selected)
                    if len(choices) > 1:
                        break
            if len(choices) > 1:
                break
        if len(choices) != 1:
            continue
        selected = choices[0]
        result = [regular_row(t, i, amounts[i['iid']]) for i in invoices + fixed_credits]
        result.extend(regular_row(t, item, amount) for item, amount in selected)
        key = tuple(sorted(tuple(r) for r in result))
        all_solutions[key] = result
    if len(all_solutions) == 1:
        return next(iter(all_solutions.values())), 'recovery:related_credit_exact_net'
    return None


def propose(t, current_rows, static_rows, catalog, ledger, sources=None):
    """Return a changed source-supported decision, or leave the incumbent intact."""
    catalog = _CatalogView(catalog)
    proposed = pool_category(t, catalog, ledger)
    if proposed and changed(proposed[0], current_rows):
        return proposed
    if is_return(t):
        proposed = returned_operation(t, catalog, ledger)
        return proposed if proposed and changed(proposed[0], current_rows) else None
    proposed = named_service_month(t, current_rows, catalog, ledger)
    if proposed and changed(proposed[0], current_rows):
        return proposed
    # Replacement lookup is targeted at unresolved or explicitly cancelled matches.
    if not current_rows[0][1] or any(facts(catalog.item(r[1])).get('cancelled') for r in current_rows if r[1] and catalog.item(r[1])):
        proposed = replaced_reference(t, current_rows, catalog, ledger)
        if proposed and changed(proposed[0], current_rows):
            return proposed
    proposed = credit_netting(t, current_rows, static_rows, catalog, ledger)
    return proposed if proposed and changed(proposed[0], current_rows) else None
