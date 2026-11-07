# V6: recover mechanisms before ranking more candidates

The dataset is synthetic, and its official README says so. That makes repeated templates, source relationships and exact monetary identities useful targets. It does not make every hidden choice recoverable: truncated narratives can remove the evidence, and multiple groups can fit the same cash amount. V6 adds candidates that v4's model never saw, then keeps v5 for the remaining decisions.

## Scope and inputs

This is a deterministic overlay on the immutable v5 LIVE edition. It reuses the v4 trained model's decisions, v5's archived LLM decisions, the existing SQLite catalogs, opening balances, structured payment files and cached PDF text. It does not refit weights, extract PDFs again, call a new LLM, or run the full TRAIN pipeline. It outputs the same five-column submission contract.

Pattern discovery uses the existing July–December 2024 calibration bank/golden subset. `inspect_cases.py` saves a bounded casebook, at most eight examples per weak family, under ignored `work/version-6/`. It never feeds those golden rows into LIVE inference. The organizer's README, POLICIES and FORMAT are authoritative; local copies are in `work/archives/docs/`.

## Rules implemented

| Mechanism | Evidence and decision | Source |
|---|---|---|
| Named service month | Select the matching party/currency/amount invoice issued at the beginning of the following month. A PDF's explicit service period takes precedence. Support compact `JULY2025`; reject unresolved ties and exhausted items. | POLICIES §5.6; calibration monthly-fee examples |
| Rejected supplier transfer | Recognize `RETURN AC04`, rejected-transfer narratives and the transfer's `PR…-…` reference. Resolve the individual transfer's payment-run documents, including credit notes, and check signed net cash. Reopen every source allocation with `RETURNED`. | POLICIES §§2–3, 5.3; calibration returns |
| Returned cheque | Recognize `RETURNED ITEM CHK … NSF`, `REFER TO MAKER` and `CHEQUE IMPAYE`; use the cheque number, account, amount and stub reference in cheque-deposit records. | POLICIES §§3, 5.3 |
| Card chargeback | Match masked card suffix, merchant, account, gross order amount and source date to a card-order row. Reverse the individual order, not the whole acquirer settlement. | POLICIES §§3–4; calibration chargebacks |
| Advance deduction | Parse English `Less advance received… Net amount due…` and Spanish clauses. Retrieve a missing invoice by the PDF's exact net amount, party, currency and date; apply the cash with `PARTIAL`. | POLICIES §§3, 5.8; cached English calibration PDFs |
| Cancelled/replaced invoice | Parse English `cancels and replaces invoice…` as well as Spanish. Add a read-only old-reference → replacement index. Require matching cash, entity and chronology. | POLICIES §5.7; cached English calibration PDFs |
| Credit-note netting | Use full/suffix/noisy party-scoped references and signed invoice-minus-credit arithmetic. Also retrieve a credit's documented parent when CN wording is absent. Require a unique exact cash identity. | POLICIES §§2, 5.9; credit-note `related_document` |
| Multi-invoice partial | Resolve at least two distinct printed references. Clear known remaining balances, or older invoices plus an explicitly referenced newer partial. The latter requires a unique newest invoice and a 40/50/60% residual, allowing cent rounding. | POLICIES §§2–3; calibration partial-group shape; competition hypothesis |
| Bank-charge shortfall | Keep cash separate from cleared amount. Use fee wording or a cross-border bank code, a known payer, a unique nearby invoice and both official limits (60 EUR equivalent and 2%). Preserve withholding, discounts and dispute/completion explanations. An explicit invoice plus a round fee can support a payer from a SEPA country choosing a cross-border route. | POLICIES §3; calibration and inspected development exceptions; competition hypothesis where payer-country wording differs |
| Supplier duplicate refund | Require duplicate-refund wording, incoming cash and a supplier identity. Emit `SUPPLIER_REFUND`, without inventing a credit-note allocation. | POLICIES §§3–4 |

PDF amounts accept `1,008.08` and `1.008,08`. Every item amount remains positive and in item currency; credits subtract only in the internal cash equation. Fully cleared foreign-currency invoice rows carry `FX_DIFFERENCE`. Return matching requires original-source evidence and currency/amount agreement.

## Ledger and decision order

Replay bank events in booking-date/ID order, starting from LIVE opening balances. Apply source-linked returns first, followed by refund classification, named service period, replacement, credit netting, documented advance, fee retrieval, referenced partial groups and single-item monetary policies. Carry all chosen allocations through the internal ledger. Return rows reopen balances; duplicates do not consume balances. Deterministic ordering and immutable edition checks make runs reproducible.

This remains a prediction ledger: incorrect incumbent allocations can propagate. V6 therefore uses the ledger to reject closed service candidates and to interpret documented groups, rather than treating it as perfect historical truth. Older TRAIN events outside the cached evaluation subset are not reconstructed. A complete historical TRAIN ledger would be a separate, more expensive experiment.

## Evaluation and release decision

Use the official scorer on the same 7,500 cached January–May 2025 bank lines used for v4/v5. Reconstruct the exact v5 baseline including its archived 24-case LLM review. Record composite score, component metrics, weak-family accuracies and one-rule ablations in `results/development_score.json`. This is an already inspected development fixture, not a fresh blind holdout. Revisions informed by it must be disclosed; small return/fee counts cannot establish LIVE accuracy.

New tests cover locale parsing, replacement templates, month offsets, ambiguous/closed candidates, typed return direction, masked-card merchant/gross checks, full-clearing arithmetic and bounded partial-group reconstruction. Preserve the existing v5 tests. Before publication check actual item IDs, chronology, coverage, duplicates, numeric precision, categories, exceptions and limits; use the bundled official parser too. Its LIVE registry-only validation has no hidden labels, so any synthetic score from that registry is discarded.

Aggregate balance conflicts remain visible diagnostics under the same competition profile as prior editions. They are not upload rejection rules in FORMAT. Compare their full count with v5 rather than hiding them. The upload still blocks on hard contract errors.

## What this does not solve yet

Reference-free large N-to-M groups, payments with missing remittance context and first/last partials whose previous event is outside the observed history remain difficult. Bounded exact netting does not justify searching arbitrary hundreds of invoices until some sum fits. No blanket precision/recall threshold change, ID-to-segment shortcut, fabricated LIVE labels, or promise of a 90 score is used.

The next useful signal is the website's v6 segment and exception feedback. Keep each CSV and its feedback together under `submission/v6-strategy/`. Future LLM judgment can propose a structured fact or candidate for these unresolved cases, but should compete against this reproducible base and be evaluated separately.

## Reproduce

From the repository root, with the existing local archives/catalogs/text caches and the v4 requirements installed:

```bash
python3 version-6/inspect_cases.py
python3 version-6/test_mechanisms.py
python3 -m unittest discover -s version-5 -p 'test_*.py'
python3 version-6/run.py --phase test
python3 version-6/run.py --phase live
python3 version-6/run.py --publish
```

`--rules returns,service` runs a family ablation. No golden file is opened in the LIVE inference or publishing path. The root upload file is `v6-submission.csv`; copies and edition hashes are tracked in `submission/`.
