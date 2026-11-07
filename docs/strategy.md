# Codex strategy proposal — sample-first development

Status: proposed, awaiting the user's strategy decision and comparison with Claude/Gemini. Date: 7 November 2026. Baseline: Git tag `v0.1.0-baseline`, commit `17ce829`. This document supersedes the earlier report's development sequence; it does not authorize a solver change or a pipeline run.

Latest starter-only diagnosis: `../self_review/2026-11-07_why_71_and_path_to_90.md`. It traces the 71.32 score to concrete grouping, relationship, parser and document-event failures. The development target is now **90+ on the starter before selecting a residual TRAIN/model task**. That target is not yet an achieved result. The diagnostic reads frozen sample output and selected starter sources; no solver or large-phase run was performed.

## Objective and immediate scope

The eventual product remains a deterministic compressed-input-to-submission system, expandable for agents. The immediate objective is to choose the design through fast feedback on the smallest starter/sample dataset. The current code is a reproducible initial version, not the selected final architecture.

Use the existing docs/master archive and saved sample results now. Run a focused experiment only when that experiment or its implementation is requested. Keep full TRAIN for a justified model-training step, with its task and split defined first. Whole LIVE/FINAL or corpus-wide benchmarks belong to a later production-readiness decision rather than routine design exploration.

The available sample is already inspected development data. Its result must be described that way. Fast feedback and independent evidence of generalization are different needs; using a smaller dataset saves iteration time but does not remove overfitting risk by itself.

## Architecture I recommend

Keep the verified archive reader, normalized input tables, indexed references, structured-source parsers, integer-cent arithmetic, official scorer and strict exporter. SQLite remains adequate until a measured bottleneck justifies a storage change. I do not recommend adding ML, a global solver or runtime agents by default.

The main proposed change is to separate **facts, candidates, decisions and ledger events**:

| Layer | Responsibility | Required output |
|---|---|---|
| Facts | Parse bank lines, documents, party references, opening balances and clauses. | Source path/hash, original fields, extracted fact, parser version and known/unknown status. |
| Candidate generation | Retrieve plausible items and whole document groups through multiple evidence channels. | Candidate set with supporting and contradictory evidence; completeness information. No balance mutation. |
| Decision and policy | Check party/entity/date/currency, full group cash explanation and policy-specific eligibility; resolve conflicting proposals. | An accepted complete proposal or an explicit reason for uncertainty. No single-item excess inference from an incomplete group. |
| Ledger | Apply accepted clearings, partials, returns and duplicates in a defined temporal sequence. | Auditable balance events and state provenance. |
| Export and evaluation | Write all bank IDs with exactly the official fields; validate; score requested sample experiments. | Submission plus internal unresolved/evidence artifacts and comparable metrics. |

For example, cash of 1,200 with one recovered invoice of 1,000 may be an overpayment or a payment that also includes an unrecovered 200 invoice. The amount difference alone does not distinguish them. The candidate layer should retain this ambiguity; the decision layer should require evidence that the proposed item set is complete before applying the overpayment policy.

A two-stage decision process is my current recommendation: establish strongly referenced structured groups first, then consider weaker reference/party proposals against the remaining state. Reserve or detect conflicts explicitly before committing ledger events. This is a proposal to test; it is not yet proof that two passes outperform the current chronological waterfall. Start with deterministic evidence tiers, not a large optimization dependency.

Unknown history must be explicit. The absence of a prior payment from the sample does not establish an unpaid opening balance, and current master terms do not establish the historical invoice's discount terms. Cases depending on unavailable history should have an internal reason code rather than a fabricated accounting story.

## What should remain static and where a model could help

The static system owns source integrity, identifiers, money, currencies, official policies, group totals, balances, conflicts, coverage and final CSV generation. Structured payment files and normal reference joins should remain deterministic.

A future model needs a narrow task with observable labels: for example, rank a bounded ambiguous candidate set, classify a residual non-item narrative, or extract a specific fact from an unsupported advice/PDF layout. Before using TRAIN, state the feature/input schema, target, baseline, model complexity, labeling plan, temporal/group split, inference cost and abstention rule. Avoid adding a model when the correct item is absent from the candidate set; a ranker cannot recover an ungenerated candidate.

A future agent should initially help offline: review errors, suggest general parsers and extract evidence-backed facts. If runtime review is chosen later, use only bounded residual packets and cached outputs. A provider must receive read-only context and propose facts/candidates, with checkable source spans. Source hashes alone do not establish semantic truth. Agents never directly own clearing arithmetic or the final CSV. No runtime agent use is currently selected.

