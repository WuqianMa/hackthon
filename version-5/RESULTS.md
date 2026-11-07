# V5 edition 001 — execution and submission

Website update, 7 November 2026: the user's [pasted website result](../feedback-evaluation/v5_website_feedback_2026-11-07.md) reports **LIVE 79.34**, versus v4 LIVE 79.05. The separate cached development result remains 79.29. [WEBSITE_REVIEW.md](WEBSITE_REVIEW.md) analyzes the families below 50%; no new pipeline was run for that review.

Actual upload file: **repository-root `v5-submission.csv`**. Identical copies are `submission/submission_v5_live_001.csv` and `submission/v5-strategy/submission_v5_live_001.csv`.

| Check | Result |
|---|---:|
| LIVE bank lines covered | 203,083 / 203,083 |
| Rows | 642,703 |
| Uncompressed bytes | 27,774,365 |
| Final decisions changed versus v4 | 1,927 |
| Local hard errors | 0 |
| Official schema | Passed |
| Model retraining | None |
| Bulk PDF extraction | None |

CSV SHA-256: `2e1e6354334d919d3ffffed42244d4ff3045fded370e2d28572075e7c37bda0b`. The v4 model remains `a883a203fc5bc694812895a14cbd8b125870f435a67bc5e7627ab42e4526eccb`; v3/v4 submissions are preserved. The edition JSON preserves the original release snapshot; the later website score is tracked separately above and in the submission feedback file.

## Measured development effect

The same inspected cached 7,500-case fixture was used throughout; these are development/regression results, not a new blind test or a LIVE website score.

| Configuration | Official score |
|---|---:|
| Existing v4 | 79.05 |
| V5 policy/state/recovery overlay | 79.25 |
| Overlay plus bounded LLM pilot | **79.29** |

The pilot selected 24 cases by inference signals/hash before exposing labels: 16 routed cases and eight agreement controls. Independent LLM reviewers made six changes, retained all eight controls, and abstained once. Score uplift is 0.24 over v4 and 0.04 over the non-LLM overlay. This small pilot does not establish a production-wide LLM hit rate.

## Implemented changes

The frozen v4 model's existing output is the incumbent; weights and the 49/81-feature model interfaces are unchanged. New work is an overlay rather than another expensive feature/training run.

- Joint item-currency amount/exception repair for supported AP partials, retention/plans/advances, late discounts, final/release semantics and reliable duplicate history. Keep useful ML item selections and protect v3/v4 agreements from broad policy rewrites.
- Before-event source-based ledger with uncertain speculative history; partials and returns remain legitimate. Replaying LLM-affected components touched 83 items, produced zero further downstream row changes, and did not treat LLM guesses as confirmed prior clearing.
- Cash-pool candidates scoped by account purpose, opposing participant/header flows, funding exclusions, explicit concentration language and the observed RHEI camt ZABA code. No global bank-fee mapping or unique-amount forcing.
- Cached service-period matching, unique exact related-credit netting, replacement references and strongly linked original-operation returns. Generic recovery queries were capped at 6,000; cheap account/code category checks also run directly.

Before LLM revision, 1,904 LIVE decisions changed: 985 cash-pool classifications, 572 source-supported AP partial repairs, 149 document-plan/retention/advance repairs, 108 duplicate-history repairs, 73 late-discount repairs, ten service-period recoveries, three credit-netting recoveries and four other policy/return repairs. Counts describe observable methods, not hidden website segments or proven correctness.

## Actual LLM judgment

LIVE review used **48 cases**, including eight agreement controls, and changed **23 decisions**. Together with development, 72 cases were reviewed in five isolated Codex reviewer batches. Each reviewer saw only its assigned packets, bank/source facts and valid hypotheses; no golden allocations, scores or website segment labels were supplied.

Choices used existing v3/v4/overlay alternatives and a bounded additional item pool. Where PDF text was unavailable, reviewers explicitly described service-month timing as a competition judgment rather than a verified source fact. Valid source-span service-period fact regeneration is implemented and unit-tested; this edition's actual reviews used CHOOSE/KEEP/ABSTAIN, with no factual-regeneration decisions.

Decisions are preserved in `llm/`, bound to exact packet hashes. The pipeline replays these responses; it does not contain an autonomous provider API client. External provider API calls were zero, while the reviewer agents themselves performed the LLM judgment. Their runtime usage/cost is not measured by this Python pipeline.

General LLM tool-directed catalog retrieval, broad N-to-M optimization and broader fact types remain unimplemented roadmap items. No claim is made that this edition exhausts the full proposal or reaches 90 points.

## Validation and evidence

All **33 v5 unit tests** passed (13 policy, ten recovery, ten review-contract tests). Local validation checks IDs, dates, monetary formatting, closed labels, duplicates, coverage and limits. Official schema checking passed using the known bank registry with metric fields discarded, since LIVE golden is unavailable. There were zero amount-contract fallbacks at publication.

The same competition boundary as v3/v4 retains 150 diagnostic aggregate-balance/return-history warnings; these are distinct from hard upload errors. Full records are in `results/` and `editions/live_001.json`, with a tracking copy in the submission folder.

For reproducibility use the existing caches, exact frozen v4 input and stored LLM decisions. Changing data/context invalidates packet hashes. No website upload was performed automatically.
