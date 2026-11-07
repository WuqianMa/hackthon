import csv
import hashlib
import io
import json
from pathlib import Path
import tempfile
import unittest
import zipfile

from bankrec.catalog import Catalog
from bankrec.engine import Engine, classify
from bankrec.io import FIELDS, cents, extract, money, is_data_file
from bankrec.sources import Sources
from bankrec.validate import validate


class StubCatalog:
    terms = {"D2": {"early_payment_discount_pct": "2.00", "discount_days": "10"}}
    categories = {"BANK_FEES", "UNIDENTIFIED"}
    party_info = {"CUSTOMER": {"country": "ES"}, "MEXICO": {"country": "MX"}, "USA": {"country": "US"}}

    def rate(self, cur, booking):
        from decimal import Decimal
        return Decimal({"EUR": "1", "USD": "1.10"}[cur])

    def item(self, iid):
        return item() if iid == "ARI-2025-0000001" else None


def item(**kw):
    value = {"iid": "ARI-2025-0000001", "entity": "ES01", "party": "CUSTOMER", "issue": "2025-06-01",
             "currency": "EUR", "total": 100000, "initial": 100000, "balance": 100000, "terms": "D2"}
    value.update(kw)
    return value


def bank(**kw):
    value = {"bank_txn_id": "BT-2025-0000001", "entity": "ES01", "booking_date": "2025-06-14",
             "amount": "980.00", "currency": "EUR", "text": "", "account_id": "ES01-BANK-EUR"}
    value.update(kw)
    return value


class PolicyTests(unittest.TestCase):
    def setUp(self):
        self.engine = Engine(StubCatalog(), None)

    def test_discount_last_grace_day_clears_full_invoice(self):
        self.assertEqual(self.engine.policy(item(), 98000, bank()), (100000, "SHORT_DISCOUNT"))

    def test_discount_one_day_late_stays_open(self):
        self.assertEqual(self.engine.policy(item(), 98000, bank(booking_date="2025-06-15")), (98000, "PARTIAL"))

    def test_discount_uses_total_and_decimal_rounding(self):
        self.assertEqual(self.engine.policy(item(total=10001, balance=10001), 9801, bank()), (10001, "SHORT_DISCOUNT"))

    def test_dispute_uses_cash(self):
        self.assertEqual(self.engine.policy(item(), 95000, bank(), "damaged goods"), (95000, "SHORT_DISPUTE"))

    def test_fx_overrides_full_discount(self):
        self.assertEqual(self.engine.policy(item(currency="USD"), 98000, bank()), (100000, "FX_DIFFERENCE"))

    def test_fx_keeps_partial(self):
        self.assertEqual(self.engine.policy(item(currency="USD"), 30000, bank()), (30000, "PARTIAL"))

    def test_credit_note_full_amount_positive_and_empty_exception(self):
        self.assertEqual(self.engine.policy(item(iid="ARC-2025-0000001", currency="USD"), 100000, bank()), (100000, ""))

    def test_last_instalment_has_no_exception(self):
        self.assertEqual(self.engine.policy(item(balance=30000), 30000, bank()), (30000, ""))

    def test_duplicate_does_not_clear_closed_balance(self):
        self.assertEqual(self.engine.policy(item(balance=0), 100000, bank()), (100000, "DUPLICATE_PAYMENT"))

    def test_return_reopens_original_allocation(self):
        self.assertEqual(self.engine.policy(item(balance=0), 40000, bank(), force_return=True), (40000, "RETURNED"))

    def test_overpayment_clears_only_open_amount(self):
        self.assertEqual(self.engine.policy(item(), 101000, bank()), (100000, "OVERPAYMENT"))

    def test_withholding_requires_eligible_country(self):
        self.assertEqual(self.engine.policy(item(party="MEXICO"), 98500, bank()), (100000, "SHORT_WITHHOLDING"))
        self.assertEqual(self.engine.policy(item(), 98500, bank()), (98500, "PARTIAL"))

    def test_bank_charges_require_marker_and_both_limits(self):
        b = bank(text="/CHGS/EUR20,00")
        self.assertEqual(self.engine.policy(item(party="USA", terms="T30"), 98000, b), (100000, "SHORT_BANK_CHARGES"))
        self.assertEqual(self.engine.policy(item(party="USA", terms="T30"), 98000, bank()), (98000, "PARTIAL"))
        self.assertEqual(self.engine.policy(item(party="USA", terms="T30"), 97000, b), (97000, "PARTIAL"))

    def test_fx_rates_use_previous_available_business_day(self):
        c = object.__new__(Catalog)
        c.fx = {"USD": [("2025-06-06", "1.10"), ("2025-06-09", "1.20")]}
        self.assertEqual(str(c.rate("USD", "2025-06-08")), "1.10")
        with self.assertRaises(ValueError):
            c.rate("USD", "2025-06-01")

    def test_fx_cash_tolerance_and_original_currency(self):
        self.assertTrue(self.engine.cash_matches(bank(amount="900.00"), "USD", 100000))
        self.assertFalse(self.engine.cash_matches(bank(amount="800.00"), "USD", 100000))
        self.assertTrue(self.engine.cash_matches(bank(orig_amount="1000.00", orig_currency="USD"), "USD", 100000))

    def test_ambiguous_subset_abstains(self):
        self.assertIsNone(Engine.subset([item(balance=100), item(balance=200), item(balance=300)], 300))


