"""Diagnose saved baseline outputs against labels from the 10 MB starter only.

This does not run reconciliation, train a model, change predictions, or read TRAIN/LIVE.
Usage: python3 self_review/tools/analyze_saved_sample.py
"""
from collections import Counter, defaultdict
from decimal import Decimal
from pathlib import Path
import csv
import gzip
import json
import re
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))


ROOT = Path(__file__).resolve().parents[2]
SAMPLE = ROOT / "data/docs/sample"
OUTPUT = ROOT / "self_review/2026-11-07_sample_diagnosis.json"


def read(path):
    op = gzip.open if path.suffix == ".gz" else open
    with op(path, "rt", encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def correct_amount(pred, gold):
    return abs(Decimal(pred) - Decimal(gold)) <= max(Decimal("0.01"), Decimal(gold) * Decimal("0.005"))


def norm(value):
    return re.sub(r"[^A-Z0-9]", "", value.upper())


def main():
    transactions = {r["bank_txn_id"]: r for r in read(SAMPLE / "bank_transactions.csv.gz")}
    golden, predicted = defaultdict(list), defaultdict(list)
    for r in read(SAMPLE / "golden_allocations.csv.gz"):
        golden[r["bank_txn_id"]].append(r)
    for r in read(ROOT / "final_submission/sample/submission.csv"):
        predicted[r["bank_txn_id"]].append(r)
    evidence = {}
    for line in (ROOT / "final_submission/sample/evidence.jsonl").read_text().splitlines():
        r = json.loads(line)
        evidence[r["bank_txn_id"]] = r
    items = {}
    for name in ("ar_invoices", "ap_invoices", "credit_notes"):
        for r in read(SAMPLE / (name + ".csv.gz")):
            items[r["item_id"]] = r

    failures, by_segment, methods = Counter(), {}, {}
    missing_pairs, amount_errors, exception_errors = Counter(), Counter(), Counter()
    mismatch_types, examples, overpay_rows = {}, defaultdict(list), Counter()
    overpay_examples = []
    gold_pair_count = matched_pairs = predicted_pair_count = 0
    missing_item_ids = set()
    for tid, gold in golden.items():
        pred = predicted.get(tid, [])
        gi = {r["item_id"]: r for r in gold if r["item_id"]}
        pi = {r["item_id"]: r for r in pred if r["item_id"]}
        missing, extra = gi.keys() - pi.keys(), pi.keys() - gi.keys()
        bad_amount = {i for i in gi.keys() & pi.keys() if not correct_amount(pi[i]["amount"], gi[i]["amount"])}
        bad_exc = {i for i in gi.keys() & pi.keys() if pi[i]["exception"] != gi[i]["exception"]}
        seg = gold[0]["segment"]
        method = evidence[tid]["method"]
        for i in gi:
            if i not in items:
                missing_item_ids.add(i)
        gold_pair_count += len(gi)
        predicted_pair_count += len(pi)
        matched_pairs += sum(correct_amount(pi[i]["amount"], gi[i]["amount"]) for i in gi.keys() & pi.keys())
        missing_pairs[seg] += len(missing)
        amount_errors[seg] += len(bad_amount)
        exception_errors[seg] += len(bad_exc)
        if gi:
            if not pi:
                kind = "item_case_unresolved" if method == "unresolved" else "item_case_wrongly_categorized"
            elif missing and extra:
                kind = "missing_and_extra_items"
            elif missing:
                kind = "missing_items_only"
            elif extra:
                kind = "extra_items_only"
            elif bad_amount:
                kind = "correct_item_set_wrong_amount"
            elif bad_exc:
                kind = "correct_items_and_amounts_wrong_exception"
            else:
                kind = "correct"
        elif pi:
            kind = "nonitem_case_forced_to_items"
        elif not pred or pred[0]["category"] != gold[0]["category"]:
            kind = "nonitem_wrong_or_missing_category"
        elif pred[0]["exception"] != gold[0]["exception"]:
            kind = "nonitem_wrong_exception"
        else:
            kind = "correct"
        failures[kind] += 1
        mismatch_types[tid] = kind
        for stats, key in ((by_segment, seg), (methods, method)):
            rec = stats.setdefault(key, {"transactions": 0, "correct": 0, "failures": Counter(), "missing_item_pairs": 0})
            rec["transactions"] += 1
            rec["correct"] += kind == "correct"
            rec["failures"][kind] += 1
            rec["missing_item_pairs"] += len(missing)
        if kind != "correct" and len(examples[seg]) < 2:
            examples[seg].append({"bank_txn_id": tid, "kind": kind, "bank": transactions[tid],
                                  "prediction": pred, "golden": gold, "evidence": evidence[tid]})
        for iid, row in pi.items():
            if row["exception"] != "OVERPAYMENT":
                continue
            gr = gi.get(iid)
            overpay_rows["predicted"] += 1
            if gr and gr["exception"] == "OVERPAYMENT":
                overpay_rows["correct_exception_key"] += 1
            else:
                overpay_rows["false_exception_key"] += 1
                overpay_rows["false_in_multi_item_golden_case"] += len(gi) > 1
                overpay_rows["false_with_missing_golden_items"] += bool(missing)
                overpay_rows["false_but_item_amount_correct"] += bool(gr and correct_amount(row["amount"], gr["amount"]))
                overpay_rows["gold_exception:" + (gr["exception"] if gr else "ITEM_NOT_IN_GOLD")] += 1
                if missing and len(overpay_examples) < 3:
                    overpay_examples.append({"bank_txn_id": tid, "bank": transactions[tid],
                                             "prediction": pred, "golden": gold,
                                             "documents": {i: items.get(i) for i in gi}, "evidence": evidence[tid]})

    runs = [r for f in sorted((SAMPLE / "payment_runs").glob("*.csv")) for r in read(f)]
    runids = {norm(r["run_id"]) for r in runs}
    confirming = []
    for tid, gold in golden.items():
        if gold[0]["segment"] != "ap_confirming":
            continue
        t = transactions[tid]
        refs = set(re.findall(r"CF\d+", " ".join(t.get(k, "") for k in ("text", "ref1", "ref2", "end_to_end_id"))))
        confirming.append({"bank_txn_id": tid, "references": sorted(refs),
                           "has_exact_run_reference_in_sample": bool({norm(r) for r in refs} & runids)})
    saved = json.loads((ROOT / "reports/sample_score.json").read_text())
    metric = saved["metrics"]
    weights = {"allocation_f1": 50, "txn_accuracy": 30, "exception_macro_f1": 20}
    components = {k: {"value": metric[k], "score_points": round(w*metric[k], 5),
                       "headroom_to_perfect_points": round(w*(1-metric[k]), 5)} for k,w in weights.items()}
    # These are label-assisted diagnostics of the frozen output, never achievable-score claims.
    pair_ceilings = {
        "perfect_exception_macro_with_other_components_fixed": round(50*metric["allocation_f1"] + 30*metric["txn_accuracy"] + 20, 2),
        "perfect_txn_accuracy_with_other_components_fixed": round(50*metric["allocation_f1"] + 30 + 20*metric["exception_macro_f1"], 2),
        "perfect_allocation_f1_with_other_components_fixed": round(50 + 30*metric["txn_accuracy"] + 20*metric["exception_macro_f1"], 2),
    }
    result = {
        "scope": "diagnostic comparison of saved predictions with labels in the 10 MB starter only",
        "warning": "Contains golden-assisted analysis; evaluation-only, never an inference input. No solver run or training.",
        "sample_transactions": len(transactions), "saved_official_score": saved["score"],
        "components": components, "component_only_arithmetic_ceilings": pair_ceilings,
        "item_pair_counts": {"golden": gold_pair_count, "predicted": predicted_pair_count, "correct_with_amount_tolerance": matched_pairs,
                             "absent_required_item_keys": sum(missing_pairs.values()), "wrong_amount_common_item_keys": sum(amount_errors.values()),
                             "golden_item_ids_absent_from_sample_item_tables": len(missing_item_ids)},
        "transaction_outcomes_mutually_exclusive": dict(failures),
        "missing_pairs_by_segment": dict(missing_pairs.most_common()),
        "amount_errors_by_segment": dict(amount_errors.most_common()),
        "exception_errors_by_segment": dict(exception_errors.most_common()),
        "segments": by_segment, "methods": methods,
        "overpayment_diagnosis": dict(overpay_rows), "overpayment_examples": overpay_examples,
        "confirming_source_availability": {"transactions": len(confirming),
                    "exact_run_reference_present": sum(r["has_exact_run_reference_in_sample"] for r in confirming),
                    "reference_examples": confirming[:5]},
        "failure_examples_by_segment": dict(examples),
    }
    # A small set of source-level counterexamples. This prepares sample source facts only;
    # it never calls Engine.reconcile, Catalog.apply or any archive containing another phase.
    from bankrec.sources import Sources
    from pypdf import PdfReader
    sources = Sources(SAMPLE, ROOT / "work/cache/pdf_text")
    customers = read(ROOT / "data/docs/masters/customers.csv")
    traces = {}
    parent_case = examples["ar_short_dispute"][0]
    parent_group = next(g for g in sources.candidates(parent_case["bank"]) if g.kind == "remittance")
    entry = parent_group.entries[0]
    child = next(i for i in items.values() if i["entity"] == parent_group.entity and norm(i.get("document_number", "")) == norm(entry["doc"]))
    payer = next(r for r in customers if norm(r["name"]) == norm(entry["name"]))
    child_master = next(r for r in customers if r["customer_id"] == child["customer_id"])
    traces["parent_payer_rejected"] = {
        "bank_txn_id": parent_case["bank_txn_id"], "source": parent_group.source,
        "source_document_count": len(parent_group.entries), "golden_document_count": len(parent_case["golden"]),
        "source_cash_cents": parent_group.cash, "payer": payer["customer_id"], "invoice_customer": child["customer_id"],
        "invoice_customer_parent": child_master["parent_customer_id"],
        "payer_group": payer["group_id"], "invoice_customer_group": child_master["group_id"],
        "first_entry_document": entry["doc"], "observed_prediction": parent_case["prediction"],
    }
    present = next(r for r in confirming if r["has_exact_run_reference_in_sample"])
    tid = present["bank_txn_id"]
    matching_run = [r for r in runs if norm(r["run_id"]) in {norm(k) for k in present["references"]}]
    traces["confirming_wrong_group_granularity"] = {
        "bank_txn_id": tid, "bank_cash": transactions[tid]["amount"], "source_rows": len(matching_run),
        "whole_run_signed_document_sum": str(sum(Decimal(r["document_amount"]) for r in matching_run)),
        "golden_rows": len(golden[tid]),
        "matching_transfer_rows": [r for r in matching_run if abs(Decimal(r["transfer_amount"])) == abs(Decimal(transactions[tid]["amount"]))],
    }
    credit_case = examples["ar_1toN_credit_note"][0]
    traces["unmentioned_credit_relation"] = {
        "bank_txn_id": credit_case["bank_txn_id"], "bank_text": credit_case["bank"]["text"],
        "credit_notes": [items[r["item_id"]] for r in credit_case["golden"] if r["item_id"].startswith("ARC")],
        "observed_prediction": credit_case["prediction"],
    }
    plan_case = examples["ar_instalment"][0]
    plan_item = items[plan_case["golden"][0]["item_id"]]
    pdf = next(r for r in read(SAMPLE / "pdfs/index.csv") if r["document_number"] == plan_item["document_number"])
    tx = "\n".join(page.extract_text() or "" for page in PdfReader(SAMPLE / "pdfs" / pdf["file"]).pages)
    traces["last_instalment_ignored"] = {
        "bank_txn_id": plan_case["bank_txn_id"], "bank_text": plan_case["bank"]["text"],
        "pdf": "pdfs/" + pdf["file"], "clauses": [line for line in tx.splitlines() if "instalment" in line.lower()],
        "observed_prediction": plan_case["prediction"], "golden": plan_case["golden"],
    }
    # Selected by the document-overlap audit: incorrect totals can prevent retrieval itself.
    mail_group = sources.groups["advice:remittance_advices/ES01/RA_20250609_SUMINISTROSP_358143.txt"]
    mail_entry = next(e for e in mail_group.entries if "DAMAGED GOODS" in e["reason"])
    raw_item = next(i for i in items.values() if norm(i.get("document_number", "")) == norm(mail_entry["doc"]))
    traces["mail_deduction_misread_as_paid"] = {
        "bank_txn_id": "BT-2025-0173384", "source": mail_group.source,
        "retrieved_by_existing_source_index": mail_group.key in {g.key for g in sources.candidates(transactions["BT-2025-0173384"])},
        "document": mail_entry["doc"], "invoice_total": raw_item["total_amount"],
        "parsed_paid_cents": mail_entry["paid"], "parsed_first_amount_cents": mail_entry["gross"],
        "deduction_reason": mail_entry["reason"],
        "golden_allocation": next(r for r in golden["BT-2025-0173384"] if r["item_id"] == raw_item["item_id"]),
    }
    result["source_traces"] = traces
    expected = round(metric["txn_accuracy"]*len(transactions))
    assert failures["correct"] == expected, (failures["correct"], expected)
    OUTPUT.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({k:result[k] for k in ["components", "component_only_arithmetic_ceilings", "item_pair_counts",
        "transaction_outcomes_mutually_exclusive", "overpayment_diagnosis", "confirming_source_availability"]}, indent=2))
    print("Largest missing-pair segments:", missing_pairs.most_common(8))
    print("Saved:", OUTPUT)


if __name__ == "__main__":
    main()
