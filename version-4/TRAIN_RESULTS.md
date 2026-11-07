# V4 TRAIN result — frozen model, no LLM judgment

7 November 2026. The official scorer gives **79.05** on the January–May 2025 temporal holdout, versus **73.34** for static reconstruction on the same **7,500 transactions**: **+5.71 points**. All held-out transactions are represented. This is a local TRAIN result, not a LIVE website score and not a whole-TRAIN score.

## What was trained

The full checksum-verified TRAIN archive was scanned: 1,489,931 bank lines, 3,963,735 AR invoices, 1,530,203 AP invoices and 150,215 credit notes. The disk catalog retains all invoice history and indexed PDF facts; 125,116 invoice PDF records resolved to a unique indexed item. A separate cache pass processed 148,306 invoice/advice PDFs. Ambiguous or unindexed PDFs are not claimed to have yielded item facts.

Select 1,500 bank lines per month by the smallest SHA-256 hash of `v4-train-42:<bank_txn_id>`, without consulting labels, segments or difficulty. Across 47 months this yields 70,500 transactions before episode purging. June 2025 is excluded because the starter was already inspected. This is bounded supervised fitting across TRAIN, rather than fitting all 1.49 million bank lines.

| Role | Period | Transactions after purge |
|---|---|---:|
| Allocation model | July 2021–December 2023 | 44,986 |
| Complete-payment model | January–June 2024 | 8,984 |
| Calibration | July–December 2024 | 8,989 |
| Temporal test | January–May 2025 | 7,500 |

Remove 41 earlier-role transactions sharing a true item with a later role. These labels define the split and supervision, never predictive features. The payment model receives allocation probabilities from a model that did not fit that period. Fit **2,047,316 allocation candidates** and **45,788 complete-payment hypotheses** with two HistGradientBoostingClassifier models: 100 iterations, 15 leaves, learning rate 0.08, L2 2, minimum leaf size 30, seed 42. Allocation features: 49; payment features: 81. IDs, golden segment and difficulty are excluded as predictors.

The 2024 calibration grid selects **alpha 0.75, static bonus 0**, scoring **78.73**, versus static **72.87** on those calibration cases. A static-only fallback was included before test evaluation. Freeze the resulting model bundle before scoring the temporal test; the bundle hash remains unchanged through evaluation and is the model applied to LIVE.

The fitted artifact is `models/train_001.joblib`, with its checksum, feature schemas, source hashes, library versions and catalog inventory in `models/train_001.json`. The printed positive counters in the first training log overflowed NumPy int8 accumulation; this affected diagnostics only. The binary target arrays and fitting were unaffected. The counter now uses int64 accumulation.

## Official held-out metrics

| Metric | Static | V4 |
|---|---:|---:|
| Composite score | 73.34 | **79.05** |
| Allocation F1 | 79.12% | **86.19%** |
| Pair precision | 77.54% | **90.46%** |
| Pair recall | 80.77% | **82.30%** |
| Whole-transaction accuracy | 79.68% | **83.31%** |
| Exception macro-F1 | 49.37% | **54.82%** |
| Amount-weighted accuracy | 76.09% | **77.24%** |

There are **296 newly correct transactions and 24 regressions**, a net gain of 272 complete decisions. The official scorer's amount-weighting fallback uses item-currency allocations because the bank table lacks `amount_eur`; it is not a reconstructed EUR-cash metric and does not change the composite formula.

| Segment | Test cases | Static accuracy | V4 accuracy |
|---|---:|---:|---:|
| Same-amount FIFO | 236 | 14.41% | 45.34% |
| Named service month | 185 | 15.14% | 39.46% |
| AR partial | 139 | 41.01% | 64.03% |
| Genuine unidentified | 127 | 74.80% | 97.64% |
| Unidentified lookalike | 41 | 70.73% | 87.80% |
| DD returned | 130 | 63.08% | 72.31% |
| AP partial | 111 | 85.59% | 79.28% |
| Retention | 35 | 68.57% | 60.00% |
| N-to-M | 65 | 6.15% | 3.08% |

Small segments are noisy: the advance-deduction regression is one transaction out of eight, and short-bank-charge accuracy is zero on five cases. Full segment metrics and baseline results are retained in `training-results/held_out.json`.

## What this result establishes and its limits

The learned decision layer improves this fixed evaluation, especially precision, unresolved receipts and repeated-amount choices. It does not establish a LIVE score, an optimal model family, or achievement of the 90-point target. The starter result 80.95 and static v3's user-reported LIVE score 77.46 belong to different evaluation populations.

Only **22,383 of 26,528** golden test item/amount pairs occur correctly in the candidate pool: **84.375% coverage**, leaving **4,145 absent pairs**. A better ranker alone cannot recover those missing proposals. N-to-M episodes, duplicate history, replacement interpretation, rare charge/return exceptions and non-item category alternatives remain weaknesses. Cash-pool accuracy is 28.33% on 60 cases; payroll accuracy is 36.84% on 19. The current model cannot invent a missing category or allocation hypothesis.

Static TRAIN history replays sampled bank transactions only. Its ledger is incomplete; notably, many old invoices remain apparently open. LIVE has its actual opening snapshot and the existing full chronological static edition, so the +5.71-point gain must not be added mechanically to the earlier LIVE score. Non-static alternatives use opening amounts and do not see an end-of-month predicted ledger. Source windows, current master snapshots, shared customers, and a strategy previously developed on the June 2025 starter limit a strictly causal/generalization interpretation. The test labels did not choose parameters or calibration, but this is not a preregistered blind competition test.

## LIVE application and reproduction

Apply this same frozen bundle to all 203,083 LIVE bank lines using the verified LIVE archive, its opening snapshot, structured sources and PDF clauses. **No LLM calls or judgments** contribute. Keep the output under `submission/` and `submission/v4-strategy/`; website feedback remains pending until the user uploads the CSV.

```sh
python3 -m pip install -r version-4/requirements.txt
# Rebuild the training experiment, evaluate, then generate LIVE:
python3 version-4/train_live.py
# Apply the preserved trained artifact without opening TRAIN:
python3 version-4/train_live.py --mode live --workers 3
```

Machine-readable evidence: `training-results/split.json`, `calibration.json`, `held_out.json`, `training_sample.json`, plus the parser/parallel-validation records. Working catalogs, features and detailed held-out predictions remain under ignored `work/version-4-train/`.
