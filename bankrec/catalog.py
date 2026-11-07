from __future__ import annotations

from collections import defaultdict, Counter
from datetime import date
from functools import lru_cache
from pathlib import Path
import bisect
import json
import re
import sqlite3

from .io import cents, norm, plain, rows, table, pdf_text


def reference_keys(value):
    n = norm(value)
    if not n:
        return set()
    result = {n}
    d = "".join(re.findall(r"\d", n))
    if len(d) >= 5:
        result.add(d)
        result.add(d.lstrip("0"))
    # Bank references commonly omit the prefix/year and quote the last six digits.
    if len(d) >= 8:
        result.add(d[-6:])
        result.add(d[-6:].lstrip("0"))
    return {k for k in result if len(k) >= 5}


def tokens(text):
    text = plain(text).replace(" | ", "")
    return {norm(v) for v in re.findall(r"[A-Z0-9][A-Z0-9./_-]*", text) if len(norm(v)) >= 5}


class Catalog:
    def __init__(self, dbpath, phase, masters, pdf_cache, use_pdfs=True):
        self.phase, self.masters = Path(phase), Path(masters)
        self.db = sqlite3.connect(dbpath)
        self.db.row_factory = sqlite3.Row
        self.db.executescript("""
          PRAGMA journal_mode=WAL;
          CREATE TABLE items(iid TEXT PRIMARY KEY, entity TEXT, party TEXT, name TEXT,
              doc TEXT, issue TEXT, due TEXT, currency TEXT, total INTEGER, initial INTEGER,
              balance INTEGER, terms TEXT, side TEXT, method TEXT, facts TEXT);
          CREATE TABLE refs(ref TEXT, iid TEXT, kind TEXT, PRIMARY KEY(ref,iid,kind));
          CREATE INDEX refs_lookup ON refs(ref);
          CREATE INDEX items_party ON items(party,issue);
          CREATE INDEX items_amount ON items(entity,currency,total);
        """)
        self.aliases = defaultdict(set)
        self.ibans = defaultdict(set)
        self.word_names = defaultdict(set)
        self.names = {}
        self.party_info = {}
        self.terms = {r["code"]: r for r in rows(table(masters, "payment_terms"))}
        self.categories = {r["category"] for r in rows(table(masters, "categories"))}
        self.fx = defaultdict(list)
        for r in rows(table(masters, "fx_rates")):
            self.fx[r["currency"]].append((r["date"], r["units_per_eur"]))
        for key in self.fx:
            self.fx[key].sort()
        self.counts = Counter()
        for name, idcol in (("customers", "customer_id"), ("suppliers", "supplier_id")):
            for r in rows(table(masters, name)):
                pid = r[idcol]
                self.party_info[pid] = r
                self.add_name(pid, r["name"])
                self.add_name(pid, r.get("trade_name", ""))
                if r.get("iban"):
                    self.ibans[norm(r["iban"])].add(pid)
        for fname in ("ar_invoices", "ap_invoices", "credit_notes"):
            p = table(phase, fname)
            for r in rows(p):
                iid = r["item_id"]
                party = r.get("customer_id") or r.get("supplier_id") or r.get("party_id")
                name = r.get("customer_name") or r.get("supplier_name") or r.get("party_name") or ""
                doc = r.get("document_number") or r.get("supplier_invoice_number")
                total = cents(r["total_amount"])
                self.db.execute("INSERT INTO items VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    (iid, r["entity"], party, name, doc, r["issue_date"], r.get("due_date", ""),
                     r["currency"], total, total, total, r.get("payment_terms", ""), iid[:2],
                     r.get("payment_method", ""), "{}"))
                self.add_refs(iid, doc)
                for col in ("customer_po", "our_po"):
                    if r.get(col):
                        self.add_refs(iid, r[col], "po", exact=True)
                self.add_name(party, name)
                self.counts[fname] += 1
        opening = table(phase, "open_items_at_start", required=False)
        if phase.name in ("live", "final") and opening is None:
            raise ValueError("LIVE/FINAL requires an opening-items snapshot")
        if opening:
            for r in rows(opening):
                iid, amt = r["item_id"], cents(r["open_amount"])
                if self.db.execute("SELECT 1 FROM items WHERE iid=?", (iid,)).fetchone():
                    self.db.execute("UPDATE items SET initial=?,balance=? WHERE iid=?", (amt, amt, iid))
                else:
                    self.db.execute("INSERT INTO items VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                        (iid, r["entity"], r["party_id"], "", r["document_number"], r["issue_date"],
                         r.get("due_date", ""), r["currency"], cents(r["total_amount"]), amt, amt,
                         self.party_info.get(r["party_id"], {}).get("payment_terms", ""), iid[:2], "", "{}"))
                    self.add_refs(iid, r["document_number"])
                self.counts["opening_items"] += 1
        self.db.commit()
        if use_pdfs:
            self.load_facts(pdf_cache)

    def add_name(self, pid, name):
        key = norm(name)
        if len(key) < 5:
            return
        self.aliases[key].add(pid)
        self.names[key] = plain(name)
        for word in set(re.findall(r"[A-Z0-9]+", plain(name))):
            if len(word) >= 4:
                self.word_names[word].add(key)

    def add_refs(self, iid, ref, kind="document", exact=False):
        keys = {norm(ref)} if exact else reference_keys(ref)
        self.db.executemany("INSERT OR IGNORE INTO refs VALUES(?,?,?)", ((k, iid, kind) for k in keys if k))

    def load_facts(self, cache):
        index = table(self.phase / "pdfs", "index", required=False)
        if not index:
            return
        for r in rows(index):
            match = list(self.db.execute("SELECT i.* FROM items i JOIN refs r ON r.iid=i.iid "
                                        "WHERE r.ref=? AND i.entity=? AND i.party=?",
                                        (norm(r["document_number"]), r["entity"], r["party_id"])))
            if len(match) != 1:
                continue
            p = self.phase / "pdfs" / r["file"]
            tx = plain(pdf_text(p, cache))
            facts = {}
            if "VENCIMIENTOS" in tx or "INSTALMENT" in tx:
                facts["instalments"] = True
            if "RETENCION EN GARANTIA" in tx:
                facts["retention"] = True
            if "DEDUCIR ANTICIPO" in tx:
                facts["advance"] = True
            old = re.search(r"ANULA Y SUSTITUYE A LA FACTURA\s+([A-Z0-9/-]+)", tx)
            if old:
                facts["replaces"] = old[1]
                self.add_refs(match[0]["iid"], old[1], "replacement")
                for olditem in list(self.db.execute("SELECT i.iid,i.facts FROM items i JOIN refs r ON r.iid=i.iid "
                                     "WHERE r.ref=? AND i.entity=? AND i.party=? AND i.iid!=?",
                                     (norm(old[1]), r["entity"], r["party_id"], match[0]["iid"]))):
                    of = json.loads(olditem["facts"])
                    of["cancelled"] = True
                    self.db.execute("UPDATE items SET facts=? WHERE iid=?", (json.dumps(of), olditem["iid"]))
            month = re.search(r"(?:SERVICIO[S]?|MANTENIMIENTO)[^\n]*?(?:ENERO|FEBRERO|MARZO|ABRIL|MAYO|JUNIO|JULIO|AGOSTO|SEPTIEMBRE|OCTUBRE|NOVIEMBRE|DICIEMBRE|JANUARY|FEBRUARY|MARCH|APRIL|MAY|JUNE|JULY|AUGUST|SEPTEMBER|OCTOBER|NOVEMBER|DECEMBER)[^\n]*", tx)
            if month:
                facts["service_month"] = month[0]
            # Keep provenance, including clauses that this initial parser cannot yet interpret.
            facts["source"] = "pdfs/" + r["file"]
            prior = json.loads(match[0]["facts"])
            prior.update(facts)
            self.db.execute("UPDATE items SET facts=? WHERE iid=?", (json.dumps(prior), match[0]["iid"]))
            self.counts["pdfs_read"] += 1
        self.db.commit()

    def item(self, iid):
        r = self.db.execute("SELECT * FROM items WHERE iid=?", (iid,)).fetchone()
        return dict(r) if r else None

    def by_party(self, parties, booking):
        result = []
        for pid in sorted(parties):
            result.extend(dict(r) for r in self.db.execute("SELECT * FROM items WHERE party=? AND issue<=? ORDER BY issue,iid", (pid, booking)))
        return result

    def lookup(self, ref, entity=None, parties=None, side=None, booking="9999"):
        # Do not generate aliases of a bank token: a truncated reference must not become more ambiguous.
        keys = [norm(ref)]
        result = {}
        for k in keys:
            for r in self.db.execute("SELECT i.*,r.kind AS ref_kind FROM refs r JOIN items i ON i.iid=r.iid WHERE r.ref=?", (k,)):
                if entity and r["entity"] != entity:
                    continue
                if parties and r["party"] not in parties:
                    continue
                if side and r["side"] != side:
                    continue
                if r["issue"] > booking or json.loads(r["facts"]).get("cancelled"):
                    continue
                result[r["iid"]] = dict(r)
        return list(result.values())

    def identify(self, text, entity=None, side=None, iban=""):
        parties = set()
        for ib in re.findall(r"[A-Z]{2}\d{2}[A-Z0-9]{10,30}", plain(text)) + [norm(iban)]:
            parties.update(self.ibans.get(ib, set()))
        ptext, ntext = plain(text), norm(text)
        possible = set()
        for word in set(re.findall(r"[A-Z0-9]+", ptext)):
            possible.update(self.word_names.get(word, ()))
        matches = []
        for key in possible:
            if key in ntext:
                matches.append(key)
        # Longest complete aliases suppress shorter aliases contained in the same name.
        for key in sorted(matches, key=len, reverse=True):
            if not any(key != other and key in other for other in matches):
                parties.update(self.aliases[key])
        if entity:
            parties = {p for p in parties if self.party_info.get(p, {}).get("entity") == entity}
        if side:
            parties = {p for p in parties if p.startswith("C" if side == "AR" else "S")}
        return parties

    def rate(self, currency, booking):
        from decimal import Decimal
        if currency == "EUR":
            return Decimal(1)
        values = self.fx.get(currency, [])
        i = bisect.bisect_right(values, (booking, "zz")) - 1
        if i < 0:
            raise ValueError(f"no prior FX rate for {currency} at {booking}")
        return Decimal(values[i][1])

    def apply(self, iid, amount, exception):
        item = self.item(iid)
        if exception == "DUPLICATE_PAYMENT":
            return
        if exception == "RETURNED":
            balance = min(item["total"], item["balance"] + amount)
        else:
            balance = max(0, item["balance"] - amount)
        self.db.execute("UPDATE items SET balance=? WHERE iid=?", (balance, iid))
