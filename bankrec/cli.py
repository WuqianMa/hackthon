from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from datetime import date
import csv
import importlib.util
import json
import os
from pathlib import Path
import shutil
import sys
import time

from . import __version__
from .catalog import Catalog
from .engine import Engine, text_of
from .io import FIELDS, EXCEPTIONS, HASHES, cents, digest, extract, find_folder, rows, table, write_json, is_data_file
from .sources import Sources
from .validate import validate


DATES = {"sample": ("2025-06-01", "2025-06-30"), "train": ("2021-07-01", "2025-06-30"),
         "live": ("2025-07-01", "2025-12-31"), "final": ("2026-01-01", "2026-06-30")}


def merged_masters(base, phase, target):
    """FINAL rows override baseline rows by stable primary keys; retain missing older rows."""
    overlay = phase / "masters_final"
    if not overlay.is_dir():
        return base
    target.mkdir(parents=True, exist_ok=True)
    keys = {"entities": ["entity"], "bank_accounts": ["account_id"], "customers": ["customer_id"],
            "suppliers": ["supplier_id"], "categories": ["category"], "payment_terms": ["code"],
            "fx_rates": ["date", "currency"]}
    for name, keycols in keys.items():
        record = {}
        fields = None
        for root in (base, overlay):
            p = table(root, name, required=False)
            if not p:
                continue
            for r in rows(p):
                if fields is None:
                    fields = list(r)
                if set(r) != set(fields):
                    raise ValueError(f"master schema drift in {p}; review the changed columns")
                record[tuple(r[k] for k in keycols)] = r
        if fields is None:
            raise ValueError(f"missing master {name}")
        with (target / (name + ".csv")).open("w", encoding="utf-8", newline="") as f:
            w = csv.DictWriter(f, fieldnames=fields, lineterminator="\n")
            w.writeheader()
            w.writerows(record[k] for k in sorted(record))
    return target


def reversal_pairs(transactions):
    from .io import plain
    by_amount, result = defaultdict(list), set()
    for t in transactions.values():
        by_amount[(t["account_id"], t["currency"], cents(t["amount"]))].append(t)
    for t in transactions.values():
        tx = plain(text_of(t))
        if "ANULACION OPERACION INDEBIDA" not in tx and "BANK ERROR REVERSAL" not in tx:
            continue
        peers = [p for p in by_amount[(t["account_id"], t["currency"], -cents(t["amount"]))]
                 if 0 <= (date.fromisoformat(t["booking_date"]) - date.fromisoformat(p["booking_date"])).days <= 7]
        result.add(t["bank_txn_id"])
        if len(peers) == 1:
            result.add(peers[0]["bank_txn_id"])
    return result


