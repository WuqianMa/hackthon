# Selected v4 strategy — 7 November 2026

Execution update: the user authorized TRAIN fitting and full LIVE application **without LLM judgment**. The frozen TRAIN model scores **79.05** versus static **73.34** on the same 7,500 temporal test cases. Fitting/calibration/test use 70,500 deterministic sampled cases before purging; the full invoice context is indexed. See [TRAIN_RESULTS.md](TRAIN_RESULTS.md) and [TRAIN_EXECUTION.md](TRAIN_EXECUTION.md). The optional tier-3 design below remains future work and is disabled for this submission edition.

The original selection included three tiers and permitted LLM revision. The starter stage below preceded TRAIN fitting; no external LLM contribution is included in either measured ML result.

## Tier 1: static reconstruction

Verify archives, parse source files, retain IDs/currencies and document relationships, construct payment hypotheses and calculate policy-consistent amounts. Static v3 remains an explicit candidate. Models choose explanations rather than invent monetary values or closed-list labels.

## Tier 2: learned decisions

Current choice: two gradient-boosted tree classifiers, implemented with scikit-learn HistGradientBoostingClassifier. One predicts correct item/amount pairs; the second predicts complete transaction correctness from group features and allocation probabilities. Starter configuration: 100 iterations, 15 leaves, learning rate .08, L2 2, minimum leaf size 30, seed 42; 49 allocation and 81 payment features. This is a fixed initial model, not an optimal-configuration claim.

No transaction/item/party IDs, golden segment/difficulty or labels are predictive features. Calibration uses the actual official composite to choose the mixture of whole-payment probability, estimated pair-F1 and static bonus. Partial hypotheses remain eligible for competition credit. Genuine unidentified cases participate in evaluation.

Tree models are the first choice because the structured-data experiment improves by 2.30 points. DL remains a later comparison for multilingual text, documents or payment history; a bigger model is not presumed better.

## Tier 3: LLM revision actor

Route cases with close alternatives, low whole-payment probability, static/model disagreement, unexplained residuals or missing document meaning. Queue selection uses inference signals, never knowledge that a case failed golden evaluation.

Packets contain bank text, bounded candidate hypotheses, dates/currencies, relationship facts and relevant source excerpts/paths. Allowed actions: KEEP, CHOOSE an existing hypothesis with reasoning, EXTRACT_FACT with a source span for static regeneration, or ABSTAIN. Candidate choices must belong to the packet; no fabricated IDs, currencies, amounts or labels. The initial selection adapter and queue exist; automatic fact regeneration and provider integration do not yet exist.

Compare ML-only against ML+LLM on the same preselected held-out queue. Record newly correct/regressed cases, official score change, calls, latency and cost. The model/provider and revision budget remain to be configured. **80.95 is ML-only.** The actor may make competition guesses, but its self-reported confidence is not a correctness guarantee.

## TRAIN protocol

Start with a bounded fitting pilot to measure feature throughput, then expand deliberately. Do not automatically run the entire corpus as a side effect of deciding the strategy.

| Role | Period |
|---|---|
| Fit parameters | July 2021–December 2023 |
| Select features/model settings | January–June 2024 |
| Calibrate output and tier-3 routing | July–December 2024 |
| Locked temporal evaluation | January–May 2025 |
| Inspected starter regression fixture | June 2025 |

Preserve transactions and related episodes; derive historical state only from permitted preceding information. Attach targets after independent candidate generation. Use disjoint/out-of-fold allocation probabilities when fitting the payment model. Keep locked evaluation untouched. Add a separate parent/customer-group stress split. Document master-snapshot limitations; a late master snapshot is not automatically historically causal.

The starter folds isolate repeated true-item episodes, not entire customers or all source files. Static rules already saw this sample. Its score is development evidence, not a future-period estimate. Only 85.08% of required pairs are available in the current candidate pool, so more data must improve retrieval/document interpretation as well as decision training. An LLM is useful where an extracted source fact can create a missing hypothesis.