class InputTests(unittest.TestCase):
    def test_macos_sidecars_are_not_data(self):
        with tempfile.TemporaryDirectory() as d:
            for name in ("._file.csv", "file.csv", ".DS_Store"):
                (Path(d) / name).write_bytes(b"test")
            self.assertFalse(is_data_file(Path(d) / "._file.csv"))
            self.assertFalse(is_data_file(Path(d) / ".DS_Store"))
            self.assertTrue(is_data_file(Path(d) / "file.csv"))

    def test_decimal_money(self):
        self.assertEqual(cents("1.005"), 101)
        self.assertEqual(money(101), "1.01")
        for value in ["NaN", "Infinity"]:
            with self.assertRaises(ValueError):
                cents(value)

    def test_archive_rejects_traversal_after_hash_verification(self):
        with tempfile.TemporaryDirectory() as d:
            archive = Path(d) / "bad.zip"
            with zipfile.ZipFile(archive, "w") as z:
                z.writestr("../escaped.txt", "bad")
            expected = hashlib.sha256(archive.read_bytes()).hexdigest()
            with self.assertRaises(ValueError):
                extract(archive, Path(d) / "out", expected)
            self.assertFalse((Path(d) / "escaped.txt").exists())

    def test_checksum_mismatch_never_extracts(self):
        with tempfile.TemporaryDirectory() as d:
            archive = Path(d) / "ok.zip"
            with zipfile.ZipFile(archive, "w") as z:
                z.writestr("file.txt", "ok")
            with self.assertRaises(ValueError):
                extract(archive, Path(d) / "out", "0" * 64)
            self.assertFalse((Path(d) / "out").exists())

    def test_spanish_and_english_advice_amounts(self):
        es = "Ref.\nPAY123456\nFecha\n02/06/2025\nImporte\n1.000,00 EUR\nFV25-0100001\n01/05/2025\n1.100,00\n-100,00 PRECIO\n1.000,00\nDocumento sintético de prueba"
        en = "Subject: Payment advice PAY123456\nSent 1,000.00 EUR on 06/02/2025\n  FA250100001 01/05/25 1,000.00\nKind regards"
        for tx in (es, en):
            ref, dt, curr, entries = Sources.text_advice(tx)
            self.assertEqual((ref, dt, curr), ("PAY123456", "2025-06-02", "EUR"))
            self.assertEqual(entries[0]["paid"], 100000)
        self.assertEqual(Sources.text_advice(es)[3][0]["reason"], "PRECIO")

    def test_unidentified_is_not_classified_as_fee(self):
        self.assertIsNone(classify(bank(amount="-450.00", text="unknown outgoing transfer")))

    def test_numeric_printed_number_in_us_advice(self):
        tx = "Payment ref.\nPAY123456\nDate\n02/07/2025\nAmount\n1,000.00 USD\n1122511858\n01/06/2025\n1,000.00\n1,000.00\n"
        self.assertEqual(Sources.text_advice(tx)[3][0]["doc"], "1122511858")

    def test_cheque_number_is_not_globally_unique(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "cheque_deposits"; p.mkdir()
            fields = ["deposit_id", "deposit_date", "account_id", "currency", "deposit_total", "cheque_number", "drawer", "drawer_bank_routing", "amount", "stub_reference"]
            for account in ("ES01-BANK-EUR", "FR01-BANK-EUR"):
                with (p / (account + ".csv")).open("w", newline="") as f:
                    w = csv.writer(f); w.writerow(fields)
                    w.writerow(["DEP123456", "2025-06-01", account, "EUR", "100.00", "6177116", "Payer", "", "100.00", "INV123456"])
            s = Sources(Path(d), Path(d) / "cache")
            self.assertEqual(s.counts["cheque"], 2)

    def test_extension_provenance_excludes_golden_and_wrong_hash(self):
        from bankrec.extensions import Evidence, evidence_is_valid
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            (root / "golden_allocations.csv").write_text("labels")
            (root / "advice.txt").write_text("invoice 123")
            h = hashlib.sha256(b"invoice 123").hexdigest()
            self.assertTrue(evidence_is_valid((Evidence("advice.txt", h, "printed reference"),), root))
            self.assertFalse(evidence_is_valid((Evidence("advice.txt", "0"*64, "printed reference"),), root))
            self.assertFalse(evidence_is_valid((Evidence("golden_allocations.csv", h, "labels"),), root))


class ValidationTests(unittest.TestCase):
    def check(self, values, txns=None):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "submission.csv"
            with p.open("w", newline="") as f:
                w = csv.writer(f); w.writerow(FIELDS); w.writerows(values)
            return validate(p, txns or {bank()["bank_txn_id"]: bank()}, StubCatalog())

    def test_valid_submission(self):
        self.assertTrue(self.check([[bank()["bank_txn_id"], item()["iid"], "1000.00", "", "SHORT_DISCOUNT"]])["ok"])

    def test_unknown_item_rejected_even_if_syntax_valid(self):
        self.assertFalse(self.check([[bank()["bank_txn_id"], "ARI-2025-9999999", "100.00", "", ""]])["ok"])

    def test_coverage_and_duplicate_and_mixed_rows(self):
        t = bank()["bank_txn_id"]
        self.assertFalse(self.check([])["ok"])
        self.assertFalse(self.check([[t, "", "", "BANK_FEES", ""]] * 2)["ok"])
        self.assertFalse(self.check([[t, "", "", "BANK_FEES", ""], [t, item()["iid"], "100.00", "", ""]])["ok"])

    def test_nonfinite_negative_and_precision(self):
        for a in ("NaN", "-1.00", "1.001"):
            self.assertFalse(self.check([[bank()["bank_txn_id"], item()["iid"], a, "", ""]])["ok"])

    def test_overclearing_across_transactions(self):
        t1, t2 = bank(), bank(bank_txn_id="BT-2025-0000002")
        values = [[t1["bank_txn_id"], item()["iid"], "600.00", "", "PARTIAL"],
                  [t2["bank_txn_id"], item()["iid"], "600.00", "", ""]]
        self.assertFalse(self.check(values, {t1["bank_txn_id"]: t1, t2["bank_txn_id"]: t2})["ok"])


if __name__ == "__main__":
    unittest.main()
