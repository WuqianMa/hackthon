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

PAYMENT_FACTORY = {'ES00', 'ES01', 'ES02', 'PT01'}


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
        # related_document index: (entity, norm(related_doc)) → [credit_note_iid]
        self.related_credits = defaultdict(list)
        for filename in ['ar_invoices', 'ap_invoices', 'credit_notes']:
            for r in iter_csv(self.folder / (filename + '.csv.gz')):
                iid = r['item_id']
                r['kind'] = iid[:3]
                r['pid'] = r.get('customer_id', r.get('supplier_id', r.get('party_id')))
                r['number'] = norm(r.get('document_number', r.get('supplier_invoice_number')))
                r['total'] = cents(r['total_amount'])
                r['issued'] = day(r['issue_date'])
                r['balance'] = r['total']
                # Build related_document index for credit notes
                related = r.get('related_document', '')
                if related and r['kind'].endswith('C'):
                    self.related_credits[(r['entity'], norm(related))].append(iid)
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
        # Amount index: (entity, amount_cents) → [item_ids]
        self.by_entity_amount = defaultdict(list)
        for iid, item in self.items.items():
            if item['kind'].endswith('I'):
                self.by_entity_amount[(item['entity'], item['total'])].append(iid)
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
        self.confirming_runs = defaultdict(lambda: defaultdict(list))  # [account][run_id] -> [{e2e, amount, allocs}]
        self.used_confirming = set()
        # DD return cross-reference: (entity, mandate_norm, amount_cents) → [(collection_date, iid)]
        self.dd_collections = defaultdict(list)
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
            confirming_entries = defaultdict(list)  # (account, run_id) -> [rows]
            for path in sorted((self.folder / folder).glob('*.csv')):
                for r in read_csv(path):
                    if kind == 'ap' and r.get('run_type') == 'confirming':
                        confirming_entries[(r[account], r['run_id'])].append(r)
                        continue
                    groupkey = r[key]
                    if kind == 'ap' and r['run_type'] != 'transfers':
                        groupkey = r['run_id'] + ':' + r[dt]
                    groups[(r[account], groupkey)].append(r)
            # Process confirming runs: store per-e2e entries for subset matching
            for (acc, run_id), rs in confirming_entries.items():
                entity = self.account_entities[acc]
                search_entities = PAYMENT_FACTORY if entity == 'ES00' else {entity}
                for r in rs:
                    scores = {}
                    for fe in search_entities:
                        for p, s in self.party_scores(r['beneficiary'] + ' ' + r['beneficiary_iban'], fe, 'S').items():
                            scores[p] = max(scores.get(p, 0), s)
                    pid = max(scores, key=scores.get) if scores else None
                    amount = abs(cents(r['document_amount']))
                    doc_kinds = {'APC'} if cents(r['document_amount']) < 0 else {'API'}
                    iid = None
                    for fe in search_entities:
                        iid = self.resolve(r['document_number'], fe, doc_kinds, pid, amount)
                        if iid:
                            break
                    allocs = [(iid, amount)] if iid else []
                    self.confirming_runs[acc][run_id].append(dict(
                        e2e=r['end_to_end_id'], transfer_amount=cents(r['transfer_amount']),
                        currency=r['currency'], date=r[dt], allocations=allocs))
            for (acc, gid), rs in groups.items():
                entity = self.account_entities[acc]
                allocations = []
                for r in rs:
                    if kind == 'dd':
                        pid = self.mandates.get(norm(r['mandate_id']))
                        iid = self.resolve(r['remittance_info'], entity, {'ARI'}, pid, cents(r['amount']))
                        amount = cents(r['amount'])
                        # Build DD collection index for return cross-reference
                        if iid and r.get('mandate_id'):
                            self.dd_collections[(entity, norm(r['mandate_id']), amount)].append(
                                (r['collection_date'], iid))
                    elif kind == 'card':
                        ids = self.by_po.get((entity, norm(r['order_number'])), [])
                        iid = ids[0] if len(ids) == 1 else self.resolve(r['order_number'], entity, {'ARI'})
                        amount = cents(r['gross'])
                    elif kind == 'cheque':
                        iid = self.resolve(r['stub_reference'], entity, {'ARI'}, amount=cents(r['amount']))
                        amount = cents(r['amount'])
                    else:
                        # Payment factory: only ES00 pays invoices for ES01/ES02/PT01
                        search_entities = PAYMENT_FACTORY if entity == 'ES00' else {entity}
                        scores = {}
                        for fe in search_entities:
                            for p, s in self.party_scores(r['beneficiary'] + ' ' + r['beneficiary_iban'], fe, 'S').items():
                                scores[p] = max(scores.get(p, 0), s)
                        pid = max(scores, key=scores.get) if scores else None
                        amount = abs(cents(r['document_amount']))
                        kinds = {'APC'} if cents(r['document_amount']) < 0 else {'API'}
                        iid = None
                        for fe in search_entities:
                            iid = self.resolve(r['document_number'], fe, kinds, pid, amount)
                            if iid:
                                break
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
            if g['id'] in self.used_groups:
                continue
            # Accept partial batches if at least 50% of entries resolved
            if not g['rows']:
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
            # Bonus for complete batches and reference matches
            completeness = 5 if g['complete'] else 0
            score = 20 - delta + completeness + (15 if norm(g['id'].split(':')[0]) in compact else 0)
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

    def confirming_match(self, t, text):
        """Match confirming payment debits to subsets of a confirming run."""
        if cents(t['amount']) >= 0:
            return None
        wt = words(text)
        m = re.search(r'REMESA\s+(\S+)', wt)
        if not m:
            return None
        run_ref = norm(m[1])
        cash = abs(cents(t['amount']))
        # Find confirming runs on this account matching the ref
        runs = self.confirming_runs.get(t['account_id'], {})
        matched_run_id = None
        for rid, entries in runs.items():
            if norm(rid) == run_ref or run_ref in norm(rid) or norm(rid) in run_ref:
                matched_run_id = rid
                break
        if not matched_run_id:
            return None
        entries = runs[matched_run_id]
        # Filter out already-used entries
        available = [e for e in entries if e['e2e'] not in self.used_confirming]
        if not available:
            return None
        # Parse N PROVEEDORES if present
        nm = re.search(r'(\d+)\s+PROVEEDOR', wt)
        expected_n = int(nm[1]) if nm else None
        # Try to find subset of entries that sums to cash
        amounts = [e['transfer_amount'] for e in available]
        # For small N, try exact combinations
        max_n = expected_n or min(len(available), 8)
        best = None
        for n in (range(expected_n, expected_n + 1) if expected_n else range(1, max_n + 1)):
            if n > len(available):
                break
            if n <= 4 or (n <= 8 and len(available) <= 20):
                for combo in itertools.combinations(range(len(available)), n):
                    total = sum(amounts[i] for i in combo)
                    if abs(total - cash) <= 2:
                        best = combo
                        break
            if best:
                break
        if not best:
            # Fallback: try all entries if small enough
            if len(available) <= 20 and not expected_n:
                states = {0: ()}
                for idx, amt in enumerate(amounts):
                    for total, prefix in list(states.items()):
                        val = total + amt
                        if abs(val - cash) <= 2:
                            best = prefix + (idx,)
                            break
                        if val < cash + 2 and val not in states:
                            states[val] = prefix + (idx,)
                    if best:
                        break
        if not best:
            return None
        # Collect allocations from matched entries
        rows = []
        for idx in best:
            e = available[idx]
            self.used_confirming.add(e['e2e'])
            for iid, amt in e['allocations']:
                item = self.items[iid]
                exc = ''
                if item['currency'] != t['currency'] and item['kind'].endswith('I'):
                    exc = 'FX_DIFFERENCE'
                rows.append((iid, amt, exc))
        if not rows:
            return None
        return rows, 'confirming'

    def category(self, t, text):
        if t['bank_txn_id'] in self.reversal_ids:
            return 'BANK_REVERSAL'
        # ISO 20022 / bank_code structural signals (100% reliable)
        code = (t.get('bank_code', ''), t.get('bank_subcode', ''))
        if code in (('NCHG', ''), ('ACMT/MCOP/CHRG', ''), ('17', '310'), ('17', '701')):
            return 'BANK_FEES'
        if code == ('CAMT/ACCB/ZABA', ''):
            return 'CASH_POOL'
        if code == ('99', '622') or code == ('99', '867'):
            return 'CASH_POOL'
        w = words(text)
        patterns = [
            ('BANK_REVERSAL', r'ANULACION OPERACION INDEBIDA|BANK ERROR|ERRONEOUS|REVERSAL OF ERROR'),
            ('BANK_FEES', r'COMISION|COMISS|FRAIS|GEBUHR|BANK FEES|TRANSFER FEE|MAINTENANCE FEE|\bCOM (?:TRANSF|REMESA|DEVOL)|LIQUIDACION CTA|SERV EM TRANSF|GASTOS (?:TRANSF|CORRESPONSAL|TRANSFERENCIA)'),
            ('CASH_POOL', r'CASH POOL|CASH CONCENTRATION|SWEEP|ZBA|BARRIDO|NIVELACION|TRASPASO ENTRE CUENTAS|TRASPASO PROPIO'),
            ('CUSTOMER_ADVANCE', r'PROFORMA'),
            ('CUSTOMER_REFUND', r'REFUND DUPLICATE|DEVOLUCION COBRO DUPLICADO'),
            ('SUPPLIER_REFUND', r'REEMBOLSO'),
            ('INSURANCE', r'INSURANCE PREMIUM|PRIMA SEGURO|SEGUROS MULTIRRIESGO'),
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
        # LIQUIDACION INTERESES: same text for income vs expense, differentiated by amount sign
        if re.search(r'LIQUIDACION INTERESES', w):
            return 'INTEREST_INCOME' if cents(t['amount']) > 0 else 'INTEREST_EXPENSE'
        # Own-account identity distinguishes same-entity transfers from group financing.
        acct = norm(t.get('counterparty_account', ''))
        if acct:
            for r in self.accounts.values():
                if acct == norm(r['iban'] or r['account_number']):
                    return 'INTERNAL_TRANSFER' if r['entity'] == t['entity'] else 'INTERCOMPANY'
        return None

    def references(self, text, entity, kinds):
        entities = entity if isinstance(entity, set) else {entity}
        compact = norm(text)
        found = set()
        tokens = re.findall(r'[A-Z0-9][A-Z0-9/.-]*', unicodedata.normalize('NFKD', text.upper()))
        for token in tokens:
            key = norm(token)
            for ent in entities:
                for iid in self.by_number.get((ent, key), ()):
                    if self.items[iid]['kind'] in kinds:
                        found.add(self.replacements.get((ent, key), iid))
                if len(key) >= 5:
                    for iid in self.by_po.get((ent, key), ()):
                        if self.items[iid]['kind'] in kinds:
                            found.add(iid)
                if key.isdigit() and len(key) >= 6:
                    for iid in self.by_suffix.get((ent, key[-6:]), ()):
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

    def credit_payout_match(self, t, text):
        """Match credit note payouts: supplier refunds (APC settled by incoming)
        or customer credit notes paid out (ARC settled by outgoing transfer)."""
        cash = abs(cents(t['amount']))
        incoming = cents(t['amount']) > 0
        # Supplier refund: incoming payment settles an AP credit note (APC)
        # Customer credit payout: outgoing transfer settles an AR credit note (ARC)
        if incoming:
            kind = 'APC'
            side = 'S'
        else:
            kind = 'ARC'
            side = 'C'
        factory_ap = t['entity'] == 'ES00' and not incoming
        search_entities = PAYMENT_FACTORY if factory_ap else {t['entity']}
        if isinstance(search_entities, str):
            search_entities = {search_entities}
        ps = {}
        for ent in search_entities:
            for p, s in self.party_scores(text, ent, side).items():
                ps[p] = max(ps.get(p, 0), s)
        if not ps:
            return None
        # Find credit notes for identified parties
        credits = []
        for pid in ps:
            for iid in self.by_party.get(pid, []):
                item = self.items[iid]
                if item['kind'] != kind or item['balance'] <= 0:
                    continue
                expected = self.amount_for(item, t)
                if expected is not None and abs(expected - cash) <= max(2, cash * .03):
                    credits.append((iid, item))
        if not credits:
            return None
        # Prefer exact amount match, then closest
        exact = [(iid, item) for iid, item in credits if abs(self.amount_for(item, t) - cash) <= 2]
        if exact:
            iid, item = exact[0]
            exc = 'FX_DIFFERENCE' if item['currency'] != t['currency'] else ''
            return [(iid, item['balance'], exc)], 'credit_payout'
        if len(credits) == 1:
            iid, item = credits[0]
            exc = 'FX_DIFFERENCE' if item['currency'] != t['currency'] else ''
            return [(iid, item['balance'], exc)], 'credit_payout'
        return None

    def _prepare_generic(self, t, text):
        """Shared setup for generic matching: compute refs, party scores, candidate item ids."""
        cash = abs(cents(t['amount']))
        wt = words(text)
        returned = bool(re.search(r'DEVOLUCION RECIBO|DEVOL RECIBOS|RETURN|RUE?CKLAST|REJET|IMPAYE|CHARGEBACK|RETROCESION CONTRACARGO|DEVOLUCION TRANSFERENCIA', wt))
        incoming = cents(t['amount']) > 0
        factory_ap = t['entity'] == 'ES00' and not incoming and not returned
        if returned:
            kinds = {'API'} if incoming else {'ARI'}
        else:
            kinds = {'ARI', 'ARC', 'APC'} if incoming else {'API', 'APC', 'ARC'}
        search_entities = PAYMENT_FACTORY if factory_ap else t['entity']
        refs = self.references(text, search_entities, kinds)
        if factory_ap:
            ps = {}
            for fe in PAYMENT_FACTORY:
                for p, s in self.party_scores(text, fe, 'S').items():
                    ps[p] = max(ps.get(p, 0), s)
        else:
            ps = self.party_scores(text, t['entity'])
        if ps:
            best = max(ps.values())
            ps = {p: s for p, s in ps.items() if s >= max(5, best - 8)}
        for pid, score in list(ps.items()):
            for related in self.groups.get(self.parties.get(pid, {}).get('group_id', ''), ()):
                if related in self.by_party:
                    ps[related] = max(ps.get(related, 0), score - 1)
        ids = set(refs)
        for pid in ps:
            ids.update(self.by_party[pid])
        ids = {i for i in ids if self.items[i]['kind'] in kinds and self.items[i]['issued'] <= day(t['booking_date'])}
        if ps:
            refs = {i for i in refs if self.items[i]['pid'] in ps or self.items[i]['number'] in norm(text)}
        refids = sorted(i for i in refs if i in ids)
        ids = sorted(ids, key=lambda i: (-(ps.get(self.items[i]['pid'], 0) + (12 if i in refs else 0)), self.items[i]['issued'], i))
        amounts = {i: self.amount_for(self.items[i], t) for i in ids}
        amounts = {i: a for i, a in amounts.items() if a is not None}
        return cash, wt, returned, incoming, factory_ap, kinds, refs, ps, ids, refids, amounts

    def generic_match(self, t, text):
        """Original single-best generic match (used by Layer 1 for returns)."""
        prep = self._prepare_generic(t, text)
        if not prep:
            return None
        cash, wt, returned, incoming, factory_ap, kinds, refs, ps, ids, refids, amounts = prep
        if not ids:
            return None
        def normal_rows(chosen):
            return [(i, self.items[i]['balance'], 'FX_DIFFERENCE' if self.items[i]['currency'] != t['currency'] and self.items[i]['kind'].endswith('I') else '') for i in chosen]
        if returned:
            matches = [i for i in ids if abs(self.items[i]['total'] - cash) <= 2 and self.items[i]['currency'] == t['currency']]
            if matches:
                if len(matches) > 1:
                    mandate_pids = {pid for pid, sc in ps.items() if sc >= 22}
                    if mandate_pids:
                        for mandate_norm, pid in self.mandates.items():
                            if pid in mandate_pids:
                                entries = self.dd_collections.get((t['entity'], mandate_norm, cash), [])
                                if entries:
                                    entries_sorted = sorted(entries, key=lambda x: x[0], reverse=True)
                                    for coll_date, iid in entries_sorted:
                                        if iid in set(matches) and day(coll_date) <= day(t['booking_date']):
                                            return [(iid, cash, 'RETURNED')], 'return'
                                    for coll_date, iid in entries_sorted:
                                        if iid in set(matches):
                                            return [(iid, cash, 'RETURNED')], 'return'
                return [(matches[0], cash, 'RETURNED')], 'return'
            return None
        return None

    def generate_candidates(self, t, text):
        """Layer 2: generate all candidate matches with confidence scores.

        Returns list of (rows, score, method) tuples. Each 'rows' is a list of
        (item_id, amount, exception) triples. Score is a numeric confidence
        (higher = more confident). Multiple candidates may share items — Layer 3
        resolves conflicts.
        """
        prep = self._prepare_generic(t, text)
        if not prep:
            return []
        cash, wt, returned, incoming, factory_ap, kinds, refs, ps, ids, refids, amounts = prep
        if not ids or returned:
            return []
        candidates = []
        def normal_rows(chosen):
            return [(i, self.items[i]['balance'], 'FX_DIFFERENCE' if self.items[i]['currency'] != t['currency'] and self.items[i]['kind'].endswith('I') else '') for i in chosen]

        # --- Strategy 1: Complete references (score 80) ---
        if refids:
            r_refids = list(refids)
            if ps:
                known = [i for i in r_refids if self.items[i]['pid'] in ps]
                if known:
                    r_refids = known
            r_refids = [i for i in r_refids if self.items[i]['balance'] > 0]
            # Auto-include related credit notes via related_document index
            related_creds = set()
            for i in r_refids:
                item = self.items[i]
                if item['kind'].endswith('I'):
                    for cid in self.related_credits.get((item['entity'], item['number']), []):
                        if cid in ids and self.items[cid]['balance'] > 0:
                            related_creds.add(cid)
            all_refids = r_refids + [c for c in related_creds if c not in r_refids]
            signed = sum(amounts.get(i, 0) * (-1 if self.items[i]['kind'].endswith('C') else 1) for i in all_refids)
            if all_refids and abs(signed - cash) <= 2:
                candidates.append((normal_rows(all_refids), 80, 'references'))
            else:
                # Try without related credits
                signed_orig = sum(amounts.get(i, 0) * (-1 if self.items[i]['kind'].endswith('C') else 1) for i in r_refids)
                if r_refids and abs(signed_orig - cash) <= 2:
                    candidates.append((normal_rows(r_refids), 80, 'references'))
                elif r_refids and signed_orig > cash:
                    parties = {self.items[i]['pid'] for i in r_refids}
                    credits = [i for i in ids if i not in r_refids and self.items[i]['pid'] in parties and self.items[i]['kind'].endswith('C') and self.items[i]['balance'] > 0]
                    # Also include related credits
                    for i in r_refids:
                        item = self.items[i]
                        if item['kind'].endswith('I'):
                            for cid in self.related_credits.get((item['entity'], item['number']), []):
                                if self.items[cid]['balance'] > 0 and cid not in credits and cid not in r_refids:
                                    credits.append(cid)
                    chosen = self.subset(credits, signed_orig - cash, amounts)
                    if chosen:
                        candidates.append((normal_rows(r_refids + chosen), 75, 'netted_credit'))
                # Anchored residual: references found but don't sum to cash,
                # search same party's open items for the residual
                if r_refids and not any(m == 'references' or m == 'netted_credit' for _, _, m in candidates):
                    anchor_signed = sum(amounts.get(i, 0) * (-1 if self.items[i]['kind'].endswith('C') else 1) for i in r_refids)
                    residual = cash - anchor_signed
                    if 0 < residual < cash:
                        anchor_parties = {self.items[i]['pid'] for i in r_refids}
                        pool = [i for i in ids if i not in set(r_refids)
                                and self.items[i]['pid'] in anchor_parties
                                and self.items[i]['kind'].endswith('I')
                                and self.items[i]['balance'] > 0
                                and 0 < amounts.get(i, 0) <= residual]
                        chosen = self.subset(pool, residual, amounts)
                        if chosen:
                            candidates.append((normal_rows(r_refids + chosen), 72, 'anchored_residual'))

        # --- Strategy 2: Identity + exact amount (score 60) ---
        exact = [i for i in ids if amounts.get(i) == cash and (self.items[i]['pid'] in ps or i in refs)]
        if exact:
            months = ['JANUARY|JANVIER|ENERO|JANUAR', 'FEBRUARY|FEVRIER|FEBRERO|FEBRUAR', 'MARCH|MARS|MARZO|MARZ',
                      'APRIL|AVRIL|ABRIL', 'MAY|MAI|MAYO', 'JUNE|JUIN|JUNIO|JUNI', 'JULY|JUILLET|JULIO|JULI',
                      'AUGUST|AOUT|AGOSTO', 'SEPTEMBER|SEPTEMBRE|SEPTIEMBRE', 'OCTOBER|OCTOBRE|OCTUBRE|OKTOBER',
                      'NOVEMBER|NOVEMBRE|NOVIEMBRE', 'DECEMBER|DECEMBRE|DICIEMBRE|DEZEMBER']
            filtered = list(exact)
            for month, pattern in enumerate(months, 1):
                if re.search(r'\b(?:' + pattern + r')\b', wt):
                    dated = [i for i in exact if int(self.items[i]['issue_date'][5:7]) == month % 12 + 1]
                    if dated:
                        filtered = dated
                        break
            # Score boost if party identity is strong
            pid_score = ps.get(self.items[filtered[0]]['pid'], 0)
            s = 60 + min(pid_score, 10)
            candidates.append((normal_rows([filtered[0]]), s, 'identity_amount'))

        # --- Strategy 3: Discount / Withholding / FX / Bank charges (score 55) ---
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
                candidates.append(([(i, bal if timely else cash, 'SHORT_DISCOUNT' if timely else 'PARTIAL')], 55, 'discount'))
                break
            country = self.parties.get(item['pid'], {}).get('country')
            if country in {'MX', 'BR', 'MA'} and item['currency'] == t['currency']:
                if any(abs(cash - round(expected * (1 - p))) <= 2 for p in [.0125, .015, .1]):
                    candidates.append(([(i, bal, 'SHORT_WITHHOLDING')], 55, 'withholding'))
                    break
            if item['currency'] != t['currency'] and abs(expected - cash) <= expected * .03 and (i in refs or ps.get(item['pid'], 0) >= 8):
                candidates.append(([(i, bal, 'FX_DIFFERENCE')], 50, 'fx'))
                break
            # Use orig_amount/orig_currency for high-confidence FX matching
            orig_amt = t.get('orig_amount', '')
            orig_cur = t.get('orig_currency', '')
            if orig_amt and orig_cur and orig_cur != t['currency'] and item['currency'] == orig_cur:
                orig_cents = abs(cents(orig_amt))
                if abs(orig_cents - bal) <= max(2, bal * .005) and (i in refs or ps.get(item['pid'], 0) >= 5):
                    candidates.append(([(i, bal, 'FX_DIFFERENCE')], 65, 'fx_orig'))
                    break
            nonsepa = country in {'US', 'CA', 'MX', 'BR', 'MA', 'CN', 'AU', 'ZA'}
            if (re.search(r'CHGS|SHA|BEN|BANK CHARGES', wt) or nonsepa) and item['currency'] == t['currency'] and 0 < expected - cash <= min(6000, expected * .02):
                candidates.append(([(i, bal, 'SHORT_BANK_CHARGES')], 50, 'charges'))
                break
            pdf = self.meta.get(i, '')
            retention = re.search(r'(?:Retention|Retenci[oó]n)\s+(\d+)\s*%', pdf, re.I)
            if retention and item['currency'] == t['currency']:
                retained = round(item['total'] * int(retention[1]) / 100)
                if abs(cash - retained) <= 2:
                    candidates.append(([(i, cash, '')], 52, 'retention_release'))
                    break
                if abs(cash - (item['total'] - retained)) <= 2:
                    candidates.append(([(i, cash, 'PARTIAL')], 52, 'retention'))
                    break
            plan = re.search(r'(\d+)\s+instalments\s+at\s+([\d/]+)\s+days', pdf, re.I)
            if plan and item['currency'] == t['currency'] and abs(cash - item['total'] / int(plan[1])) <= 5:
                schedule = [int(x) for x in plan[2].split('/')]
                age = day(t['booking_date']) - item['issued']
                pos = min(range(len(schedule)), key=lambda x: abs(age - schedule[x]))
                candidates.append(([(i, cash, '' if pos == len(schedule) - 1 else 'PARTIAL')], 52, 'instalment_pdf'))
                break

        # --- Strategy 4: Party subset-sum (score 45) ---
        for pid in sorted(ps, key=lambda p: (-ps[p], p)):
            own = [i for i in ids if self.items[i]['pid'] == pid and self.items[i]['kind'].endswith('I') and self.items[i]['balance'] > 0]
            chosen = self.subset(own, cash, amounts)
            if chosen:
                pid_score = ps.get(pid, 0)
                candidates.append((normal_rows(chosen), 45 + min(pid_score, 10), 'party_subset'))
                break
            credits = [i for i in ids if self.items[i]['pid'] == pid and self.items[i]['kind'].endswith('C') and self.items[i]['balance'] > 0]
            found_net = False
            for credit in credits[:12]:
                chosen = self.subset(own, cash + amounts.get(credit, 0), amounts)
                if chosen:
                    candidates.append((normal_rows(chosen + [credit]), 42, 'party_net_subset'))
                    found_net = True
                    break
            if found_net:
                break
            for c1, c2 in itertools.combinations(credits[:10], 2):
                target = cash + amounts.get(c1, 0) + amounts.get(c2, 0)
                chosen = self.subset(own, target, amounts)
                if chosen:
                    candidates.append((normal_rows(chosen + [c1, c2]), 40, 'party_net_subset'))
                    found_net = True
                    break
            if found_net:
                break
            if len(credits) <= 8:
                for combo in itertools.combinations(credits, 3):
                    target = cash + sum(amounts.get(c, 0) for c in combo)
                    chosen = self.subset(own, target, amounts)
                    if chosen:
                        candidates.append((normal_rows(chosen + list(combo)), 38, 'party_net_subset'))
                        found_net = True
                        break
            if found_net:
                break

        # --- Strategy 5: Referenced partial / overpayment (score 35) ---
        if len(refids) == 1:
            i = refids[0]
            item = self.items[i]
            if item['currency'] == t['currency']:
                bal = item['balance']
                if bal > 0 and cash < bal:
                    exc = '' if re.search(r'SETTLEMENT|RETENTION RELEASE|\bREST\b|RESTO|SOLDE', wt) else 'PARTIAL'
                    instalment = re.search(r'(?:RATE|PLAZO|INSTALMENT|ECHEANCE)\s+(\d+)/(\d+)', text.upper())
                    if instalment and instalment[1] == instalment[2]:
                        exc = ''
                    candidates.append(([(i, cash, exc)], 35, 'referenced_partial'))
                if bal > 0 and cash <= bal * 1.1 and cash > bal:
                    candidates.append(([(i, bal, 'OVERPAYMENT')], 35, 'overpayment'))

        # --- Strategy 6: Duplicate payment (score 25) ---
        closed = [i for i in ids if self.items[i]['balance'] == 0 and abs(self.items[i]['total'] - cash) <= 2]
        if closed and (closed[0] in refs or ps.get(self.items[closed[0]]['pid'], 0) >= 8):
            candidates.append(([(closed[0], cash, 'DUPLICATE_PAYMENT')], 25, 'duplicate'))

        # --- Strategy 7: Amount-unique fallback (score 20) ---
        # When no party identified but only ONE open item in the entity has
        # this exact amount. Conservative constraints to avoid overfitting:
        # - same currency, exact amount
        # - amount has cents (not round hundreds/thousands — avoids fees/subscriptions)
        # - item issued before booking date, balance > 0
        # - no candidates found from stronger strategies
        if not candidates and not ps and not returned:
            if cash > 1000 and cash % 100 != 0:
                matches = [i for i in self.by_entity_amount.get((t['entity'], cash), [])
                           if self.items[i]['kind'] in kinds
                           and self.items[i]['balance'] > 0
                           and self.items[i]['currency'] == t['currency']
                           and self.items[i]['issued'] <= day(t['booking_date'])]
                if len(matches) == 1:
                    i = matches[0]
                    candidates.append(([(i, self.items[i]['balance'], '')], 20, 'amount_unique'))

        return candidates

    def _apply_match(self, t, rows, method, results, audit):
        """Apply a match result: consume balances, record output rows."""
        merged = {}
        for iid, amt, exc in rows:
            if iid in merged:
                old = merged[iid]
                merged[iid] = (old[0] + amt, exc or old[1])
            else:
                merged[iid] = (amt, exc)
        out_rows = []
        for iid, (amt, exc) in merged.items():
            out_rows.append((t['bank_txn_id'], iid, money(amt), '', exc))
            if exc == 'RETURNED':
                self.items[iid]['balance'] += amt
            elif exc != 'DUPLICATE_PAYMENT':
                self.items[iid]['balance'] = max(0, self.items[iid]['balance'] - amt)
        results[t['bank_txn_id']] = (out_rows, method)

    def run(self, out, trace):
        import time
        import resource
        from contextlib import ExitStack
        out = Path(out)
        out.parent.mkdir(parents=True, exist_ok=True)
        temp = out.with_name(out.name + '.partial')
        started = time.monotonic()

        results = {}  # bank_txn_id -> (out_rows, method)
        texts = {}    # bank_txn_id -> text

        # Precompute texts
        for t in self.transactions:
            texts[t['bank_txn_id']] = self.bank_text(t)

        # ============================================================
        # Layer 1: Strong evidence — batch, advice, confirming, returns
        # These are high-confidence matches that consume balances immediately.
        # ============================================================
        for n, t in enumerate(self.transactions, 1):
            text = texts[t['bank_txn_id']]
            match = None

            # Category-first for known non-item patterns (bank reversals, fees, etc.)
            cat = self.category(t, text)
            if cat:
                results[t['bank_txn_id']] = ([(t['bank_txn_id'], '', '', cat, 'UNIDENTIFIED' if cat == 'UNIDENTIFIED' else '')], 'category_' + cat)
                self.stats['L1_category_' + cat] += 1
                continue

            # Batch / advice / confirming — high-confidence structured evidence
            if self.full:
                match = self.batch_match(t, text) or self.advice_match(t, text) or self.confirming_match(t, text)
            if match:
                self._apply_match(t, match[0], 'L1_' + match[1], results, None)
                self.stats['L1_' + match[1]] += 1
                continue

            # Credit note payouts — supplier refunds / customer credit note paid out
            if self.full:
                cpayout = self.credit_payout_match(t, text)
                if cpayout:
                    self._apply_match(t, cpayout[0], 'L1_' + cpayout[1], results, None)
                    self.stats['L1_' + cpayout[1]] += 1
                    continue

            # Returns — unambiguous when cross-referenced with DD batches
            ret = self.generic_match(t, text)
            if ret:
                self._apply_match(t, ret[0], 'L1_' + ret[1], results, None)
                self.stats['L1_' + ret[1]] += 1
                continue

            if n % 5000 == 0:
                elapsed = time.monotonic() - started
                print(f'L1 PROGRESS {n}/{len(self.transactions)} date={t["booking_date"]} rate={n/max(elapsed,.001):.1f}/s', flush=True)

        layer1_count = len(results)
        print(f'LAYER 1 DONE: {layer1_count}/{len(self.transactions)} resolved', flush=True)

        # ============================================================
        # Layer 2+3: Candidate generation and resolution per transaction
        # Process in TRANSACTION TIME ORDER to preserve FIFO balance
        # consumption. For each transaction, generate all candidates,
        # pick the highest-scored one whose items are still available.
        # ============================================================
        l23_resolved = 0
        l23_unidentified = 0
        unresolved_count = 0
        for n, t in enumerate(self.transactions, 1):
            if t['bank_txn_id'] in results:
                continue
            unresolved_count += 1
            text = texts[t['bank_txn_id']]
            cands = self.generate_candidates(t, text)
            # Sort candidates by score descending
            cands.sort(key=lambda c: -c[1])
            assigned = False
            for rows, score, method in cands:
                # Check item availability
                ok = True
                for iid, amt, exc in rows:
                    item = self.items[iid]
                    if exc in ('DUPLICATE_PAYMENT', 'RETURNED'):
                        continue
                    if item['balance'] <= 0:
                        ok = False
                        break
                if not ok:
                    continue
                self._apply_match(t, rows, 'L3_' + method, results, None)
                self.stats['L3_' + method] += 1
                assigned = True
                l23_resolved += 1
                break
            if not assigned:
                results[t['bank_txn_id']] = ([(t['bank_txn_id'], '', '', 'UNIDENTIFIED', 'UNIDENTIFIED')], 'L3_unidentified')
                self.stats['L3_unidentified'] += 1
                l23_unidentified += 1
            if n % 5000 == 0:
                elapsed = time.monotonic() - started
                print(f'L2+3 PROGRESS {n}/{len(self.transactions)} date={t["booking_date"]} rate={n/max(elapsed,.001):.1f}/s', flush=True)

        print(f'LAYER 2+3 DONE: {l23_resolved} resolved, {l23_unidentified} unidentified (of {unresolved_count} unresolved)', flush=True)

        # ============================================================
        # Write output
        # ============================================================
        count = 0
        with ExitStack() as stack:
            op = gzip.open if out.suffix == '.gz' else open
            f = stack.enter_context(op(temp, 'wt', encoding='utf-8', newline=''))
            w = csv.writer(f, lineterminator='\n')
            w.writerow(['bank_txn_id', 'item_id', 'amount', 'category', 'exception'])
            audit = stack.enter_context(open(trace, 'w')) if trace else None
            for t in self.transactions:
                out_rows, method = results[t['bank_txn_id']]
                for row in out_rows:
                    w.writerow(row)
                    count += 1
                self.stats[method] = self.stats.get(method, 0)
                if audit:
                    audit.write(json.dumps({'bank_txn_id': t['bank_txn_id'], 'method': method}) + '\n')
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
