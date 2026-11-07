# v3 starter experiment results

7 November 2026. Actual execution on the complete 8,499-transaction starter sample, with the unchanged official scorer. TRAIN/LIVE/FINAL were not read or run for this stage. These are inspected development-data results.

| Metric | Baseline | Selected v3 aggressive |
|---|---:|---:|
| Official score | 71.32 | **78.65** |
| Allocation F1 | 79.3908% | 84.6947% |
| Pair precision | 99.5980% | 95.6708% |
| Pair recall | 66.0002% | 75.9780% |
| Whole-transaction accuracy | 75.9383% | 85.3983% |
| Exception macro-F1 | 44.2233% | 53.4209% |
| Coverage | 8,499/8,499 | 8,499/8,499 |
| CSV rows | 26,030 | 29,702 |
| Unresolved | 1,721 | 710 |

Gain: **7.33 score points**. The winning profile takes approximately 12 seconds with prepared PDF text. Export rows are canonically ordered for reproducibility. Eleven new mechanism tests and 30 existing tests pass. The manifest includes all v3 module hashes, runtime and input hashes; `results/` retains the actual scorer, validation, manifest and comparison JSON.

## Experiments and selection

1. Initial broad prefix emission: 76.54 in a diagnostic official scorer call, but local validation failed on an aggregate balance conflict. It was not published as a successful output. Broad prefixes also generated excessive false item rows.
2. Balanced candidate after correcting the conflict, stronger partial references, mandate returns and anchored residuals: 77.85; local validation passed.
3. Explicit speculative profile, deferring weak hypotheses from balance mutation: 78.37; upload-contract checks passed. Added cross-bank balance diagnostics are warnings in this profile, as documented in POLICY.md.
4. Add the confirming maturity grouping level: **78.65**, selected; all official sample validation checks pass. No newly achieved 90+ score is claimed.

Each retained experiment is evaluated on the entire sample, including genuinely unidentified transactions. The implementation does not use golden labels to decide which cases to guess. Experiments were developed while observing this sample, so this is model/strategy selection on development data rather than an independent holdout.

## Gains and regressions

- Supplier credit refunds: 33.33% → 100% transaction accuracy.
- Instalments: 47.31% → 86.56%.
- Noisy references: 75.27% → 89.00%.
- Confirming: 0% → 46.27%.
- Multi-invoice text: 46.70% → 74.50%.
- Invoice/credit netting: 20.60% → 39.20%.
- DD returns: 28.22% → 40.10%.
- Genuine unidentified: 100% → 88.82%; unidentified lookalikes: 100% → 92.42%. Aggressive matching loses some correct abstentions.

The higher score therefore involves a real precision/recall tradeoff. Speculative cross-bank balance conflicts are disclosed in validation warnings; they are not assertions of a fully consistent accounting ledger. The CSV still has valid phase/item IDs, allowed labels, canonical fields, numeric values and coverage, and is accepted by the official sample scorer.

## Apply or continue?

**Keep v3 as the improved starter development candidate; continue before applying to TRAIN/LIVE.** The 90+ development gate remains unmet. N-to-M accuracy is still 9.80%, netted groups are incomplete, many confirming and returned-payment events remain unresolved, and exception macro-F1 is only 53.42%. A fully implemented phase-wide conflict pass and richer payment schedules/return links are still pending.

The experiment validates that broader hypotheses and explicit source relationships improve this baseline. It does not establish that every part of the review's architecture is implemented or that this operating point will generalize. Next sample work should target residual complete-group recall and event interpretation, including the genuine-unidentified regression, rather than simply increasing prefix guesses further.

Reproduce: `python3 -m v3 --speculative`. Selected artifact: `final_submission/v3/sample/submission.csv`. No challenge upload was made.
