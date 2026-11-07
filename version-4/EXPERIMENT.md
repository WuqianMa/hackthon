# v4 starter ML experiment

Authorized 7 November 2026. Implement and measure v4 using only the 10 MB starter/docs/master bundle. TRAIN/LIVE are not run. The v3 website-feedback Markdown has not appeared in the local folders or remote q at experiment start; do not substitute starter scores for website feedback. Incorporate the file if/when available.

## Models and target

Two scikit-learn HistGradientBoostingClassifier models: allocation correctness (item + amount within official tolerance), and complete payment-hypothesis correctness (all rows/amounts/exceptions/category). Static v3 supplies an unchanged candidate/baseline; additional party-scoped amount/reference proposals expand retrieval. Candidate generation never reads golden. Labels are attached in the evaluation/training program after candidates are frozen.

Features are numeric evidence and fixed categorical indicators: amount residuals, ratios, reference quality, name/party evidence, invoice/due age, currency, channel, payment-event markers, static proposal membership, competing candidates, proposed exceptions, hypothesis item count and aggregated allocation probabilities. No transaction/item/party ID or scenario/difficulty label is a predictor.

## Starter-only split

Build connected transaction episodes from repeated true item keys and structured payment-container references. Use these groups only to partition data, not as features. Five group-disjoint folds rotate through test (one fold), calibration (one), hypothesis fitting (one), and allocation fitting (two). Hypothesis fitting therefore receives allocation probabilities from a model that did not fit those transactions. Calibration selects an operating point using the official composite; test labels never select it. Every transaction has exactly one held-out prediction in the pooled score.

The starter and its static heuristics were already inspected. This is a grouped development experiment, not a claim of unseen-period generalization. If there are too few independent episodes or poor rare-class support, report that limitation rather than call an in-sample score a test score.

## Comparison and delivery

Score pooled out-of-fold v4 and the unchanged v3 output with the same official scorer over all 8,499 cases, including genuine unidentified controls. Report candidate coverage, model metrics, fold roles, score components, method/exception changes and regressions. Preserve baseline as an explicit decision alternative. Unknown probabilities are not interpreted as a guarantee.

Intermediate datasets/models go under work/version-4. Code, feature definitions, split IDs/hashes, summaries and measured results belong in version-4 and are committed/pushed to q after each completed stage. No v4 LIVE submission is produced in this experiment.
