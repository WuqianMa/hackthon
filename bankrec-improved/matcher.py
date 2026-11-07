"""Evidence-based bank reconciliation. Prediction never reads golden labels.

Designed and evaluated on the bundled sample, not yet a full-scale production solver.
Amounts are integer cents; references and names are Unicode-normalized.
"""
from __future__ import annotations
import argparse
import bisect
import csv
import gzip
import hashlib
import itertools
import json
import math
import re
import unicodedata
from functools import lru_cache
from collections import Counter, defaultdict
from datetime import date, timedelta
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path


def iter_csv(path):
    path = Path(path)
    if not path.exists():
        return
    op = gzip.open if path.suffix == '.gz' else open
    with op(path, 'rt', encoding='utf-8-sig', newline='') as f:
        yield from csv.DictReader(f)


def read_csv(path):
    return list(iter_csv(path))


def cents(value):
    return int((Decimal(str(value or 0)) * 100).quantize(Decimal('1'), rounding=ROUND_HALF_UP))


def money(value):
    return f'{value / 100:.2f}'


def words(s):
    s = unicodedata.normalize('NFKD', str(s).upper())
    s = ''.join(c for c in s if not unicodedata.combining(c))
    return re.sub(r'[^A-Z0-9]+', ' ', s).strip()


def norm(s):
    return words(s).replace(' ', '')


def day(s):
    return date.fromisoformat(s[:10]).toordinal()


def parsed_money(s):
    s = str(s).strip().replace(' ', '').replace('\u00a0', '')
    if ',' in s and '.' in s:
        s = s.replace('.', '').replace(',', '.') if s.rfind(',') > s.rfind('.') else s.replace(',', '')
    elif ',' in s:
        s = s.replace(',', '.') if len(s.rsplit(',', 1)[1]) == 2 else s.replace(',', '')
    return cents(s)


STOP = set('SL SLU SA SAS SARL EURL GMBH CO KG AG EK LTD INC LLC BV SRL S L A U DE DEL LA EL Y ET AND THE GROUP PLUS'.split())


