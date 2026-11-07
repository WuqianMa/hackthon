from __future__ import annotations

from collections import defaultdict, Counter
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
import csv
import re

from .io import cents, norm, pdf_text, plain, rows, xlsx_rows, is_data_file
from .catalog import tokens


@dataclass
class Group:
    key: str
    kind: str
    source: str
    date: str
    currency: str
    cash: int
    account: str = ""
    entity: str = ""
    entries: list = field(default_factory=list)
    refs: set = field(default_factory=set)


class Sources:
    def __init__(self, phase, cache, use_pdfs=True):
        self.groups = {}
        self.by_ref = defaultdict(set)
        self.by_cash = defaultdict(set)
        self.counts, self.issues = Counter(), []
        self.load_batches(Path(phase))
        self.load_advices(Path(phase), cache, use_pdfs)
        for key, g in self.groups.items():
            for ref in g.refs | {g.key}:
                if len(norm(ref)) >= 5:
                    self.by_ref[norm(ref)].add(key)
            self.by_cash[(g.account, g.currency, g.cash)].add(key)

    def add(self, g):
        # Repeating a source record must never silently double an allocation.
        if g.key in self.groups:
            raise ValueError(f"duplicate source group {g.key}")
        self.groups[g.key] = g
        self.counts[g.kind] += 1

    def load_batches(self, phase):
        grouped = {}
        for kind in ["direct_debit_batches", "card_settlements", "cheque_deposits", "payment_runs"]:
            files = sorted(p for p in (phase / kind).glob("*.csv") if is_data_file(p))
            if not files:
                self.issues.append({"source": kind, "reason": "no structured source files present"})
            for f in files:
                for lineno, r in enumerate(rows(f), 2):
                    source = str(f.relative_to(phase))
                    e = {"source": source, "line": lineno, "reason": ""}
                    if kind == "direct_debit_batches":
                        gid, account, dt, curr = r["batch_id"], r["account_id"], r["collection_date"], r["currency"]
                        cash = cents(r["batch_total"])
                        e.update(doc=r["remittance_info"], paid=cents(r["amount"]),
                                 name=r["debtor_name"], iban=r["debtor_iban"], side="AR")
                        single_id = r["end_to_end_id"]
                        single = Group("receipt:" + account + ":" + single_id, "receipt", source, dt, curr, e["paid"],
                                       account, account.split("-")[0], [e.copy()], {single_id, r["mandate_id"]})
                        self.add(single)
                    elif kind == "card_settlements":
                        gid, account, dt, curr = r["settlement_id"], r["account_id"], r["settlement_date"], r["currency"]
                        cash = cents(r["net"])
                        e.update(doc=r["order_number"], paid=cents(r["gross"]), name="", iban="", side="AR")
                    elif kind == "cheque_deposits":
                        gid, account, dt, curr = r["deposit_id"], r["account_id"], r["deposit_date"], r["currency"]
                        cash = cents(r["deposit_total"])
                        e.update(doc=r["stub_reference"], paid=cents(r["amount"]), name=r["drawer"], iban="", side="AR")
                        single = Group("cheque:" + account + ":" + gid + ":" + r["cheque_number"], "cheque", source, dt, curr, e["paid"],
                                       account, account.split("-")[0], [e.copy()], {r["cheque_number"]})
                        self.add(single)
                    else:
                        account, dt, curr = r["debtor_account_id"], r["execution_date"], r["currency"]
                        gid = r["end_to_end_id"] if r["run_type"] == "transfers" else r["run_id"] + ":" + dt
                        cash = -cents(r["transfer_amount"])
                        e.update(doc=r["document_number"], paid=abs(cents(r["document_amount"])),
                                 name=r["beneficiary"], iban=r["beneficiary_iban"], side="AP",
                                 credit=cents(r["document_amount"]) < 0)
                    key = kind + ":" + account + ":" + gid
                    if key not in grouped:
                        grouped[key] = Group(key, kind, source, dt, curr, 0 if kind == "card_settlements" else cash,
                                             account, account.split("-")[0], [], {gid.split(":")[0]})
                    g = grouped[key]
                    if kind == "card_settlements":
                        g.cash += cash
                    elif kind == "payment_runs" and r["run_type"] != "transfers":
                        # transfer_amount repeats per beneficiary; document_amount is additive.
                        if not g.entries:
                            g.cash = 0
                        g.cash -= cents(r["document_amount"])
                    elif cash != g.cash:
                        raise ValueError(f"inconsistent batch totals in {source}:{lineno}")
                    g.entries.append(e)
                    if kind == "payment_runs":
                        g.refs.update({r["run_id"], r["end_to_end_id"]})
        for g in grouped.values():
            self.add(g)

    def load_advices(self, phase, cache, use_pdfs):
        folder = phase / "remittance_advices"
        index = folder / "index.csv"
        meta = {r["file"]: r for r in rows(index)} if index.exists() else {}
        for f in sorted(folder.rglob("*")):
            if not is_data_file(f) or f.suffix not in (".pdf", ".txt", ".xlsx", ".csv") or f == index:
                continue
            source = str(f.relative_to(phase))
            m = meta.get(str(f.relative_to(folder)), {})
            try:
                if f.suffix == ".csv":
                    with f.open(encoding="utf-8-sig", newline="") as fh:
                        first = fh.readline()
                        fh.seek(0)
                        allrows = list(csv.reader(fh, delimiter=";" if first.count(";") > first.count(",") else ","))
                    head = allrows[0]
                    if head[0] != "payment_ref":
                        raise ValueError("unknown advice CSV layout")
                    ref, dt, curr = head[1], head[3], head[5]
                    entries = self.tabular(allrows[1:])
                elif f.suffix == ".xlsx":
                    allrows = list(xlsx_rows(f))
                    ref, dt = allrows[1][1:3]
                    curr = ""  # The layout omits currency; resolve against the bank and every item.
                    entries = self.tabular(allrows[2:])
                else:
                    if f.suffix == ".pdf" and not use_pdfs:
                        self.issues.append({"source": source, "reason": "PDF extraction disabled"})
                        continue
                    tx = pdf_text(f, cache) if f.suffix == ".pdf" else f.read_text(encoding="utf-8-sig")
                    ref, dt, curr, entries = self.text_advice(tx)
                if not entries:
                    raise ValueError("no document rows parsed")
                entity = m.get("entity") or f.parent.name
                cash = sum((-1 if e.get("credit") else 1) * e["paid"] for e in entries)
                for e in entries:
                    e.update(source=source, name=m.get("payer_name", ""), iban="", side="AR")
                self.add(Group("advice:" + source, "remittance", source, dt, curr, cash,
                               "", entity, entries, {ref}))
            except (ValueError, KeyError, IndexError) as ex:
                self.issues.append({"source": source, "reason": str(ex)})

    @staticmethod
    def tabular(rs):
        headers = [plain(h).lower() for h in rs[0]]
        entries = []
        for vals in rs[1:]:
            if not vals or plain(vals[0]) in ("TOTAL", "", "DOCUMENT"):
                continue
            r = dict(zip(headers, vals))
            doc = r.get("document", "")
            gross = cents(r.get("gross"))
            paid = cents(r.get("paid"))
            entries.append({"doc": doc, "paid": abs(paid), "gross": abs(gross),
                            "credit": gross < 0, "reason": r.get("reason", "")})
        return entries

    @staticmethod
    def text_advice(tx):
        ref = re.search(r"(?:Payment ref\.|Payment advice|Aviso de pago|^Ref\.)\s*([^\s]+)", tx, re.I | re.M)
        if not ref:
            raise ValueError("payment reference not recognized")
        dt = re.search(r"\b(\d{4}-\d{2}-\d{2})\b", tx)
        if dt:
            dt = dt[1]
        elif re.search(r"on (\d{2}/\d{2}/\d{4})", tx):
            dt = datetime.strptime(re.search(r"on (\d{2}/\d{2}/\d{4})", tx)[1], "%m/%d/%Y").date().isoformat()
        else:
            m = re.search(r"\b\d{2}/\d{2}/\d{4}\b", tx)
            if not m:
                raise ValueError("payment date not recognized")
            dt = datetime.strptime(m[0], "%d/%m/%Y").date().isoformat()
        curr = re.search(r"\b(EUR|USD|GBP|PLN|MXN|BRL|MAD|CNY|CAD|AUD|CHF|ZAR)\b", tx)
        if not curr:
            raise ValueError("advice currency not recognized")
        # Native PDF text is one cell per line; mail advice is one document per line.
        amount_pattern = r"-?\d[\d.,]*[.,]\d{2}(?!\d)"
        def amount_value(s):
            if s.rfind(",") > s.rfind("."):
                s = s.replace(".", "").replace(",", ".")
            return cents(s)
        pat = re.compile(r"(?m)^\s*([A-Z0-9][A-Z0-9/-]{4,})\s+(\d{2}/\d{2}/\d{2,4})\s+(" + amount_pattern + ")")
        matches = list(pat.finditer(tx))
        entries = []
        for i, match in enumerate(matches):
            tail = tx[match.end():matches[i+1].start() if i+1 < len(matches) else len(tx)]
            tail = re.split(r"Documento sint|Kind regards|Saludos cordiales", tail)[0]
            amounts = re.findall(amount_pattern, tail)
            gross = amount_value(match[3])
            paid = amount_value(amounts[-1]) if amounts else gross
            reason = re.sub(r"[-\d,.\s]+", " ", tail).strip()
            if "Documento sint" in reason or "Kind regards" in reason:
                reason = ""
            entries.append({"doc": match[1], "paid": abs(paid), "gross": abs(gross),
                            "credit": gross < 0, "reason": reason if abs(paid) < abs(gross) else ""})
        return ref[1], dt, curr[1], entries

    def candidates(self, t):
        tx = " ".join(str(t.get(k, "")) for k in ("ref1", "ref2", "text", "end_to_end_id", "remittance_info"))
        keys = set()
        for token in tokens(tx):
            keys.update(self.by_ref.get(token, ()))
        curr = t.get("orig_currency") or t["currency"]
        cash = cents(t.get("orig_amount") or t["amount"])
        if cents(t["amount"]) < 0:
            cash = -abs(cash)
        for account in (t["account_id"], ""):
            keys.update(self.by_cash.get((account, curr, cash), ()))
        return [self.groups[k] for k in sorted(keys)]
