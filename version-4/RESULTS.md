# Measured starter ML result

**80.95 / 100**, compared with **78.65** static v3 on the same 8,499 transactions: **+2.30 points**. Official scorer unchanged. No TRAIN/LIVE input, deep network or LLM revision was used.

| Metric | Static v3 | v4 GBDT |
|---|---:|---:|
| Allocation F1 | 84.6947% | 87.9756% |
| Pair precision | 95.6708% | 94.6454% |
| Pair recall | 75.9780% | 82.1840% |
| Transaction accuracy | 85.3983% | 86.5984% |
| Exception macro-F1 | 53.4209% | 54.8963% |
| Coverage | 8,499 / 8,499 | 8,499 / 8,499 |

155,091 label-free allocation proposals, 49 allocation features and 81 payment features. Fitting/evaluating from frozen cached candidates takes approximately 16 seconds locally, excluding preparation. Fitted models are local under work/version-4/models; their hashes are recorded.

## Split and model stack

8,207 connected split groups, largest 27 transactions, are built from repeated golden item keys solely for partitioning. Each test fold is separate from allocation fitting (two other folds), payment-model fitting (another fold) and calibration (another fold). The payment model never fits in-sample allocation probabilities. Each transaction has exactly one held-out prediction.

| Test fold | Cases | Static | ML |
|---|---:|---:|---:|
| 0 | 1,700 | 76.45 | 78.38 |
| 1 | 1,700 | 82.29 | 84.71 |
| 2 | 1,700 | 77.55 | 80.35 |
| 3 | 1,700 | 80.61 | 82.56 |
| 4 | 1,699 | 76.22 | 78.53 |

All five folds improve. The global score comes from pooled predictions, not averaging fold scores. This is an inspected starter development experiment: static rules had seen the whole sample, and whole customers/source containers are not additionally held out. It is not a blind temporal evaluation.

## Gains, regressions and limit

155 newly correct transactions and 53 regressions yield a net gain of 102. Dispute settlement improves 58.49% → 84.91%, AR partial 40.80% → 62.64%, and retention release 38.64% → 56.82%. Regressions include instalments 86.56% → 79.57%, AP partial 86.11% → 73.61%, and late discounts 79.49% → 66.67%. The learned decisions improve the aggregate but do not dominate every static family.

Only **30,338 / 35,659 required item/amount pairs (85.08%)** exist in the frozen candidate pool. No ranker can select the absent 5,321 pairs. More complete groups and exception/event alternatives are needed. Exception macro-F1 remains only 54.90%; the 90+ target is not met.

## Tier 3 and next decision

The user selected the three-tier hybrid and permitted LLM revision. Inference signals identify 1,125 eligible cases; 200 evidence packets are exported without golden/segment labels. The adapter validates candidate choices and separates new facts from direct allocation edits. **Zero external LLM calls occurred; no tier-3 gain is claimed.** Inspection of initial packets shows some lack a complete explanation among the supplied hypotheses, requiring new facts/candidates rather than merely another ranking choice.

Next data source: TRAIN under STRATEGY.md, starting with a bounded fitting pilot and preserving later temporal evaluation. This stage produces neither a production-fitted TRAIN model nor a new LIVE submission.

## Artifacts

Official score and baseline, per-fold scores, feature definitions, split assignments, model/source/input hashes and validation are in results/. Local contract validation passes; aggregate balance warnings remain disclosed diagnostics as in v3's competition profile. `results/submission_v4_sample_oof.csv` is **sample-only, not for LIVE upload**. Repeated complete training/evaluation runs reproduce the same CSV hash. Seven new tests cover label correctness, split/stack isolation, selection and the tier-3 revision boundary.
