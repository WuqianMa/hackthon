from __future__ import annotations

from collections import Counter, defaultdict
from datetime import date
from decimal import Decimal, ROUND_HALF_UP
import json
import re

from .catalog import tokens
from .io import cents, money, norm, plain


def text_of(t):
    return " ".join(t.get(k, "") for k in ("text", "ref1", "ref2", "counterparty_name",
                                            "counterparty_account", "end_to_end_id", "remittance_info"))


def is_return(t):
    return bool(re.search(r"DEVOLUCION (?:RECIBO|TRANSFERENCIA)|RETURN(?:ED)? (?:DD|DIRECT|PAYMENT)|"
                          r"CHEQUE IMPAYE|CHARGEBACK|RUECKLASTSCHRIFT|RETOUR IMPAYE", plain(text_of(t))))


def classify(t):
    """High precision narrative rules. Unmatched is an explicit review fallback."""
    tx, amt = plain(text_of(t)), cents(t["amount"])
    rules = [
        ("BANK_REVERSAL", r"ANULACION OPERACION INDEBIDA|ERROR BANCARIO|BANK ERROR|ERRONEOUS BOOKING"),
        ("CASH_POOL", r"ZBA|SWEEP|CASH.?POOL|BARRIDO|TRASPASO ENTRE CUENTAS ES00"),
        ("FX_DEAL", r"FX DEAL|FORWARD|COMPRA(?:VENTA)? (?:DE )?DIVISA|VENTA (?:DE )?DIVISA|CAMBIO DE DIVISA"),
        ("INTERCOMPANY", r"FINANCIACION IC|INTERCOMPANY|INTRAGRUPO|GROUP FUNDING|PRESTAMO IC|TRANSF\. IC"),
        ("INTERNAL_TRANSFER", r"TRASPASO (?:DE|ENTRE|A) CTA|OWN ACCOUNT|INTERNAL TRANSFER|VIREMENT INTERNE"),
        ("CUSTOMER_ADVANCE", r"PROFORMA|CUSTOMER ADVANCE"),
        ("LEASING", r"LEASING|ARRENDAMIENTO|CREDIT.BAIL|CUOTA RENTING|CUOTA LSG"),
        ("LOAN_REPAYMENT", r"AMORTIZACION DE PRESTAMO|LOAN REPAYMENT|CUOTA PRESTAMO|PRES\.[A-Z]{2}\d{2}-"),
        ("LOAN_DRAWDOWN", r"DISPOSICION (?:DE )?PRESTAMO|LOAN DRAWDOWN"),
        ("INSURANCE", r"PRIMA (?:DE )?SEGURO|INSURANCE PREMIUM"),
        ("CARD_EXPENSES", r"ADEUDO MENSUAL DE TARJETA|CORPORATE CARD|TARJETAS DE EMPRESA"),
        ("PAYROLL", r"NOMINAS|PAYROLL|SALAIRES|GEHALT"),
        ("SOCIAL_SECURITY", r"SEG\.? SOCIAL|SOCIAL CHARGES|SOCIAL SECURITY|URSSAF|SEGURIDAD SOCIAL"),
        ("TAX_REFUND", r"TAX REFUND|DEVOLUCION IMPUEST|DEVOLUCION AEAT"),
        ("TAX_PAYMENT", r"TAX PAYMENT|PAGO IMPUEST|AEAT|HACIENDA|VAT PAYMENT|VAT RETURN|IMPUESTOS MOD"),
        ("SUPPLIER_REFUND", r"REEMBOLSO|REFUND.*DUPLIC|DUPLIC.*REFUND"),
        ("BANK_FEES", r"COMISION|COMISS|GASTOS BANC|BANK FEE|FRAIS|ENTGELT|GEBUEHR|CHARGES TRANSFER|MAINTENANCE FEE|LIQUIDACION CTA\.CTO|COM\. TRANSF|SERV\. EM\. TRANSF"),
    ]
    if "INTERES" in tx or "INTEREST" in tx:
        return ("INTEREST_INCOME" if amt > 0 else "INTEREST_EXPENSE"), "", "narrative:interest"
    for category, pattern in rules:
        if re.search(pattern, tx):
            if category == "SUPPLIER_REFUND" and amt < 0:
                category = "CUSTOMER_REFUND"
            return category, "", "narrative:" + category
    return None


