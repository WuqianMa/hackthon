# Strategy v3: competition payment hypotheses

User-selected implementation experiment, 7 November 2026. Input for this stage is only the verified 10 MB docs/master/sample archive. The unchanged official scorer is the objective: 50% allocation F1, 30% complete-transaction accuracy, 20% exception macro-F1. Baseline is 71.32. Target is 90+, subject to measured results.

## Review assessment

The Gemini-folder review correctly unifies missing retrieval and oversimplified event representation. Adopt payer/debtor separation, signed credit relationships, parsed settlement units, nested payment groups and partial group recovery. Its warning about an oracle-selected guessing experiment is sound: evaluate the complete sample, including true unidentified lines, rather than selecting only errors by golden labels.

The document's own attribution states it was authored by Claude Opus 5.5 in Antigravity after reading the Claude proposal. It is useful synthesis, not an independently verified Gemini-model result. Its stage-wise score ceilings are diagnostic ideas, not achieved scores. A ten-stage framework and a full oracle attribution harness are not prerequisites to making measurable improvements; v3 implements useful hypotheses incrementally.

## Competition decision policy

- Maximize the official sample score, not a real-world auto-posting confidence target. Partial but credible item sets may be emitted; unresolved entries do not veto an entire payment.
- Expand truncated names, reference variants, parent/debtor scopes and related credit notes. Rank alternatives and make deterministic choices rather than requiring unique candidates everywhere.
- Keep legal submission constraints strict. Amounts remain in item currency; all IDs must exist; exception/category codes remain official. Internal uncertainty/residual labels never become submission labels.
- Preserve exact structured solutions first. Test aggressive fallbacks on the whole population, preserving genuine unidentified controls where the evidence favors them.
- Infer exceptions after candidate membership. An incomplete group can clear known items without declaring every unexplained cent a single-invoice overpayment.
- Use PDF schedules and explicit final-instalment/service-month phrases, rather than treating every item as one undifferentiated initial amount.
- Golden labels are evaluation only. No transaction-ID rules, golden-derived inference lookup or hidden-phase data. Empirical ranking is permitted and its effect is measured, rather than presented as organizer policy.

## Task chain and deliverables

1. Verify/extract compressed docs bundle; build canonical items and source facts.
2. Index party roles, document relationships, reference variants and settlement facts.
3. Expand source containers at run, beneficiary/transfer and receipt levels.
4. Generate full and partial payment hypotheses; compare source/cash fit and evidence.
5. Select, interpret accounting events, update balances, preserve unresolved context.
6. Validate and atomically export a five-column submission CSV; score only after inference.

Implementation lives here and reuses baseline archive/CSV/Decimal infrastructure. The baseline engine remains reproducible. Run with `python3 -m v3`; output is `final_submission/v3/sample/`. Runs, scores, regressions and adoption recommendation are recorded in `v3/results/`. TRAIN/LIVE/FINAL are not run in this stage.

## Stages

1. Design and assessment: this document, committed and pushed to `q`.
2. Implement broad retrieval, source semantics, group recovery and event rules; run sample and meaningful checks; commit/push measured results to `q`.
3. If another revision is warranted by observed failures, record its hypothesis, run the same sample, preserve comparisons, commit/push its result. Do not claim a target score without an actual scorer result.