## Fast feedback without pretending the sample is unseen

For each requested change, write a short experiment card before editing:

1. **Hypothesis:** one mechanism and one alternative explanation. Example: incomplete document sets are being passed into single-item overpayment inference.
2. **Scope:** exact code module and smallest relevant fixture. Use the supplied sample, or a tiny source-derived fixture that preserves its related transactions/items/documents.
3. **Expected effects:** complete-transaction behavior, per-exception precision/recall, pair recall and possible regressions. Set criteria before reading new results.
4. **Verification:** meaningful boundary/counterexample checks plus the sample scorer only when the experiment requires it. Do not rerun a whole phase merely to test a parser or discuss architecture.
5. **Record:** base commit, input hashes, command, result, tradeoffs, uncertainty and keep/revert/defer decision.

Suggested small invariance checks include changing non-semantic item IDs consistently, reordering source rows/files, adding an unrelated same-amount invoice, and changing currency/rate/discount deadlines around policy boundaries. Do not arbitrarily reorder causally related payment events and call changed ledger results a defect. These checks test specified properties, not distributional generalization.

If diagnostic sample partitions are useful, keep a complete bank transaction and its allocation rows together; preserve related batch/party/payment-history context. A row-level random split can fragment the task. Because this sample has already informed development, partitions are diagnostic rather than blind holdouts. Keep empirical patterns separate from policy/schema rules and resist customer-ID-specific fixes.

When model training is selected, use an appropriate time/group split within TRAIN and keep the model's evaluation labels out of features and rule tuning. That later task is distinct from today's architecture comparison. Do not make a full-corpus score a prerequisite for choosing a parser or reviewing the current static design.

## Metrics for each requested experiment

Use the unchanged official composite and component definitions. The local source establishes 50% allocation F1, 30% transaction accuracy and 20% exception macro-F1. Do not replace this with a newly invented score or average scenario scores to estimate the global result.

Report the scope and input/evaluator version, validation/coverage, pair precision and recall, whole-transaction accuracy, per-exception precision/recall/F1 with support, and runtime at the stated scope/cache state. Treat amount-weighted accuracy according to the scorer's actual weights. The current bank tables lack `amount_eur`, so its fallback metric is not established as EUR-weighted cash accuracy.

Candidate recall, document-count/total reconciliation and source-evidence coverage would be valuable new instrumentation if selected. Mark these as **not currently measured**. They should help distinguish missing candidates from ranking, group-completeness, history, amount and exception errors.

The saved sample has high pair precision but lower recall and exception macro-F1. It supports prioritizing candidate completeness and exception evidence over blanket suppression of allocations or aggressive guessing. It does not establish that every low-recall scenario has the same cause.

## First code editions I would propose, after comparison

| Order | Proposed edition | Smallest useful evidence | Overfitting control |
|---|---|---|---|
| 1 | Correct available structured evidence: email deduction fields, parent-payer scoping and confirming subdivisions. | The concrete starter counterexamples in the latest diagnosis, valid controls and advice-total reconciliation. | Source/schema rules and recorded relationships; no customer-specific answer tables. |
| 2 | Preserve related credits and recover complete payment groups before inferring overpayment; separate proposals from ledger mutation. | The 12,097 absent required keys and 228 false-overpayment cases with multi-item goldens, evaluated through a focused sample experiment. | General completeness/evidence conditions, explicit conflicts; no tuned excess-percentage accounting rule. |
| 3 | Interpret PDF/bank event facts and track unknown history, including final instalments, retention/advance and service month. | Small related fixtures with actual starter clauses and boundary cases. | Use present evidence; unknown remains unknown; no golden-derived runtime history. |
| 4 | Reassess the residual task once the starter score is high enough; target 90+ during development. | Measured candidate/evidence error taxonomy and official sample components. | Define the residual model task and TRAIN split before training; inspected sample performance is not unseen performance. |

The user may select a different order or architecture after considering the independent proposals. The next action is comparison and a decision, not executing this table automatically.

## Proposal comparison and decision

Keep separately attributed proposals in `../strategy_proposals/`. Compare assumptions, policy/source grounding, complete-transaction treatment, history model, overfitting controls, smallest experiments, runtime/dependency cost, model/agent role and migration effort. Do not select by the largest claimed sample score, particularly when authors used different data scopes or already inspected labels.

`../strategy_proposals/decision.md` records the current open decision and will identify the selected design and next requested experiment when the user chooses. Preserve baseline code and historical results so later editions have a real point of comparison.
