# Selected V5 strategy — frozen models with policy repair and targeted LLM revision

## Decision and scope

Reuse the trained v4 allocation/payment models, existing catalogs, parsed sources and PDF text cache. **No ML/DL retraining, full-TRAIN feature regeneration, bulk PDF extraction, or new submission run is authorized in this design stage.** No v5 score is claimed. LLM judgment is included in the proposed architecture; no provider calls are made now.

The competition objective is a valid, higher-scoring reconciliation CSV. Permit probabilistic matching and partial allocation credit when they improve the measured composite. Keep the organizer's IDs, currencies, amount semantics, closed labels and submission contract. Do not add real-world approval processes or demand proof of every competition guess.

## Architecture and implementation order

### 1. Repair amount and exception decisions first

Keep the useful ML item ranking. Group allocation variants by item and proposed amount so the item classifier's exception-insensitive target is not interpreted as confidence in a blank exception. Suppress automatically generated blank variants when they contradict a supported retention, partial, duplicate, discount or instalment explanation. Retain legitimate alternatives for final instalments, releases, disputed remainders and other documented completion events.

For the selected item set, jointly determine **item-cleared amount and exception** from applied cash in item currency, terms, source deductions and balance immediately before the event. Changing an exception alone can be wrong: an accepted discount clears the full open amount, whereas a late discount leaves a partial balance. Retention's first payment and its later release also have different state semantics.

Use observable inputs: v3/v4 disagreement, PDF retention/advance/plan facts, booking date versus discount deadline, payment-run/remittance entries, source references, and residual balances. Do not route using hidden website segment labels. Strong v3 source evidence is a useful fallback, not a blanket veto over every ML improvement. Preserve v4's improved AR partial and return decisions unless contradictory evidence exists.

Initially prioritize AP partials, retention and late-discount disagreements. Reuse the existing amount-contract fallback for invalid proposals. Re-encode affected legacy hypotheses with their actual amounts/exceptions where needed; preserve the distinction between raw model scores and final policy decisions in the audit.

### 2. Add an inexpensive episode-state overlay

Stream existing predictions and source-supported events from the opening snapshot; build a small index of affected items and their linked bank lines. This is deterministic replay, not training. Reconstruct balances at the relevant event rather than reading the catalog's final or opening balance as if it were the current balance.

Use high-quality v3 source events and accepted corrections; mark balances influenced by speculative matches as uncertain. Such uncertainty should widen alternatives, not silently consume an item and block later valid matches. Preserve legitimate partial reuse, returns reopening balances, re-presentations and duplicates. Do not impose a one-bank-line-per-item rule.

Use booking chronology and available source order; deterministic ID sorting alone is not proof of within-day causality. Keep same-day ordering ambiguity explicit. For a revised item, replay its connected component through later affected events; include long retention/reversal links rather than applying an arbitrary short window. Full-phase linking may use later-arriving advice as allowed by POLICIES §5.4; validation must use the same offline information scope.

### 3. Widen recall through targeted candidate recovery

Start from missing/uncertain explanations and relevant connected components rather than widening every transaction's pool. Retain the original v3 and v4 outputs as explicit alternatives and leave unaffected decisions unchanged.

| Observable trigger | New candidate work |
|---|---|
| Residual amount, missing source members or credit relationships | Signed invoice-minus-credit groups; preserve complete structured groups and useful partial rows |
| Several bank lines refer to one party/document episode | Bounded N-to-M allocation hypotheses with partial payments and event order |
| Repeated amounts and month language | Resolve bank service period against cached PDF service period, separately from invoice issue month and due date; keep FIFO alternative |
| Return/chargeback/rejected-transfer markers | Link original operation by end-to-end/reference, batch, account, currency, amount and date; recover its original item allocation |
| Cancelled/replaced number or agency/parent payer | Replacement graph and scoped party/alias candidates, including permitted group and payment-factory relationships |
| No reliable party but useful amount/reference/bank evidence | Expand an entity/currency/date-scoped pool; unique amount is a proposal, not automatic acceptance |
| Non-item ambiguity, especially cash pool | Add explicit category alternatives from account relationships, paired flows, bank/format-specific code evidence and narrative |

Expand beyond the additional-item cap only on triggered cases; keep source group members intact. For ordinary ambiguous retrieval, begin with bounded per-channel lists and increase only when useful. Large explicit batches must not be truncated to a generic top-N limit.

Keep existing original-currency matching. Improve its candidate path only where evidence shows a gap. Verify bank-code meanings in bank/format context before adopting category rules; do not turn all codes quoted in an unverified mining note into BANK_FEES.

### 4. Add LLM revision where semantic interpretation is missing