class Matcher:
    def __init__(self, root, phase='sample', mode='full', cache=None):
        self.root = Path(root)
        self.folder = self.root / phase
        self.mode = mode
        self.full = mode == 'full'
        self.cache = Path(cache) if cache else None
        self.items = {}
        self.by_number = defaultdict(list)
        self.by_suffix = defaultdict(list)
        self.by_party = defaultdict(list)
        self.by_po = defaultdict(list)
        self.parties = {}
        self.aliases = defaultdict(set)
        self.token_parties = defaultdict(set)
        self.bank_ids = defaultdict(set)
        self.mandates = {}
        self.groups = defaultdict(set)
        self.terms = {r['code']: r for r in read_csv(self.root / 'masters/payment_terms.csv')}
        self.accounts = {r['account_id']: r for r in read_csv(self.root / 'masters/bank_accounts.csv')}
        self.entities = {r['entity']: r for r in read_csv(self.root / 'masters/entities.csv')}
        self.categories = {r['category'] for r in read_csv(self.root / 'masters/categories.csv')}
        self.fx = defaultdict(list)
        for r in read_csv(self.root / 'masters/fx_rates.csv'):
            self.fx[r['currency']].append((r['date'], float(r['units_per_eur'])))
        for rates in self.fx.values():
            rates.sort()
        for filename, key in [('customers.csv', 'customer_id'), ('suppliers.csv', 'supplier_id')]:
            for r in read_csv(self.root / 'masters' / filename):
                pid = r[key]
                self.parties[pid] = r
                for name in [r['name'], r.get('trade_name', '')]:
                    if name:
                        self.aliases[pid].add(words(name))
                for field in ['iban', 'account_number']:
                    if r.get(field):
                        self.bank_ids[norm(r[field])].add(pid)
                if r.get('sepa_mandate_id'):
                    self.mandates[norm(r['sepa_mandate_id'])] = pid
                if r.get('group_id'):
                    self.groups[r['group_id']].add(pid)
        for filename in ['ar_invoices', 'ap_invoices', 'credit_notes']:
            for r in iter_csv(self.folder / (filename + '.csv.gz')):
                iid = r['item_id']
                r['kind'] = iid[:3]
                r['pid'] = r.get('customer_id', r.get('supplier_id', r.get('party_id')))
                r['number'] = norm(r.get('document_number', r.get('supplier_invoice_number')))
                r['total'] = cents(r['total_amount'])
                r['issued'] = day(r['issue_date'])
                r['balance'] = r['total']
                self.items[iid] = r
                self.by_number[(r['entity'], r['number'])].append(iid)
                digits = re.sub(r'\D', '', r['number'])
                if len(digits) >= 6:
                    self.by_suffix[(r['entity'], digits[-6:])].append(iid)
                self.by_party[r['pid']].append(iid)
                for field in ['customer_po', 'our_po']:
                    if r.get(field):
                        self.by_po[(r['entity'], norm(r[field]))].append(iid)
                name = r.get('customer_name', r.get('supplier_name', r.get('party_name')))
                if name:
                    self.aliases[r['pid']].add(words(name))
                # Keep only fields used during prediction, not raw descriptions/taxes.
                for field in list(r):
                    if field not in {'kind','pid','number','total','issued','balance','entity','currency','issue_date','payment_terms'}:
                        del r[field]
        for r in read_csv(self.folder / 'open_items_at_start.csv.gz'):
            if r['item_id'] in self.items:
                self.items[r['item_id']]['balance'] = cents(r['open_amount'])
        for pid in self.by_party:
            for alias in self.aliases[pid]:
                for token in set(alias.split()) - STOP:
                    if len(token) > 2:
                        self.token_parties[token].add(pid)
        self.entity_tokens = defaultdict(set)
        self.alias_features = defaultdict(list)
        self.alias_prefixes = defaultdict(set)
        self.alias_owners = defaultdict(set)
        self.alias_anchors = defaultdict(set)
        self.unanchored_parties = defaultdict(set)
        for token, pids in self.token_parties.items():
            for pid in pids:
                self.entity_tokens[(self.parties.get(pid, {}).get('entity'), token)].add(pid)
        for pid in self.by_party:
            for alias in self.aliases[pid]:
                ts = set(alias.split()) - STOP
                if ts:
                    weights = {tok: 1 / math.sqrt(max(1, len(self.token_parties[tok]))) for tok in ts}
                    total_weight = sum(weights.values())
                    ac = alias.replace(' ', '')
                    # Without a name bonus, coverage must reach 4.5/6 = 75%.
                    # Any token carrying >25% of weight must therefore be present.
                    required = {tok for tok, weight in weights.items() if weight > .250000001 * total_weight}
                    self.alias_features[pid].append((ac, ts, weights, total_weight, required))
                    entity = self.parties.get(pid, {}).get('entity')
                    # At least one token from any subset carrying >25% of
                    # weight must occur. This also handles long names where
                    # no individual token alone has >25% weight.
                    anchor_weight = 0
                    for anchor in sorted(ts, key=lambda tok: (-weights[tok], tok)):
                        self.alias_anchors[(entity, anchor)].add(pid)
                        anchor_weight += weights[anchor]
                        if anchor_weight > .250000001 * total_weight:
                            break
                    if len(ac) >= 8:
                        self.alias_prefixes[(entity, ac[:8])].add(ac)
                        self.alias_owners[(entity, ac)].add(pid)
        self.transactions = sorted(read_csv(self.folder / 'bank_transactions.csv.gz'), key=lambda r: (r['booking_date'], r['bank_txn_id']))
        # Historical accounts may be absent from the current masters snapshot.
        self.account_entities = {k: r['entity'] for k, r in self.accounts.items()}
        for t in self.transactions:
            previous = self.account_entities.setdefault(t['account_id'], t['entity'])
            if previous != t['entity']:
                raise ValueError(f"Conflicting entity for account {t['account_id']}")
        self.meta = {}
        self.replacements = {}
        self.groups_by_account = defaultdict(list)
        self.advice_by_entity = defaultdict(list)
        self.used_advice = set()
        self.used_groups = set()
        self.history = defaultdict(list)
        self.stats = Counter()
        self.warnings = []
        # An explicitly marked bank-error reversal also identifies its opposite leg.
        self.reversal_ids = set()
        by_account_amount = defaultdict(list)
        for t in self.transactions:
            by_account_amount[(t['account_id'], cents(t['amount']))].append(t)
        for t in self.transactions:
            if 'ANULACION OPERACION INDEBIDA' in words(t['text']):
                self.reversal_ids.add(t['bank_txn_id'])
                candidates = [r for r in by_account_amount[(t['account_id'], -cents(t['amount']))]
                              if 0 <= day(t['booking_date']) - day(r['booking_date']) <= 7]
                if len(candidates) == 1:
                    self.reversal_ids.add(candidates[0]['bank_txn_id'])
        if self.full:
            self.load_evidence()
        self.batch_index = self.make_amount_index(self.groups_by_account)
        self.advice_index = self.make_amount_index(self.advice_by_entity)

    @staticmethod
    def make_amount_index(groups):
        index = defaultdict(list)
        for owner, records in groups.items():
            for r in records:
                index[(owner, r['currency'])].append(r)
        return {k: (sorted(r['total'] for r in rs), sorted(rs, key=lambda r:r['total'])) for k,rs in index.items()}

    def amount_candidates(self, index, owner, cash, currency, dt, tolerance):
        for (key, cur), (values, records) in index.items():
            if key != owner:
                continue
            target = self.convert(cash, currency, cur, dt)
            if target is None:
                continue
            radius = tolerance if cur == currency else abs(target) * .032 + 3
            lo = bisect.bisect_left(values, target - radius)
            hi = bisect.bisect_right(values, target + radius)
            yield from records[lo:hi]

    def rate(self, currency, dt):
        if currency == 'EUR':
            return 1.0
        rates = self.fx.get(currency, [])
        ix = bisect.bisect_right(rates, (dt, float('inf'))) - 1
        return rates[ix][1] if ix >= 0 else None

    def convert(self, amount, source, target, dt):
        if source == target:
            return amount
        a, b = self.rate(source, dt), self.rate(target, dt)
        return round(amount / a * b) if a and b else None

    @lru_cache(maxsize=32768)
    def party_scores(self, text, entity, side=None):
        w = words(text)
        compact = w.replace(' ', '')
        tokens = set(w.split()) - STOP
        candidates = set()
        for tok in tokens:
            candidates.update(self.entity_tokens.get((entity, tok), ()))
        possible = set(self.unanchored_parties.get(entity, ()))
        for tok in tokens:
            possible.update(self.alias_anchors.get((entity, tok), ()))
        bonus = {}
        for prefix in {compact[i:i+8] for i in range(max(0, len(compact)-7))}:
            for ac in self.alias_prefixes.get((entity, prefix), ()):
                if ac in compact:
                    bonus[ac] = 8
                elif len(ac) >= 14 and ac[:min(25, len(ac))] in compact:
                    bonus[ac] = 5
                if ac in bonus:
                    possible.update(self.alias_owners[(entity, ac)])
        # Preserve iteration order: downstream equal-score ties use dict order.
        candidates = [pid for pid in candidates if pid in possible]
        scores = {}
        for pid in candidates:
            if pid not in self.by_party:
                continue
            pr = self.parties.get(pid, {})
            if pr.get('entity') != entity or (side and not pid.startswith(side)):
                continue
            best = 0
            for ac, ts, weights, total_weight, required in self.alias_features[pid]:
                name_bonus = bonus.get(ac, 0)
                if not name_bonus and not required <= tokens:
                    continue
                overlap = ts & tokens
                coverage = sum(weights[t] for t in overlap) / total_weight
                score = coverage * 6 + name_bonus
                if len(overlap) < 2 and len(ts) > 1 and coverage < .85:
                    score *= .5
                best = max(best, score)
            if best >= 4.5:
                scores[pid] = best
        for tok in w.split():
            for pid in self.bank_ids.get(tok, ()):
                if pid in self.by_party and (not side or pid.startswith(side)):
                    scores[pid] = max(scores.get(pid, 0), 20)
        # Mandates may be split by hyphens in the transaction text.
        for m in re.findall(r'VTM\s*[ -]\s*[A-Z]{2}\s*[ -]\s*\d+', str(text).upper()):
            pid = self.mandates.get(norm(m))
            if pid in self.by_party:
                scores[pid] = 22
        return scores

    def resolve(self, number, entity, kinds=None, pid=None, amount=None):
        key = norm(number)
        ids = list(self.by_number.get((entity, key), ()))
        if not ids:
            digs = re.sub(r'\D', '', key)
            if len(digs) >= 6:
                ids = list(self.by_suffix.get((entity, digs[-6:]), ()))
        if kinds:
            ids = [i for i in ids if self.items[i]['kind'] in kinds]
        if pid:
            own = [i for i in ids if self.items[i]['pid'] == pid]
            if own:
                ids = own
        if amount is not None and len(ids) > 1:
            exact = [i for i in ids if abs(self.items[i]['total'] - abs(amount)) <= 2]
            if exact:
                ids = exact
        return ids[0] if len(ids) == 1 else None

    def pdf_text(self, path):
        from pypdf import PdfReader
        if self.cache:
            key = hashlib.sha256(path.read_bytes()).hexdigest()
            dest = self.cache / (key + '.txt')
            if dest.exists():
                return dest.read_text()
        result = '\n'.join(p.extract_text(extraction_mode='layout') or '' for p in PdfReader(path).pages)
        if self.cache:
            self.cache.mkdir(parents=True, exist_ok=True)
            dest.write_text(result)
        return result

    def load_evidence(self):
        for r in read_csv(self.folder / 'pdfs/index.csv'):
            if r['document_type'] != 'invoice':
                continue
            iid = self.resolve(r['document_number'], r['entity'], {'ARI'}, r['party_id'])
            if not iid:
                continue
            text = self.pdf_text(self.folder / 'pdfs' / r['file'])
            self.meta[iid] = text
            m = re.search(r'(?:replaces invoice|sustituye (?:a )?(?:la )?factura)\s+([A-Z0-9/-]+)', text, re.I)
            if m:
                self.replacements[(r['entity'], norm(m[1]))] = iid
        for folder, key, account, dt, kind in [
            ('direct_debit_batches', 'batch_id', 'account_id', 'collection_date', 'dd'),
            ('card_settlements', 'settlement_id', 'account_id', 'settlement_date', 'card'),
            ('cheque_deposits', 'deposit_id', 'account_id', 'deposit_date', 'cheque'),
            ('payment_runs', 'end_to_end_id', 'debtor_account_id', 'execution_date', 'ap'),
        ]:
            groups = defaultdict(list)
            for path in sorted((self.folder / folder).glob('*.csv')):
                for r in read_csv(path):
                    groupkey = r[key]
                    if kind == 'ap' and r['run_type'] != 'transfers':
                        groupkey = r['run_id'] + ':' + r[dt]
                    groups[(r[account], groupkey)].append(r)
            for (acc, gid), rs in groups.items():
                entity = self.account_entities[acc]
                allocations = []
                for r in rs:
                    if kind == 'dd':
                        pid = self.mandates.get(norm(r['mandate_id']))
                        iid = self.resolve(r['remittance_info'], entity, {'ARI'}, pid, cents(r['amount']))
                        amount = cents(r['amount'])
                    elif kind == 'card':
                        ids = self.by_po.get((entity, norm(r['order_number'])), [])
                        iid = ids[0] if len(ids) == 1 else self.resolve(r['order_number'], entity, {'ARI'})
                        amount = cents(r['gross'])
                    elif kind == 'cheque':
                        iid = self.resolve(r['stub_reference'], entity, {'ARI'}, amount=cents(r['amount']))
                        amount = cents(r['amount'])
                    else:
                        scores = self.party_scores(r['beneficiary'] + ' ' + r['beneficiary_iban'], entity, 'S')
                        pid = max(scores, key=scores.get) if scores else None
                        amount = abs(cents(r['document_amount']))
                        kinds = {'APC'} if cents(r['document_amount']) < 0 else {'API'}
                        iid = self.resolve(r['document_number'], entity, kinds, pid, amount)
                    if iid:
                        allocations.append((iid, amount))
                if kind == 'dd':
                    total = cents(rs[0]['batch_total'])
                elif kind == 'card':
                    total = sum(cents(r['net']) for r in rs)
                elif kind == 'cheque':
                    total = cents(rs[0]['deposit_total'])
                else:
                    transfers = {r['end_to_end_id']: cents(r['transfer_amount']) for r in rs}
                    total = sum(transfers.values())
                self.groups_by_account[acc].append(dict(id=gid, kind=kind, date=rs[0][dt], currency=rs[0]['currency'], total=total,
                    rows=allocations, complete=len(allocations) == len(rs)))
        for index in read_csv(self.folder / 'remittance_advices/index.csv'):
            path = self.folder / 'remittance_advices' / index['file']
            records, ref, dt, currency = [], '', index['received_date'], 'EUR'
            try:
                if path.suffix == '.csv':
                    with path.open(newline='') as f:
                        content = f.read()
                    delimiter = ';' if content.splitlines()[0].count(';') > content.splitlines()[0].count(',') else ','
                    rr = list(csv.reader(content.splitlines(), delimiter=delimiter))
                    header = dict(zip(rr[0][::2], rr[0][1::2]))
                    ref, dt, currency = header.get('payment_ref', ''), header.get('payment_date', dt), header.get('currency', 'EUR')
                    for r in [dict(zip(rr[1], row)) for row in rr[2:]]:
                        if r.get('document', '').upper() not in ('', 'TOTAL'):
                            records.append((r['document'], parsed_money(r['gross']), parsed_money(r['paid']), r.get('reason', '')))
                elif path.suffix == '.xlsx':
                    from openpyxl import load_workbook
                    wb = load_workbook(path, read_only=True, data_only=True)
                    rr = list(wb.active.values)
                    wb.close()
                    ref, dt = str(rr[1][1]), str(rr[1][2])[:10]
                    for row in rr[3:]:
                        if row[0] and str(row[0]).upper() != 'TOTAL':
                            records.append((str(row[0]), cents(row[2]), cents(row[5]), str(row[4] or '')))
                else:
                    text = self.pdf_text(path) if path.suffix == '.pdf' else path.read_text()
                    m = re.search(r'(?:Payment ref\.|Subject:\s*Payment advice)\s+(\S+)', text, re.I)
                    ref = m[1] if m else ''
                    m = re.search(r'^Date\s+(\d{2})/(\d{2})/(\d{4})', text, re.M)
                    if m:
                        dt = f'{m[3]}-{m[2]}-{m[1]}'
                    m = re.search(r'\b(EUR|USD|GBP|CHF|PLN|MAD|AUD|CAD|BRL|MXN|CNY|ZAR)\b', text)
                    if m:
                        currency = m[1]
                    for line in text.splitlines():
                        m = re.match(r'^\s*([A-Z][A-Z0-9/-]+)\s+\d{2}/\d{2}/\d{2,4}\s+(.+)$', line)
                        if not m:
                            continue
                        nums = re.findall(r'-?\d[\d,.]*[.,]\d{2}(?!\d)', m[2])
                        if nums:
                            records.append((m[1], parsed_money(nums[0]), parsed_money(nums[-1]), m[2] if len(nums) > 2 else ''))
                alloc = []
                for number, gross, paid, reason in records:
                    iid = self.resolve(number, index['entity'], {'ARI', 'ARC'}, amount=abs(gross))
                    if iid:
                        exc = 'SHORT_DISPUTE' if reason and paid != gross and gross > 0 else ''
                        alloc.append((iid, abs(paid) if exc else abs(gross), exc))
                if alloc:
                    self.advice_by_entity[index['entity']].append(dict(id=index['file'], ref=norm(ref), date=dt, currency=currency,
                        total=sum(r[2] for r in records), rows=alloc, complete=len(alloc) == len(records), payer=index['payer_name']))
                elif records:
                    self.warnings.append(f'{path.name}: no unambiguous document matches')
            except (ValueError, KeyError, IndexError) as exc:
                self.warnings.append(f'{path.name}: {type(exc).__name__}: {exc}')

    def bank_text(self, t):
        return ' '.join(t.get(k, '') for k in ['text', 'ref1', 'ref2', 'remittance_info', 'counterparty_name', 'counterparty_account', 'end_to_end_id'])

    def batch_match(self, t, text):
        cash = abs(cents(t['amount']))
        compact = norm(text)
        candidates = []
        for g in self.amount_candidates(self.batch_index, t['account_id'], cash, t['currency'], t['booking_date'], 2):
            if g['id'] in self.used_groups or not g['complete']:
                continue
            if (g['kind'] == 'ap') != (cents(t['amount']) < 0):
                continue
            delta = abs(day(t['booking_date']) - day(g['date']))
            if delta > 7:
                continue
            expected = self.convert(g['total'], g['currency'], t['currency'], t['booking_date'])
            if expected is None:
                continue
            tol = 2 if g['currency'] == t['currency'] else max(2, expected * .03)
            if abs(cash - expected) > tol:
                continue
            score = 20 - delta + (15 if norm(g['id'].split(':')[0]) in compact else 0)
            candidates.append((score, g))
        if not candidates:
            return None
        candidates.sort(key=lambda x: (-x[0], x[1]['id']))
        if len(candidates) > 1 and candidates[0][0] == candidates[1][0]:
            return None
        g = candidates[0][1]
        self.used_groups.add(g['id'])
        rows = []
        for iid, amt in g['rows']:
            item = self.items[iid]
            exc = ''
            if amt < item['balance'] - 2 and item['kind'].endswith('I'):
                exc = 'PARTIAL'
            if item['currency'] != t['currency'] and item['kind'].endswith('I') and not exc:
                exc = 'FX_DIFFERENCE'
            rows.append((iid, amt, exc))
        return rows, 'batch_' + g['kind']

    def advice_match(self, t, text):
        if cents(t['amount']) <= 0:
            return None
        cash = cents(t['amount'])
        compact = norm(text)
        candidates = []
        for a in self.amount_candidates(self.advice_index, t['entity'], cash, t['currency'], t['booking_date'], 3):
            if a['id'] in self.used_advice or not a['complete']:
                continue
            delta = abs(day(t['booking_date']) - day(a['date']))
            if delta > 14:
                continue
            expected = self.convert(a['total'], a['currency'], t['currency'], t['booking_date'])
            if expected is None or abs(cash - expected) > (3 if a['currency'] == t['currency'] else expected * .03):
                continue
            refhit = len(a['ref']) >= 5 and a['ref'] in compact
            scores = self.party_scores(text, t['entity'], 'C')
            parties = {self.items[r[0]]['pid'] for r in a['rows']}
            identity = max([scores.get(p, 0) for p in parties] or [0])
            if not refhit and identity < 5:
                continue
            candidates.append((int(refhit) * 30 + identity - delta, a))
        if not candidates:
            return None
        candidates.sort(key=lambda x: (-x[0], x[1]['id']))
        if len(candidates) > 1 and candidates[0][0] == candidates[1][0]:
            return None
        a = candidates[0][1]
        self.used_advice.add(a['id'])
        rows = [(i, amt, ('FX_DIFFERENCE' if self.items[i]['currency'] != t['currency'] and self.items[i]['kind'] == 'ARI' and not e else e)) for i, amt, e in a['rows']]
        return rows, 'advice'

    def category(self, t, text):
        if t['bank_txn_id'] in self.reversal_ids:
            return 'BANK_REVERSAL'
        w = words(text)
        patterns = [
            ('BANK_REVERSAL', r'ANULACION OPERACION INDEBIDA|BANK ERROR|ERRONEOUS|REVERSAL OF ERROR'),
            ('BANK_FEES', r'COMISION|COMISS|FRAIS|GEBUHR|BANK FEES|TRANSFER FEE|MAINTENANCE FEE|\bCOM (?:TRANSF|REMESA|DEVOL)|LIQUIDACION CTA|SERV EM TRANSF|GASTOS (?:TRANSF|CORRESPONSAL|TRANSFERENCIA)'),
            ('CASH_POOL', r'CASH POOL|SWEEP|ZBA|BARRIDO|NIVELACION'),
            ('CUSTOMER_ADVANCE', r'PROFORMA'),
            ('CUSTOMER_REFUND', r'REFUND DUPLICATE|DEVOLUCION COBRO DUPLICADO'),
            ('SUPPLIER_REFUND', r'REEMBOLSO'),
            ('CARD_EXPENSES', r'ADEUDO MENSUAL DE TARJETA|CORPORATE CARD|CARTE ENTREPRISE'),
            ('LEASING', r'LEASING|ARRENDAMIENTO|RENTING'),
            ('LOAN_REPAYMENT', r'AMORTIZACION|LOAN REPAYMENT|CUOTA PRESTAMO'),
            ('LOAN_DRAWDOWN', r'DISPOSICION PRESTAMO|LOAN DRAWDOWN'),
            ('SOCIAL_SECURITY', r'SOCIAL CHARGES|SEG SOCIAL|SEGURIDAD SOCIAL|URSSAF'),
            ('TAX_REFUND', r'TAX REFUND|DEVOLUCION IMPUEST'),
            ('TAX_PAYMENT', r'TAX PAYMENT|IMPUEST|AEAT|HACIENDA|TVA'),
            ('PAYROLL', r'PAYROLL|NOMINAS|SALAIRES|GEHALT'),
            ('INTEREST_INCOME', r'INTEREST CREDIT|INTERESES A FAVOR|INTEREST INCOME|INTERETS CREDITEURS'),
            ('INTEREST_EXPENSE', r'INTEREST DEBIT|INTEREST EXPENSE|INTERESES DEUD|INTERETS DEBITEURS'),
            ('INTERCOMPANY', r'FINANCIACION IC|INTERCOMPANY|PRESTAMO IC'),
            ('INTERNAL_TRANSFER', r'TRASPASO|OWN ACCOUNT|VIREMENT INTERNE'),
            ('FX_DEAL', r'FX DEAL|FORWARD|COMPRAVENTA DIVISA'),
        ]
        for cat, pat in patterns:
            if re.search(pat, w):
                return cat
        # Own-account identity distinguishes same-entity transfers from group financing.
        acct = norm(t.get('counterparty_account', ''))
        if acct:
            for r in self.accounts.values():
                if acct == norm(r['iban'] or r['account_number']):
                    return 'INTERNAL_TRANSFER' if r['entity'] == t['entity'] else 'INTERCOMPANY'
        return None

    def references(self, text, entity, kinds):
        compact = norm(text)
        found = set()
        tokens = re.findall(r'[A-Z0-9][A-Z0-9/.-]*', unicodedata.normalize('NFKD', text.upper()))
        for token in tokens:
            key = norm(token)
            for iid in self.by_number.get((entity, key), ()):
                if self.items[iid]['kind'] in kinds:
                    found.add(self.replacements.get((entity, key), iid))
            if len(key) >= 5:
                for iid in self.by_po.get((entity, key), ()):
                    if self.items[iid]['kind'] in kinds:
                        found.add(iid)
            if key.isdigit() and len(key) >= 6:
                for iid in self.by_suffix.get((entity, key[-6:]), ()):
                    if self.items[iid]['kind'] in kinds:
                        found.add(iid)
        return found

    def amount_for(self, item, t):
        return self.convert(item['balance'], item['currency'], t['currency'], t['booking_date'])

    def subset(self, ids, target, amounts):
        # Bounded exact-cent search; never an unbounded subset-sum over all invoices.
        ids = [i for i in ids if 0 < amounts.get(i, 0) <= target]
        if len(ids) > 32:
            ids = sorted(ids, key=lambda i: (self.items[i]['issue_date'], i))[:32]
        lookup = defaultdict(list)
        for i in ids:
            lookup[amounts[i]].append(i)
        for count in [1, 2, 3]:
            for prefix in itertools.combinations(ids, count - 1):
                remain = target - sum(amounts[i] for i in prefix)
                for i in lookup.get(remain, ()):
                    if i not in prefix:
                        return list(prefix) + [i]
        if len(ids) <= 20:
            states = {0: ()}
            for i in ids:
                for total, prefix in list(states.items()):
                    val = total + amounts[i]
                    if val == target:
                        return list(prefix) + [i]
                    if val < target and val not in states:
                        states[val] = prefix + (i,)
                if len(states) > 50000:
                    break
        return None

    def generic_match(self, t, text):
        cash = abs(cents(t['amount']))
        wt = words(text)
        returned = bool(re.search(r'DEVOLUCION RECIBO|DEVOL RECIBOS|RETURN|RUE?CKLAST|REJET|IMPAYE|CHARGEBACK|DEVOLUCION TRANSFERENCIA', wt))
        incoming = cents(t['amount']) > 0
        if returned:
            kinds = {'API'} if incoming else {'ARI'}
        else:
            kinds = {'ARI', 'ARC', 'APC'} if incoming else {'API', 'APC', 'ARC'}
        refs = self.references(text, t['entity'], kinds)
        ps = self.party_scores(text, t['entity'])
        if ps:
            best = max(ps.values())
            ps = {p: s for p, s in ps.items() if s >= max(5, best - 8)}
        # A parent can settle subsidiaries' invoices.
        for pid, score in list(ps.items()):
            for related in self.groups.get(self.parties.get(pid, {}).get('group_id', ''), ()):
                if related in self.by_party:
                    ps[related] = max(ps.get(related, 0), score - 1)
        ids = set(refs)
        for pid in ps:
            ids.update(self.by_party[pid])
        ids = {i for i in ids if self.items[i]['kind'] in kinds and self.items[i]['issued'] <= day(t['booking_date'])}
        if not ids:
            return None
        if ps:
            refs = {i for i in refs if self.items[i]['pid'] in ps or self.items[i]['number'] in norm(text)}
        # Prefer explicit complete references; names can point to a parent or factor.
        refids = sorted(i for i in refs if i in ids)
        score = lambda i: (ps.get(self.items[i]['pid'], 0) + (12 if i in refs else 0), -self.items[i]['issued'])
        ids = sorted(ids, key=lambda i: (-score(i)[0], self.items[i]['issued'], i))
        if returned:
            matches = [i for i in ids if abs(self.items[i]['total'] - cash) <= 2 and self.items[i]['currency'] == t['currency']]
            if matches:
                return [(matches[0], cash, 'RETURNED')], 'return'
        amounts = {i: self.amount_for(self.items[i], t) for i in ids}
        amounts = {i: a for i, a in amounts.items() if a is not None}
        def normal_rows(chosen):
            return [(i, self.items[i]['balance'], 'FX_DIFFERENCE' if self.items[i]['currency'] != t['currency'] and self.items[i]['kind'].endswith('I') else '') for i in chosen]
        if refids:
            # Resolve repeated supplier numbers using identity before summing references.
            if ps:
                known = [i for i in refids if self.items[i]['pid'] in ps]
                if known:
                    refids = known
            refids = [i for i in refids if self.items[i]['balance'] > 0]
            signed = sum(amounts.get(i, 0) * (-1 if self.items[i]['kind'].endswith('C') else 1) for i in refids)
            if refids and abs(signed - cash) <= 2:
                return normal_rows(refids), 'references'
            # Referenced invoices may be paid net of unquoted credit notes.
            if refids and signed > cash:
                parties = {self.items[i]['pid'] for i in refids}
                credits = [i for i in ids if i not in refids and self.items[i]['pid'] in parties and self.items[i]['kind'].endswith('C') and self.items[i]['balance'] > 0]
                chosen = self.subset(credits, signed - cash, amounts)
                if chosen:
                    return normal_rows(refids + chosen), 'netted_credit'
        # Full amount + identity; FIFO disambiguates repeated maintenance amounts.
        exact = [i for i in ids if amounts.get(i) == cash and (self.items[i]['pid'] in ps or i in refs)]
        if exact:
            # Monthly maintenance is billed in the following month.
            months = ['JANUARY|JANVIER|ENERO|JANUAR', 'FEBRUARY|FEVRIER|FEBRERO|FEBRUAR', 'MARCH|MARS|MARZO|MARZ',
                      'APRIL|AVRIL|ABRIL', 'MAY|MAI|MAYO', 'JUNE|JUIN|JUNIO|JUNI', 'JULY|JUILLET|JULIO|JULI',
                      'AUGUST|AOUT|AGOSTO', 'SEPTEMBER|SEPTEMBRE|SEPTIEMBRE', 'OCTOBER|OCTOBRE|OCTUBRE|OKTOBER',
                      'NOVEMBER|NOVEMBRE|NOVIEMBRE', 'DECEMBER|DECEMBRE|DICIEMBRE|DEZEMBER']
            for month, pattern in enumerate(months, 1):
                if re.search(r'\b(?:' + pattern + r')\b', wt):
                    dated = [i for i in exact if int(self.items[i]['issue_date'][5:7]) == month % 12 + 1]
                    if dated:
                        exact = dated
                        break
            return normal_rows([exact[0]]), 'identity_amount'
        # Discount and withholding candidates are tested before partial allocation.
        for i in ids:
            item = self.items[i]
            bal = item['balance']
            expected = amounts.get(i, 0)
            if not expected or bal <= 0:
                continue
            term = self.terms.get(item.get('payment_terms', ''), {})
            pct = float(term.get('early_payment_discount_pct') or 0)
            if pct and item['currency'] == t['currency'] and abs(cash - (expected - round(expected * pct / 100))) <= 2:
                timely = day(t['booking_date']) <= item['issued'] + int(term['discount_days']) + 3
                return [(i, bal if timely else cash, 'SHORT_DISCOUNT' if timely else 'PARTIAL')], 'discount'
            country = self.parties.get(item['pid'], {}).get('country')
            if country in {'MX', 'BR', 'MA'} and item['currency'] == t['currency']:
                if any(abs(cash - round(expected * (1 - pct))) <= 2 for pct in [.0125, .015, .1]):
                    return [(i, bal, 'SHORT_WITHHOLDING')], 'withholding'
            if item['currency'] != t['currency'] and abs(expected - cash) <= expected * .03 and (i in refs or ps.get(item['pid'], 0) >= 8):
                return [(i, bal, 'FX_DIFFERENCE')], 'fx'
            nonsepa = country in {'US', 'CA', 'MX', 'BR', 'MA', 'CN', 'AU', 'ZA'}
            if (re.search(r'CHGS|SHA|BEN|BANK CHARGES', wt) or nonsepa) and item['currency'] == t['currency'] and 0 < expected - cash <= min(6000, expected * .02):
                return [(i, bal, 'SHORT_BANK_CHARGES')], 'charges'
            pdf = self.meta.get(i, '')
            # Only use explicit PDF terms to infer an unreferenced instalment/retention.
            retention = re.search(r'(?:Retention|Retenci[oó]n)\s+(\d+)\s*%', pdf, re.I)
            if retention and item['currency'] == t['currency']:
                retained = round(item['total'] * int(retention[1]) / 100)
                if abs(cash - retained) <= 2:
                    return [(i, cash, '')], 'retention_release'
                if abs(cash - (item['total'] - retained)) <= 2:
                    return [(i, cash, 'PARTIAL')], 'retention'
            plan = re.search(r'(\d+)\s+instalments\s+at\s+([\d/]+)\s+days', pdf, re.I)
            if plan and item['currency'] == t['currency'] and abs(cash - item['total'] / int(plan[1])) <= 5:
                schedule = [int(x) for x in plan[2].split('/')]
                age = day(t['booking_date']) - item['issued']
                pos = min(range(len(schedule)), key=lambda x: abs(age - schedule[x]))
                return [(i, cash, '' if pos == len(schedule) - 1 else 'PARTIAL')], 'instalment_pdf'
        # Payments without complete references: search only within identified parties.
        for pid in sorted(ps, key=lambda p: (-ps[p], p)):
            own = [i for i in ids if self.items[i]['pid'] == pid and self.items[i]['kind'].endswith('I') and self.items[i]['balance'] > 0]
            chosen = self.subset(own, cash, amounts)
            if chosen:
                return normal_rows(chosen), 'party_subset'
            credits = [i for i in ids if self.items[i]['pid'] == pid and self.items[i]['kind'].endswith('C') and self.items[i]['balance'] > 0]
            for credit in credits[:12]:
                chosen = self.subset(own, cash + amounts.get(credit, 0), amounts)
                if chosen:
                    return normal_rows(chosen + [credit]), 'party_net_subset'
        # A unique reference supports a partial payment or an overpayment.
        if len(refids) == 1:
            i = refids[0]
            item = self.items[i]
            if item['currency'] == t['currency']:
                bal = item['balance']
                if cash < bal:
                    exc = '' if re.search(r'SETTLEMENT|RETENTION RELEASE|\bREST\b|RESTO|SOLDE', wt) else 'PARTIAL'
                    instalment = re.search(r'(?:RATE|PLAZO|INSTALMENT|ECHEANCE)\s+(\d+)/(\d+)', text.upper())
                    if instalment and instalment[1] == instalment[2]:
                        exc = ''
                    return [(i, cash, exc)], 'referenced_partial'
                if bal > 0 and cash <= bal * 1.1:
                    return [(i, bal, 'OVERPAYMENT')], 'overpayment'
        closed = [i for i in ids if self.items[i]['balance'] == 0 and abs(self.items[i]['total'] - cash) <= 2]
        if closed and (closed[0] in refs or ps.get(self.items[closed[0]]['pid'], 0) >= 8):
            return [(closed[0], cash, 'DUPLICATE_PAYMENT')], 'duplicate'
        return None

    def run(self, out, trace):
        import time
        import resource
        from contextlib import ExitStack
        out = Path(out)
        out.parent.mkdir(parents=True, exist_ok=True)
        temp = out.with_name(out.name + '.partial')
        count = 0
        started = time.monotonic()
        with ExitStack() as stack:
            op = gzip.open if out.suffix == '.gz' else open
            f = stack.enter_context(op(temp, 'wt', encoding='utf-8', newline=''))
            w = csv.writer(f, lineterminator='\n')
            w.writerow(['bank_txn_id', 'item_id', 'amount', 'category', 'exception'])
            audit = stack.enter_context(open(trace, 'w')) if trace else None
            for n, t in enumerate(self.transactions, 1):
                text = self.bank_text(t)
                cat = self.category(t, text)
                match = None
                if cat is None and self.full:
                    match = self.batch_match(t, text) or self.advice_match(t, text)
                if cat is None and match is None:
                    match = self.generic_match(t, text)
                if match:
                    rows, method = match
                    merged = {}
                    for iid, amt, exc in rows:
                        if iid in merged:
                            old = merged[iid]
                            merged[iid] = (old[0] + amt, exc or old[1])
                        else:
                            merged[iid] = (amt, exc)
                    for iid, (amt, exc) in merged.items():
                        w.writerow([t['bank_txn_id'], iid, money(amt), '', exc])
                        count += 1
                        if exc == 'RETURNED':
                            self.items[iid]['balance'] += amt
                        elif exc != 'DUPLICATE_PAYMENT':
                            self.items[iid]['balance'] = max(0, self.items[iid]['balance'] - amt)
                else:
                    cat = cat or 'UNIDENTIFIED'
                    method = 'category_' + cat
                    w.writerow([t['bank_txn_id'], '', '', cat, 'UNIDENTIFIED' if cat == 'UNIDENTIFIED' else ''])
                    count += 1
                self.stats[method] += 1
                if audit:
                    audit.write(json.dumps({'bank_txn_id': t['bank_txn_id'], 'method': method}) + '\n')
                if n % 5000 == 0:
                    elapsed = time.monotonic() - started
                    print(f'PROGRESS {n}/{len(self.transactions)} date={t["booking_date"]} rate={n/max(elapsed,.001):.1f}/s', flush=True)
        temp.replace(out)
        summary = {'rows': count, 'transactions': len(self.transactions), 'methods': dict(self.stats),
                   'warnings': self.warnings, 'prediction_seconds': round(time.monotonic()-started, 2),
                   'max_rss_native': resource.getrusage(resource.RUSAGE_SELF).ru_maxrss}
        out.with_name(out.name + '.stats.json').write_text(json.dumps(summary, indent=2))
        print(json.dumps({**summary, 'warnings': self.warnings[:20], 'warning_count': len(self.warnings)}, indent=2), flush=True)
        return summary


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--data', default=str(Path(__file__).resolve().parent.parent / 'bankrec-docs-and-masters'))
    parser.add_argument('--phase', default='sample', choices=['sample'])
    parser.add_argument('--mode', default='full', choices=['masters', 'full'])
    parser.add_argument('--out', required=True)
    parser.add_argument('--trace')
    parser.add_argument('--cache', default='/tmp/bankrec-pdf-text-cache')
    args = parser.parse_args()
    matcher = Matcher(args.data, args.phase, args.mode, args.cache)
    matcher.run(args.out, args.trace)


if __name__ == '__main__':
    main()