class Engine:
    def __init__(self, catalog, sources, providers=()):
        self.c, self.sources = catalog, sources
        self.providers = tuple(providers)
        self.stats = Counter()

    def extension_match(self, t):
        from .extensions import evidence_is_valid
        accepted = []
        for provider in self.providers:
            for candidate in provider.propose(dict(t), self.c):
                if candidate.bank_txn_id != t["bank_txn_id"] or not candidate.allocations:
                    continue
                if not evidence_is_valid(candidate.evidence, self.c.phase):
                    continue
                if candidate.returned and not is_return(t):
                    continue
                proposals, signed_cash, currency, seen = [], 0, None, set()
                for row in candidate.allocations:
                    i = self.c.item(row.item_id)
                    if not i or row.item_id in seen or type(row.paid_cents) is not int or row.paid_cents <= 0:
                        break
                    if i["issue"] > t["booking_date"] or json.loads(i["facts"]).get("cancelled"):
                        break
                    if currency is not None and i["currency"] != currency:
                        break
                    currency = i["currency"]
                    seen.add(row.item_id)
                    signed_cash += row.paid_cents * (1 if i["side"] == "AR" else -1) * (-1 if row.item_id.startswith(("ARC", "APC")) else 1)
                    proposals.append((row.item_id, *self.policy(i, row.paid_cents, t, row.deduction_reason, candidate.returned)))
                else:
                    if candidate.returned:
                        signed_cash = -signed_cash
                    if signed_cash * cents(t["amount"]) <= 0 or not self.cash_matches(t, currency, signed_cash):
                        continue
                    accepted.append((proposals, {"method": "extension:" + candidate.method,
                        "evidence": [e.__dict__ for e in candidate.evidence]}))
        if not accepted or any(a[0] != accepted[0][0] for a in accepted[1:]):
            return None
        return accepted[0]

    def policy(self, item, paid, t, reason="", force_return=False):
        """Return (cleared cents, exception). Full-clearing exceptions use open amount."""
        remaining = item["balance"]
        credit = item["iid"].startswith(("ARC", "APC"))
        if force_return:
            return paid, "RETURNED"
        if remaining <= 0:
            return paid, "DUPLICATE_PAYMENT"
        if abs(paid - remaining) <= 1:
            return remaining, "FX_DIFFERENCE" if item["currency"] != t["currency"] and not credit else ""
        if paid > remaining:
            # Structured partial rows can differ by a cent; larger excess is an overpayment.
            return remaining, "FX_DIFFERENCE" if item["currency"] != t["currency"] and not credit else "OVERPAYMENT"
        terms = self.c.terms.get(item["terms"], {})
        pct = terms.get("early_payment_discount_pct")
        if pct:
            days = (date.fromisoformat(t["booking_date"]) - date.fromisoformat(item["issue"])).days
            discounted = int((Decimal(item["total"]) * (1 - Decimal(pct)/100)).quantize(Decimal(1), rounding=ROUND_HALF_UP))
            if days <= int(terms["discount_days"]) + 3 and abs(paid - discounted) <= 1:
                return remaining, "FX_DIFFERENCE" if item["currency"] != t["currency"] else "SHORT_DISCOUNT"
        if reason.strip():
            return paid, "SHORT_DISPUTE"
        country = self.c.party_info.get(item["party"], {}).get("country", "")
        if country in {"MX", "BR", "MA"}:
            for pct in ("1.25", "1.5", "10"):
                expected = int((Decimal(item["total"]) * (1 - Decimal(pct)/100)).quantize(Decimal(1), rounding=ROUND_HALF_UP))
                if abs(paid-expected) <= 1:
                    return remaining, "FX_DIFFERENCE" if item["currency"] != t["currency"] else "SHORT_WITHHOLDING"
        # Fee deduction needs an explicit bank charge marker; amount similarity alone is insufficient.
        short = remaining-paid
        sepa = {"ES", "FR", "DE", "IT", "PT", "NL", "BE", "LU", "AT", "IE", "FI", "GR", "MT", "CY",
                "EE", "LV", "LT", "SI", "SK", "HR", "BG", "RO", "PL", "CZ", "HU", "SE", "DK", "GB", "CH", "NO", "IS", "LI", "MC", "SM", "AD", "VA"}
        if country and country not in sepa and re.search(r"CHGS|SHA|BEN|BANK CHARGE", plain(text_of(t))):
            eur = Decimal(short) / self.c.rate(item["currency"], t["booking_date"])
            if eur <= 6000 and short * 100 <= item["total"] * 2:
                return remaining, "FX_DIFFERENCE" if item["currency"] != t["currency"] else "SHORT_BANK_CHARGES"
        return paid, "PARTIAL"

    def cash_matches(self, t, currency, expected):
        """Exact currency cash, or reference FX within the documented 3% band."""
        if currency == t["currency"]:
            return abs(abs(cents(t["amount"])) - abs(expected)) <= 1
        if t.get("orig_currency") == currency and t.get("orig_amount"):
            return abs(abs(cents(t["orig_amount"])) - abs(expected)) <= 1
        converted = Decimal(abs(expected)) / self.c.rate(currency, t["booking_date"]) * self.c.rate(t["currency"], t["booking_date"])
        return abs(Decimal(abs(cents(t["amount"]))) - converted) <= converted * Decimal("0.03")

    def resolve_entry(self, entry, g, t):
        parties = self.c.identify(entry.get("name", "") + " " + entry.get("iban", ""),
                                  side=entry["side"], iban=entry.get("iban", ""))
        candidates = self.c.lookup(entry["doc"], parties=parties, side=entry["side"], booking=t["booking_date"])
        if not candidates:
            for token in tokens(entry["doc"]):
                candidates.extend(self.c.lookup(token, parties=parties, side=entry["side"], booking=t["booking_date"]))
        if not candidates and parties:
            candidates = [i for i in self.c.by_party(parties, t["booking_date"])
                          if i["currency"] == g.currency and i["balance"] == entry["paid"]]
        candidates = {i["iid"]: i for i in candidates}.values()
        good = []
        for i in candidates:
            if json.loads(i["facts"]).get("cancelled"):
                continue
            if "credit" in entry and (i["iid"].startswith(("ARC", "APC"))) != entry["credit"]:
                continue
            if g.currency and i["currency"] != g.currency:
                continue
            # Payment factory cross-entity payments need a resolved beneficiary identity.
            if not parties and g.entity and i["entity"] != g.entity:
                continue
            score = 5 * (i["balance"] == entry["paid"]) + 3 * (i["total"] == entry.get("gross", entry["paid"]))
            score += 10 * (norm(i["doc"]) == norm(entry["doc"])) + 10 * bool(parties)
            if i["balance"] > 0:
                score += 2
            good.append((score, i))
        good.sort(key=lambda x: (-x[0], x[1]["issue"], x[1]["iid"]))
        if not good or (len(good) > 1 and good[0][0] == good[1][0] and good[0][1]["party"] != good[1][1]["party"]):
            return None
        return good[0][1]

    def structured(self, t):
        ret = is_return(t)
        txnorm, txtokens = norm(text_of(t)), tokens(text_of(t))
        possibilities = []
        for g in self.sources.candidates(t):
            if g.account and g.account != t["account_id"]:
                continue
            if not g.account and g.entity != t["entity"]:
                continue
            days = abs((date.fromisoformat(t["booking_date"]) - date.fromisoformat(g.date)).days)
            direct = any(norm(r) in txnorm for r in g.refs if len(norm(r)) >= 5)
            if g.kind in {"receipt", "cheque"} and not ret:
                continue
            if not direct and days > 3:
                continue
            if direct and days > 45 and not ret:
                continue
            if not ret and (cents(t["amount"]) < 0) != (g.cash < 0):
                continue
            if not self.cash_matches(t, g.currency or t["currency"], g.cash):
                continue
            proposals = {}
            for entry in g.entries:
                i = self.resolve_entry(entry, g, t)
                if i is None:
                    break
                if not g.currency and i["currency"] != t["currency"]:
                    break
                key = i["iid"]
                if key not in proposals:
                    proposals[key] = {"item": i, "paid": 0, "reason": entry.get("reason", "")}
                proposals[key]["paid"] += entry["paid"]
            else:
                allocations = []
                for key, proposal in sorted(proposals.items()):
                    amount, exc = self.policy(proposal["item"], proposal["paid"], t, proposal["reason"], ret)
                    allocations.append((key, amount, exc))
                priority = (100 if direct else 0) + (20 if g.kind not in {"receipt", "cheque"} else 0) - min(days, 10)
                possibilities.append((priority, allocations, g))
        possibilities.sort(key=lambda p: (-p[0], p[2].key))
        if not possibilities:
            return None
        best = possibilities[0]
        if len(possibilities) > 1 and best[0] == possibilities[1][0] and best[1] != possibilities[1][1]:
            return None
        return best[1], {"method": "structured:" + best[2].kind, "source": best[2].source,
                         "group": best[2].key, "cash": best[2].cash}

    def reference_match(self, t):
        tx, booking, ret = text_of(t), t["booking_date"], is_return(t)
        amt = abs(cents(t["amount"]))
        side = "AR" if cents(t["amount"]) > 0 else "AP"
        if ret:
            side = "AP" if side == "AR" else "AR"
        parties = self.c.identify(tx, entity=t["entity"], side=side, iban=t.get("counterparty_account", ""))
        # Outgoing AR credit notes and incoming AP credit notes are valid settlements.
        alternate = "AP" if side == "AR" else "AR"
        otherparties = self.c.identify(tx, entity=t["entity"], side=alternate, iban=t.get("counterparty_account", ""))
        scoped = self.c.by_party(parties, booking) if parties else []
        explicit = {}
        for token in sorted(tokens(tx)):
            for i in self.c.lookup(token, entity=t["entity"], booking=booking):
                credit = i["iid"].startswith(("ARC", "APC"))
                if i["side"] != side and not credit:
                    continue
                if parties and i["party"] not in parties and i["party"] not in otherparties:
                    continue
                # A suffix/PO needs party corroboration or an exact single-amount match.
                full = token == norm(i["doc"]) or i.get("ref_kind") == "replacement"
                if not full and not parties and not self.cash_matches(t, i["currency"], i["balance"] or i["total"]):
                    continue
                explicit[i["iid"]] = i
        if explicit:
            # Prefer a replacement over the cancelled printed number, and fully scoped candidates.
            values = sorted(explicit.values(), key=lambda i: (i["issue"], i["iid"]))
            currs = {i["currency"] for i in values}
            if len(values) > 1 and len(currs) == 1:
                signed = sum((-1 if i["iid"].startswith(("ARC", "APC")) else 1) * i["balance"] for i in values)
                if all(i["balance"] > 0 for i in values) and self.cash_matches(t, values[0]["currency"], signed):
                    return [(i["iid"], *self.policy(i, i["balance"], t, force_return=ret)) for i in values], {"method": "references:netted", "references": sorted(tokens(tx))}
            ranked = []
            for i in values:
                paid = self.item_cash(i, t)
                if paid is None:
                    continue
                cleared, exc = self.policy(i, paid, t, force_return=ret)
                score = 30 * (paid == i["balance"]) + 15 * (exc in ("SHORT_DISCOUNT", "SHORT_WITHHOLDING", "SHORT_BANK_CHARGES"))
                score += 10 * (i["party"] in parties) + 5 * (i["balance"] > 0)
                if i.get("ref_kind") == "replacement":
                    score += 20
                ranked.append((score, i, cleared, exc))
            ranked.sort(key=lambda r: (-r[0], r[1]["issue"], r[1]["iid"]))
            if ranked and (len(ranked) == 1 or ranked[0][0] > ranked[1][0]):
                _, i, cleared, exc = ranked[0]
                return [(i["iid"], cleared, exc)], {"method": "references:single", "reference": i["doc"]}
        # Party-only matching never searches globally by amount (unidentified lookalikes are deliberate).
        pool = [i for i in scoped if i["balance"] > 0 and not json.loads(i["facts"]).get("cancelled")]
        exact = [i for i in pool if self.cash_matches(t, i["currency"], i["balance"])]
        if exact:
            pids = {i["party"] for i in exact}
            if len(pids) == 1:
                exact.sort(key=lambda i: (i["issue"], i["iid"]))
                i = exact[0]
                return [(i["iid"], *self.policy(i, i["balance"], t, force_return=ret))], {"method": "party:amount_fifo", "party": i["party"]}
        discounted = []
        for i in pool:
            paid = self.item_cash(i, t)
            if paid is not None:
                cleared, exc = self.policy(i, paid, t, force_return=ret)
                if exc in ("SHORT_DISCOUNT", "SHORT_WITHHOLDING", "SHORT_BANK_CHARGES"):
                    discounted.append((i, cleared, exc))
        if len(discounted) == 1:
            i, cleared, exc = discounted[0]
            return [(i["iid"], cleared, exc)], {"method": "party:policy", "party": i["party"]}
        same = [i for i in pool if i["currency"] == t["currency"] and not i["iid"].startswith(("ARC", "APC"))]
        if len(parties) == 1 and 1 < len(same) <= 24 and not ret:
            found = self.subset(same, amt)
            if found:
                return [(i["iid"], *self.policy(i, i["balance"], t)) for i in found], {"method": "party:bounded_subset", "party": next(iter(parties))}
        return None

    def item_cash(self, i, t):
        if i["currency"] == t["currency"]:
            return abs(cents(t["amount"]))
        if t.get("orig_currency") == i["currency"] and t.get("orig_amount"):
            return abs(cents(t["orig_amount"]))
        if self.cash_matches(t, i["currency"], i["balance"] or i["total"]):
            return i["balance"] or i["total"]
        return None

    @staticmethod
    def subset(items, target):
        # Bounded deterministic subset sum; ambiguity is retained as a refusal to allocate.
        states = {0: ()}
        ambiguous = set()
        for index, i in enumerate(items):
            for total, chosen in list(states.items()):
                new = total + i["balance"]
                if new > target or len(chosen) >= 6:
                    continue
                seq = chosen + (index,)
                if new in states and states[new] != seq:
                    ambiguous.add(new)
                else:
                    states[new] = seq
                if total in ambiguous:
                    ambiguous.add(new)
            if len(states) > 20000:
                return None
        if target not in states or target in ambiguous:
            return None
        return [items[i] for i in states[target]]

    def reconcile(self, t, reversal_ids=()):
        if t["bank_txn_id"] in reversal_ids:
            return [[t["bank_txn_id"], "", "", "BANK_REVERSAL", ""]], {"method": "narrative:reversal_pair"}
        category = classify(t)
        if category:
            cat, exc, method = category
            return [[t["bank_txn_id"], "", "", cat, exc]], {"method": method}
        result = self.structured(t) or self.reference_match(t) or self.extension_match(t)
        if result:
            allocations, evidence = result
            for iid, amount, exc in allocations:
                self.c.apply(iid, amount, exc)
            return [[t["bank_txn_id"], iid, money(amount), "", exc] for iid, amount, exc in allocations], evidence
        return [[t["bank_txn_id"], "", "", "UNIDENTIFIED", "UNIDENTIFIED"]], {"method": "unresolved", "reason": "no unambiguous supported allocation"}
