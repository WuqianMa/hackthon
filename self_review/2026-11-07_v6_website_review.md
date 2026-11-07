# V6 website follow-up review

Observed source: the user's LIVE website report, transcribed in `feedback-evaluation/v6_website_feedback_2026-11-07.md`. No new experiments, evaluation runs, model fitting, tests, LLM calls or solver changes were performed for this follow-up.

The release improves LIVE from v5 79.34 to **81.39** (+2.05), broadly matching the direction and magnitude of the already recorded development gain (+2.12). This supports further source/template mechanism recovery. Similar final scores across two different populations do not establish generalization calibration or prove every module correct.

Exception macro-F1 improves 52.9% → 60.3% and drives about 72% of the displayed weighted gain. Both precision and recall increase, so there is no observed aggregate precision/recall sacrifice in this release. Recall remains 77.7%, meaning high precision alone cannot carry the score to 90. Amount-weighted accuracy improves only 0.1 pp.

The intended service-month, return, advance, replacement and fee families all improve. Only credit-note groups (47.7%) and N-to-M (24.1%) remain below 50%; they require broader coherent group candidates and better observed balance/source context. A higher-capacity ranker over the same candidate pool would not resolve that limitation. Reference noise remains the largest approximate error pool by transaction volume.

The LIVE report also exposes small discount/instalment regressions absent from the 7,500-case development fixture. Future mechanism changes need these as explicit controls. A joint allocator must allow residual open balances rather than forcing every episode to close. LLM judgment should target missing semantic facts in cached source documents after candidate expansion, with separate measured contribution.

Files changed in this stage: feedback transcription/tracking, website review, result/readme references, AGENTS working direction and this review. Solver code, all submission CSVs, trained weights, tests and original release snapshots remain unchanged. Next execution is a user decision; this stage does not implement v7.
