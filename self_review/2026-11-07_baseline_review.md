# Baseline self-review — 7 November 2026

Author: Codex. Base: `17ce829`, tag `v0.1.0-baseline`. Scope: saved-result interpretation, static code inspection, development workflow and the next proposed design. No pipeline, scorer, model training or test suite was run for this review; quoted results come from existing artifacts.

## 1. What the feedback establishes

The supplied `feedback-evaluation/final_evaluation_metrics_reference.md` explains metrics and comparison methodology. It explicitly does not assess a particular submission or authorize experiments/solver modifications. It cites a separate repository snapshot with `bankrec-improved/`; that code is not part of this local baseline. I must not attribute its implementation or results to this project.

Its statement that official scoring weights were unavailable applies to that guide's source scope. Here the verified archive contains `starter/bankrec_score.py`: `W_ALLOC=0.5`, `W_TXN=0.3`, `W_EXC=0.2`, with the amount tolerance in `_tol`. The supplied guide is useful for interpretation; the local official scorer remains the authority.

The useful review principles are: distinguish pair matching from complete transactions; examine per-exception support and precision/recall; treat weighted accuracy according to its actual weights; compare like-for-like populations; and do not infer causation or generalization from aggregate results.

## 2. What I got wrong about the workflow

I advanced from sample exploration to a full LIVE run before the architecture comparison. That gave an operational compatibility measurement, but was not needed to decide the strategy. The next step should have been a clear proposal and focused sample feedback.

I also proposed broad TRAIN evaluation/history hydration too early for the user's intended loop. Full TRAIN may later support a model and a deliberately designed validation split. It is not the default cost of discussing a static matcher or checking a parser hypothesis.

The baseline's tests and sample score are useful implementation evidence. They do not settle the overfitting question. I inspected the sample and its errors while choosing rules, so the 71.32 score is a development result. A new split of that already inspected sample cannot retrospectively make it blind.

## 3. Saved results, interpreted narrowly

Sources: `reports/sample_score.json` and `reports/sample_error_analysis.json`.

| Saved measurement | What it supports | What it does not establish |
|---|---|---|
| Pair precision 99.598%, recall 66.000% | Most emitted item/amount pairs pass the scorer; many required pairs are absent. | 99.6% of transactions, exceptions or cash explanations are correct. |
| Whole-transaction accuracy 75.938% | Roughly three quarters of sample cases pass the full case check. | Similar future-period accuracy. |
| Exception macro-F1 44.223% | Exception handling remains a separate weakness. | One common exception explains every error. |
| Overpayment: 239 predicted rows, 24 golden rows, 8 correct exception keys | Strong evidence of overprediction; precision is 3.347%. | The exact root cause of all 231 false-positive keys without tracing cases. |
| 1,721 unresolved lines; 218 true unidentified keys recovered | The fallback preserves coverage and is also used on many solvable cases. | All fallback receipts have no legitimate item. |
| Weighted accuracy 60.609%, below transaction accuracy | Cases with higher scorer weights are less accurate in aggregate. | A verified EUR cash-loss measure; the scorer uses fallback allocation weights here. |

Using only saved scenario counts and accuracies, approximate incorrect-case volumes are 533 for noisy references, 186 for multi-invoice text, 158 for netted credit notes, 145 for DD returns and 129 for AR partials. These are diagnostic priorities, not predicted score gains. They do not replace per-exception priorities, and overlapping future slices must not be summed.

## 4. Concrete code findings for a future edition

These are review findings and proposed changes, not completed fixes.

| Priority | Code and observed behavior | Risk or hypothesis | Proposed correction after strategy selection |
|---|---|---|---|
| High | `bankrec/engine.py:296` attributes the whole same-currency bank amount to one item; `:247` can fall back from a non-reconciling document set to one ranked item; `:106` then labels any excess as overpayment. | An incomplete multi-item candidate can look like a single-invoice overpayment. Saved overpayment precision supports investigation, but case traces are still needed. | Require completeness evidence before this inference; preserve incomplete groups explicitly. Keep the official full-open-amount rule. |
| High | `bankrec/engine.py:335` takes the first available route and `:338` immediately mutates balances. | A weaker early result can consume an item needed by stronger later evidence. No ablation yet quantifies the effect. | Generate proposals separately; reserve stronger supported groups and resolve conflicts before committing events. |
| High | `bankrec/catalog.py:80` initializes sample items at total amount; `:102` falls back to current party terms for opening items. | Missing history and missing invoice-specific metadata can become unsupported balance/discount assumptions. | Represent metadata/history certainty explicitly. Use a small historical fixture only for an agreed history hypothesis; do not infer history from the sample score. |
| Medium | `bankrec/engine.py:119` treats eligible country plus a rate-shaped shortfall as withholding evidence. | Official rules apply to certain customers; country alone does not establish certificate-backed withholding. | Require explicit customer/document evidence or keep the case uncertain. |
| Medium | `bankrec/engine.py:331` accepts category regexes before structured evidence. | Broad words such as fees/interest/refund can mask an item settlement or a credit-note refund. | Make category results proposals with evidence/scope, and check incompatible item evidence. |
| Medium | `bankrec/engine.py:272` chooses FIFO on same-party equal amounts while extracted service-month facts are not used here. | Valid FIFO policy can be misapplied when a service month is stated. | Add the month-evidence discriminator before FIFO, using general facts rather than customer-specific exceptions. |
| Medium | `bankrec/validate.py:15` checks format, catalog/date constraints and balance replay. It does not independently prove every transaction's cash explanation or exception eligibility. | A passing validation result can be mistaken for a complete accounting proof. | Keep format validation separate from a semantic decision audit; report which invariants were checked and which are unknown. |
| Future agent integration | `bankrec/engine.py:65` passes a mutable catalog to providers; `bankrec/extensions.py:41` verifies a path/hash/description, not the truth of the extracted statement. | The current seam is a trusted-code extension point, not isolation for untrusted model output. No providers are registered now. | Supply read-only bounded context and structured facts with checkable source spans; retain static policy/arithmetic ownership. |

## 5. Overfitting risk in the current strategy

Policy arithmetic, CSV contracts, stable source schemas and signed credit arithmetic are reusable foundations. The weaker parts are empirical narrative regexes, suffix aliases, candidate ranking weights, time windows and search bounds chosen without a controlled comparison. These should have explicit provenance and a stated mechanism, not be treated as official policy.

Determinism and 30 previously passing tests establish repeatability and some invariants. They do not demonstrate robustness to different customer aliases, document layouts, currencies, history or phase drift. Increasing the sample score through more customer-specific regexes would not resolve that problem.

The next design should prefer evidence completeness, correct source interpretation and shared accounting rules. A sample-only check can quickly falsify a bad design, identify a regression and compare costs. It cannot prove future performance. This limitation should remain visible even if the sample score rises.

## 6. My proposed strategy

Keep the static archive/index/policy/export foundation, but evolve matching toward evidence-backed transaction proposals before ledger mutation. Use the sample to test a single mechanism at a time, track complete-case and per-exception effects, and add small invariant/counterexample fixtures. Introduce a trained model only after defining the residual task it would solve. Use agents later to interpret evidence or propose reusable parsers, with static verification and export.

The full recommendation and experiment protocol are in `../docs/strategy.md`. It is Codex's proposal, pending comparison with the user's Claude and Gemini proposals. Solver code and saved outputs remain unchanged in this review edition.