Use the actor in [LLM_REVIEW.md](LLM_REVIEW.md) to interpret cached clauses, choose between plausible alternatives, request scoped retrieval and extract facts that generate new candidates. Reviewing only the top three existing choices cannot recover an item absent from all three. The fact-to-candidate regeneration path is therefore part of v5, not an optional explanation-only feature.

An LLM may choose the best competition hypothesis under ambiguity and record the uncertainty. Factual extraction requires a source span; a judgment requires a reason and valid candidate IDs. Arithmetic, currency conversions, policy amount construction and CSV serialization remain deterministic. KEEP/ABSTAIN leave the incumbent decision intact; they do not automatically emit UNIDENTIFIED.

## Frozen-model compatibility

`version-4/models/train_001.joblib` remains unchanged; SHA-256 is recorded in its JSON manifest. Allocation input is exactly **49 features** and payment input **81**. Do not append bank-code, state or LLM columns to these models. New evidence initially lives in sidecar policy/retrieval/review records.

Existing feature semantics may score expanded candidates, but novel hypothesis families can be out of distribution. Keep those scores advisory; do not silently relabel a new family to impersonate a familiar one or call its confidence calibrated. Preserve the old alpha/bonus configuration initially. Any later cheap operating-point sweep uses existing calibration caches only; it is separate from refitting weights.

## Reuse existing work

| Artifact | V5 use |
|---|---|
| `version-4/models/train_001.joblib` and `.json` | Frozen model and exact schema/provenance |
| `work/cache/pdf_text/` | Existing content-hashed native text; extract structured facts once per document/fact version |
| `work/version-4-train/live/catalog.sqlite` and `catalog_state.joblib` | Read-only item/reference/party context; opening state is not the current ledger |
| `work/version-4-train/live/sources.joblib` | Parsed structured groups and advice |
| `work/version-4-train/live/predictions/` | Existing raw v4 decisions/methods; these caches do **not** contain all candidates, probabilities or margins |
| V3 LIVE CSV and `work/version-3/artifacts/live/evidence.jsonl` | Baseline and chronological source evidence, read selectively |
| `work/version-4-train/shards/` | Existing feature/candidate fixtures for later small validation, without rebuilding TRAIN |
| V4 root/edition CSV and validation records | Immutable benchmark and unchanged complement |

Regenerate only triggered transactions/components. Recovering margins or alternative hypotheses may require targeted frozen-model inference because raw decision caches do not store them. Reusing the model does not mean every future proposal is already scored.

Write derived work to a separate ignored `work/version-5/`; do not mutate shared raw data, weights, v3/v4 outputs or old cache identities. Cache keys should include model hash, bank/context hash, candidate/policy versions and relevant source hashes. An extracted fact can change the candidate set and payment features: invalidate affected feature/score caches, not the whole corpus. Store LLM responses by provider/model/prompt/input hashes. No archives or bulky feature caches belong in Git.

## Cheap staged validation — proposed, not run

1. **Policy overlay only.** Use existing predictions and local episode facts. Begin with a fixed 200–500-case inference-routed development cohort, plus easy agreements and genuine unidentified/lookalike controls. Report changed cases and failures without rebuilding candidate features for unaffected transactions.
2. **Targeted retrieval.** On the same cohort, compare policy-only with expanded source/period/group candidates. Measure correct item/amount reachability separately from successful ranking and complete-case correctness. Recompute only affected legacy feature vectors; do not retrain.
3. **LLM pilot.** Freeze the routing queue before inspecting its labels. Compare the same cases with and without LLM revisions, with all KEEP/ABSTAIN and controls included. See the 200-case/400-call initial cap in LLM_REVIEW.md.
4. **Promotion decision.** Score the full small labeled fixture with an unchanged complement using the official scorer; do not average subset composite scores. Report P/R/F1, transaction accuracy, every supported exception class's P/R/F1, newly correct/regressed cases, missing-candidate recovery and runtime/call counts. Choose on the full composite rather than precision alone. Retain regressions visibly; do not assume better recall justifies every partial/retention loss.
5. **Later full LIVE edition.** Only after implementation/testing authorization and a favorable bounded result, apply approved overlays to the existing full LIVE CSV, plus affected component replay. Validate all bank lines and upload constraints and publish a new v5 edition. No full feature rebuild is a default prerequisite.

The starter and the 7,500-case TRAIN holdout have been inspected; further tuning makes them development/regression evidence. Use existing 2024 calibration material for settings, freeze settings before a separate cached check, and do not relabel repeated tests as a new blind holdout. LIVE feedback supplies aggregate priorities, not per-bank gold labels. Keep an untouched cached time/account slice if available without new extraction, and disclose the remaining selection bias.

The success target is a measured improvement over v4 LIVE 79.05 with usable runtime. **90 is an ambition, not a predicted v5 result.** Provider choice, monetary budget and production-wide LLM capacity are execution-time configuration, not reasons to retrain the models now.
