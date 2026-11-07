# V6 results

The selected cached development score is **81.41**, versus **79.29** for the exact v5 incumbent (**+2.12**). This is not a LIVE website score.

## Same-population comparison

7,500 January–May 2025 TRAIN bank lines, official bundled scorer, no model refit. Rules were informed by July–December 2024 calibration examples and iterated on this previously inspected development fixture. This is development selection, not a blind generalization estimate. Existing v5 LLM decisions are replayed; no new LLM calls.

| Metric | V5 | V6 |
|---|---:|---:|
| Allocation F1 | 86.22% | 86.78% |
| Allocation precision | 90.49% | 90.95% |
| Allocation recall | 82.33% | 82.98% |
| Transaction accuracy | 83.93% | 85.79% |
| Exception macro-F1 | 54.99% | 61.41% |
| Amount-weighted accuracy | 77.31% | 77.73% |

## Weak families

| Family | Bank lines | V5 accuracy | V6 accuracy |
|---|---:|---:|---:|
| ar_same_amount_month | 185 | 43.8% | 91.9% |
| ar_1toN_credit_note | 119 | 42.0% | 60.5% |
| ar_n_to_m | 65 | 3.1% | 10.8% |
| ar_advance_deduction | 8 | 25.0% | 87.5% |
| ar_replaced_invoice | 12 | 16.7% | 58.3% |
| ap_returned_transfer | 8 | 25.0% | 100.0% |
| ar_short_bank_charges | 5 | 0.0% | 40.0% |
| ar_cheque_returned | 2 | 0.0% | 100.0% |
| ar_card_chargeback | 1 | 0.0% | 100.0% |
| ap_duplicate_refund | 3 | 33.3% | 100.0% |

Of 145 changed bank lines, **139 previously wrong transactions became correct**, **0 previously correct transactions became wrong**, and the remaining 6 remain wrong under the official transaction check. See `results/development_changes.json`. Return and fee samples are tiny; their 100% figures are not a LIVE prediction.

## What testing changed

The first service/return/template pass scored 80.73. Referenced partial groups raised it to 80.77. Adding advance retrieval, related-credit recovery and broad fee retrieval reached 80.83, but the fee audit exposed interference with withholding and stale invoices. Restricting fee evidence and preserving existing full-cash/withholding decisions produced 81.41. Date-effective replacement guarding and a final rerun retained 81.41. All one-rule ablations are in `results/development_score.json`; their deltas are not additive.

The selected rules improve mechanisms instead of lowering a global confidence threshold. Large reference-free N-to-M groups remain largely unsolved, and the selected score remains below 90. Do not infer that a more expressive model alone would supply the missing groups.

## Validation and release

12 v6 mechanism tests and 33 existing v5 tests pass. LIVE coverage, official schema validation, file hashes and aggregate-ledger diagnostics are recorded separately on release. The frozen model and all prior edition CSVs are preserved. Website feedback belongs in `submission/v6-strategy/feedback.md`.
