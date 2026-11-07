from collections import defaultdict
import json
import re

from bankrec.catalog import Catalog as BaseCatalog
from bankrec.io import rows, table, norm, plain, pdf_text, cents


class Catalog(BaseCatalog):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.prefixes = defaultdict(set)
        self.children = defaultdict(set)
        self.group_members = defaultdict(set)
        self.related = defaultdict(set)
        self.mandates = defaultdict(set)
        self.metadata = {}
        active = {r[0] for r in self.db.execute("SELECT DISTINCT party FROM items")}
        for pid, r in self.party_info.items():
            if r.get('sepa_mandate_id'):
                self.mandates[norm(r['sepa_mandate_id'])].add(pid)
            if r.get("parent_customer_id"):
                self.children[r["parent_customer_id"]].add(pid)
            if r.get("group_id"):
                self.group_members[r["group_id"]].add(pid)
        for alias, pids in self.aliases.items():
            eligible = pids & active
            if eligible:
                for length in range(8, min(len(alias), 40)+1):
                    self.prefixes[alias[:length]].update(eligible)
        for name in ("ar_invoices", "ap_invoices", "credit_notes"):
            for r in rows(table(self.phase, name)):
                self.metadata[r["item_id"]] = r
                if r.get("related_document"):
                    self.related[(r["entity"], norm(r["related_document"]))].add(r["item_id"])
        if kwargs.get("use_pdfs", args[4] if len(args)>4 else True):
            for r in rows(table(self.phase / "pdfs", "index")):
                found = self.lookup(r["document_number"], entity=r["entity"], parties={r["party_id"]})
                if len(found) != 1:
                    continue
                text = plain(pdf_text(self.phase / "pdfs" / r["file"], args[3]))
                facts = json.loads(found[0]["facts"])
                plan = re.search(r"(?:\d+ INSTALMENTS|\d+ VENCIMIENTOS)[^\n]*?\(([^)]+)\)", text)
                if plan:
                    amounts = re.findall(r"\d[\d.]*,\d{2}", plan[1])
                    facts["tranches"] = [cents(a.replace('.', '').replace(',', '.')) for a in amounts]
                month = re.search(r"(?:SERVICE|SERVICIO|MANTENIMIENTO|MAINTENANCE)[^\n]*(?:PERIOD|MONTH|MES|DE|:)[^\n]*", text)
                if month:
                    facts["service_clause"] = month[0]
                self.db.execute("UPDATE items SET facts=? WHERE iid=?", (json.dumps(facts), found[0]["iid"]))
        self.db.commit()

    def identify(self, text, entity=None, side=None, iban=""):
        parties = super().identify(text, entity, side, iban)
        if not parties and hasattr(self, "prefixes"):
            tx = plain(text)
            spans = [tx.split('|')[0]]
            spans += re.findall(r"/ORDP/([^/]+)|(?:TRANSFERENCIAS?|TRANSFER|ADEUDO|RECIBO)\s+([^|]+)", tx)
            strings = []
            for span in spans:
                strings.extend(span if isinstance(span, tuple) else [span])
            for span in strings:
                key = norm(re.sub(r"^(?:SEPA|TRANSFERENCIAS?|TRANSFER|ADEUDO|RECIBO)\s+", "", span.strip()))
                for length in range(min(len(key),40), 7, -1):
                    hit = self.prefixes.get(key[:length], set())
                    hit = {p for p in hit if (not entity or self.party_info.get(p,{}).get('entity')==entity)
                           and (not side or p.startswith('C' if side=='AR' else 'S'))}
                    if hit:
                        parties.update(sorted(hit)[:8])
                        break
        expanded = set(parties)
        for p in parties:
            expanded.update(self.children.get(p, ()))
            group = self.party_info.get(p,{}).get('group_id')
            if group:
                expanded.update(self.group_members[group])
        return expanded