def evaluate(docs, phase, submission, categories):
    path = docs / "starter" / "bankrec_score.py"
    spec = importlib.util.spec_from_file_location("official_bankrec_score", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    golden = mod.load_golden(str(table(phase, "golden_allocations")), str(table(phase, "bank_transactions")), sorted(EXCEPTIONS), sorted(categories))
    result = mod.score_submission(golden, submission.read_bytes(), "submission.csv")
    result["weight_note"] = "Official scorer fallback weights item-currency allocations, not true EUR cash; bank CSV lacks amount_eur."
    return result


def run(a):
    started = time.monotonic()
    work = Path(a.work_dir).resolve()
    work.mkdir(parents=True, exist_ok=True)
    print("Verifying and preparing archives...", flush=True)
    docroot, docsha = extract(a.docs_archive, work / "archives" / "docs", HASHES["docs"])
    docs = find_folder(docroot, "masters").parent
    hashes = {"docs": docsha}
    if a.phase == "sample":
        phase = docs / "sample"
    else:
        if not a.phase_archive:
            raise ValueError("--phase-archive is required outside the sample")
        expected = a.expected_phase_sha256 or HASHES.get(a.phase)
        if not expected:
            raise ValueError("FINAL requires --expected-phase-sha256 from the official download")
        root, hashes[a.phase] = extract(a.phase_archive, work / "archives" / a.phase, expected)
        phase = find_folder(root, a.phase)
    out = Path(a.output_dir or (Path("final_submission") / a.phase)).resolve()
    out.mkdir(parents=True, exist_ok=True)
    # A failed new run cannot leave an old file looking like the newly validated result.
    status = out / "run_status.json"
    write_json(status, {"status": "running", "phase": a.phase, "archive_hashes": hashes})
    runwork = work / "runs" / a.phase
    runwork.mkdir(parents=True, exist_ok=True)
    masters = merged_masters(docs / "masters", phase, runwork / "masters")
    transactions = {}
    lo, hi = DATES[a.phase]
    for t in rows(table(phase, "bank_transactions")):
        if t["bank_txn_id"] in transactions:
            raise ValueError("duplicate normalized bank ID")
        if not lo <= t["booking_date"] <= hi:
            raise ValueError(f"cross-phase booking date: {t['bank_txn_id']}")
        cents(t["amount"])
        transactions[t["bank_txn_id"]] = t
    if not transactions:
        raise ValueError("empty bank transaction input")
    dbpath = runwork / "catalog.sqlite"
    for suffix in ("", "-wal", "-shm"):
        Path(str(dbpath) + suffix).unlink(missing_ok=True)
    print(f"Indexing {len(transactions):,} bank lines, items, masters and PDF clauses...", flush=True)
    catalog = Catalog(dbpath, phase, masters, work / "cache" / "pdf_text", not a.no_pdfs)
    print("Parsing structured batches and remittance advices...", flush=True)
    sources = Sources(phase, work / "cache" / "pdf_text", not a.no_pdfs)
    engine = Engine(catalog, sources)
    reversed_ids = reversal_pairs(transactions)
    tmp = out / "submission.csv.tmp"
    audit_tmp, unresolved_tmp = out / "evidence.jsonl.tmp", out / "unresolved.jsonl.tmp"
    order = sorted(transactions, key=lambda tid: (transactions[tid]["booking_date"], tid))
    methods, exceptions = Counter(), Counter()
    print("Reconciling in booking-date order...", flush=True)
    with tmp.open("w", encoding="utf-8", newline="") as f, audit_tmp.open("w", encoding="utf-8") as af, unresolved_tmp.open("w", encoding="utf-8") as uf:
        writer = csv.writer(f, lineterminator="\n")
        writer.writerow(FIELDS)
        for n, tid in enumerate(order, 1):
            allocations, evidence = engine.reconcile(transactions[tid], reversed_ids)
            writer.writerows(allocations)
            methods[evidence["method"]] += 1
            exceptions.update(r[4] for r in allocations)
            record = {"schema": "bankrec.evidence.v1", "bank_txn_id": tid, **evidence,
                      "bank_source": "bank_transactions.csv.gz", "policy_source": "POLICIES.md §1–5",
                      "allocations": [dict(zip(FIELDS[1:], r[1:])) for r in allocations]}
            af.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")
            if evidence["method"] == "unresolved":
                uf.write(json.dumps({"schema": "bankrec.review.v1", "transaction": transactions[tid],
                                     "reason": evidence["reason"]}, ensure_ascii=False, sort_keys=True) + "\n")
            if n % 10000 == 0:
                catalog.db.commit()
                print(f"  {n:,}/{len(order):,} bank lines", flush=True)
    catalog.db.commit()
    print("Validating coverage, catalog IDs, amounts and allocation balances...", flush=True)
    result = validate(tmp, transactions, catalog)
    write_json(out / "validation.json", result)
    if not result["ok"]:
        write_json(status, {"status": "validation_failed", "phase": a.phase})
        raise ValueError(f"validation failed; inspect {out / 'validation.json'}")
    submission = out / "submission.csv"
    if a.evaluate or a.phase == "sample":
        # Use the organizer's code unchanged; inference has never read golden labels.
        scored = evaluate(docs, phase, tmp, catalog.categories)
        write_json(out / "score.json", scored)
        if not scored["ok"]:
            raise ValueError("official scorer rejected output")
        print(f"Official {a.phase} score: {scored['score']}", flush=True)
    os.replace(tmp, submission)
    os.replace(audit_tmp, out / "evidence.jsonl")
    os.replace(unresolved_tmp, out / "unresolved.jsonl")
    input_manifest = {}
    for root, prefix in ((phase, "phase"), (masters, "masters")):
        for p in sorted(root.rglob("*")):
            if is_data_file(p) and p.suffix in {".csv", ".gz"} and "golden" not in p.name:
                input_manifest[prefix + "/" + str(p.relative_to(root))] = {"sha256": digest(p), "bytes": p.stat().st_size}
    from importlib.metadata import version, PackageNotFoundError
    try:
        pdf_version = version("pypdf")
    except PackageNotFoundError:
        pdf_version = None
    source_hashes = {p.name: digest(p) for p in sorted(Path(__file__).parent.glob("*.py"))}
    manifest = {"version": __version__, "code_sha256": source_hashes, "python": sys.version,
                "pypdf": pdf_version, "command": sys.argv,
                "phase": a.phase, "archive_hashes": hashes,
                "input_tables": input_manifest, "pdf_extraction": not a.no_pdfs,
                "inference_uses_golden": False, "bank_lines": len(transactions), "methods": dict(methods),
                "exceptions": dict(exceptions), "catalog": dict(catalog.counts), "source_groups": dict(sources.counts),
                "source_issues": sources.issues, "submission_sha256": digest(submission),
                "elapsed_seconds": round(time.monotonic() - started, 3),
                "limitations": ["Conservative baseline; unresolved is a review fallback, not proof no item exists.",
                                "Historical closed items absent from the phase/opening snapshot cannot be matched.",
                                "Sample lacks opening balances; prior instalments and returns are incompletely observable."]}
    write_json(out / "manifest.json", manifest)
    write_json(status, {"status": "complete", "phase": a.phase, "submission_sha256": manifest["submission_sha256"]})
    catalog.db.close()
    print(json.dumps({"submission": str(submission), "validation": result["ok"],
                      "bank_lines": len(transactions), "rows": result["rows"],
                      "unresolved": methods["unresolved"], "seconds": manifest["elapsed_seconds"]}, indent=2))


def main():
    parser = argparse.ArgumentParser(description="Offline archive-to-submission bank reconciliation")
    parser.add_argument("--docs-archive", default="bankrec-docs-and-masters.zip")
    parser.add_argument("--phase", choices=["sample", "train", "live", "final"], default="sample")
    parser.add_argument("--phase-archive")
    parser.add_argument("--expected-phase-sha256")
    parser.add_argument("--work-dir", default="work")
    parser.add_argument("--output-dir")
    parser.add_argument("--no-pdfs", action="store_true", help="explicit reduced-coverage mode; recorded in manifest")
    parser.add_argument("--evaluate", action="store_true", help="use the official golden/scorer after inference; TRAIN/sample only")
    a = parser.parse_args()
    if a.evaluate and a.phase not in ("train", "sample"):
        parser.error("evaluation requires TRAIN or sample labels")
    try:
        run(a)
    except Exception as ex:
        output = Path(a.output_dir or (Path("final_submission") / a.phase)).resolve()
        if output.is_dir():
            write_json(output / "run_status.json", {"status": "failed", "phase": a.phase, "error": str(ex)})
        print(f"ERROR: {ex}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
