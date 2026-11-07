# V5 website review — focus on segments below 50%

## What the new result establishes

User-provided LIVE feedback reports **79.34**, versus v4 LIVE **79.05** (+0.29). The full source table is saved in [v5_website_feedback_2026-11-07.md](../feedback-evaluation/v5_website_feedback_2026-11-07.md). No new solver, model or evaluation was run for this analysis.

| LIVE metric | V4 | V5 | Change |
|---|---:|---:|---:|
| Score | 79.05 | 79.34 | +0.29 points |
| Allocation F1 | 85.0% | 85.0% | Flat when rounded |
| Precision | 94.5% | 94.6% | +0.1 pp |
| Recall | 77.3% | 77.3% | Flat when rounded |
| Transaction accuracy | 86.8% | 87.5% | +0.7 pp |
| Exception macro-F1 | 52.4% | 52.9% | +0.5 pp |
| Amount-weighted accuracy | 78.5% | 83.6% | +5.1 pp |

V5 repaired important decisions: cash pool 37.2% → 100%, AP partial 75.7% → 89.2%, late discount 49.0% → 57.1%. These gains did not materially expand allocation recall. Amount-weighted accuracy improved substantially, but the aggregate report cannot attribute that gain to a particular component or to the LLM alone.

Some large AP groups regressed: AP multi-item 98.8% → 98.3%, paid-by-holding 99.2% → 98.8%, and AP credit-note netting 98.6% → 98.2%. A 0.5-point accuracy drop on about 25,000 multi-payment lines means roughly 125 additional wrong transactions. Future fixes need these groups as controls even while focusing on the below-50% families.

## The below-50% targets

Estimated wrong transactions are `approximate count × (1 − accuracy)`. They rank error volume, not predicted score gain. Allocation-pair counts and exception confusion are not supplied; one multi-item transaction can contribute many pairs.

| Segment | V5 accuracy | Approx. lines | Approx. wrong | Required mechanism |
|---|---:|---:|---:|---|
| Service-month matching | 49.3% | 4,400 | 2,231 | Correct service-period facts and remaining-balance selection |
| AR invoice/credit-note group | 40.8% | 3,300 | 1,954 | Broader signed invoice/credit group construction |
| N-to-M | 16.3% | 1,800 | 1,507 | Joint multi-payment/multi-invoice allocation |
| Returned AP transfer | 5.2% | 170 | 161 | Link rejected transfer to original payment allocation |
| Advance deduction | 40.7% | 260 | 154 | Proforma/advance/final-invoice relationship and amount |
| Replaced invoice | 44.0% | 260 | 146 | Dated cancellation/replacement graph |
| Short bank charges | 8.8% | 150 | 137 | Fee evidence plus correct full-clearing amount |
| Returned cheque | 9.7% | 72 | 65 | Cheque/deposit reference-to-item bridge |
| AP duplicate refund | 34.3% | 67 | 44 | Link prior duplicate cash; distinguish APC credit refund |
| Card chargeback | 0.0% | 31 | 31 | Order/settlement/chargeback bridge, often partial-batch reversal |

The three large families account for approximately **5,692 wrong transactions**. The card/AP-transfer/cheque-return failures together account for about **257**. The rare failures deserve dedicated resolvers, but the largest recall opportunity is the high-volume group/period work.

Exception macro-F1 averages closed exception labels, not website segments. The three return families share RETURNED; a cheque return is not an independent macro class. SHORT_BANK_CHARGES is a distinct exception class and is worth auditing despite its small volume. AP duplicate refund is typically a category decision, not its own exception label.

With recall held around 77.3%, even perfect precision would give allocation F1 only about **87.2%**, compared with the displayed 85.0%. That is only about 1.1 overall points through the 50%-weighted allocation component if the others stayed fixed. Large progress requires recovering missing correct allocations and exception semantics, not precision polishing alone.

## Why current code leaves these families unresolved

### Returns: recognition exists, original-operation recovery is weak

`bankrec/engine.py:is_return` already recognizes CHARGEBACK and several return phrases. Adding the same keyword again does not solve the 0% result. In v5, `Ledger.original_operation` requires an earlier trusted operation on the **same account**, same currency, opposite cash within **one cent**, and a shared token of at least eight characters with four digits, within 180 days. It returns nothing unless the result is unique.

There is also a routing gap before that lookup. The recovery cohort uses a separate keyword list containing RETURN and DEVOL, but not every phrase recognized by `is_return`, such as CHARGEBACK, CHEQUE IMPAYE or RUECKLASTSCHRIFT. A transaction without another trigger may never reach the handler. The global 6,000-case cap prioritizes marked cases, so even an unmarked UNIDENTIFIED return can be crowded out. Recognition, routing and resolution are separate stages; handler unit tests do not establish end-to-end reachability.

The lookup itself misses new return references, truncated originals, deductions, earlier-phase operations and an individual chargeback/cheque/receipt embedded in a larger original settlement. The runner passes `sources=None` to recovery; it does not currently bridge these requests through all the already-parsed card, cheque, receipt and payment-run groups. The saved v5 method inventory shows only **one** linked-original-return recovery.

Proposed change: route recognized returns directly using the shared `is_return` result, with a reserved per-family budget, then index original payment/settlement objects using end-to-end IDs, mandate/receipt IDs, cheque numbers, deposit IDs, merchant order IDs and source-group membership. Recover the original item-currency allocation, not simply the negation of bank cash. Reverse the returned member rather than an entire batch for a partial chargeback. Use bank/account/currency/date/party as corroborating constraints, and keep separate return-fee lines classified as BANK_FEES. Recognition and source linking need separate diagnostics.

### Bank charges: a narrow decision gate, not necessarily a wrong threshold

The existing policy already applies the published limits: shortfall ≤ EUR 60 equivalent and ≤2% of the item, with full open amount cleared. It additionally requires a known non-SEPA customer country and literal CHGS/SHA/BEN/BANK CHARGE wording. Legitimate fee evidence can be in an advice/SWIFT text or describe the originating bank rather than the customer's master country.

Proposed change: obtain positive deduction evidence from existing cached documents and bank fields, then apply the official limits and the correct item-currency amount. Distinguish a separate fee transaction, a disputed deduction, a genuine partial payment and a fully cleared cross-currency invoice (whose exception may be FX_DIFFERENCE). Do not label every small shortfall as a fee or relax organizer tolerances.

### Credit netting and N-to-M: missing hypotheses

The v5 netting function starts from already-selected item groups, does not start from a wholly UNIDENTIFIED transaction, requires direct `related` credit links, and bounds groups to eight invoices and up to four additional credits. It skips several explained exceptions. The cohort router also lacks a general residual/related-credit/connected-payment trigger, so a known-item transaction with an unexplained shortfall may never reach netting. Only **three** new credit-netting recoveries were recorded. There is no general multi-bank N-to-M solver.

Proposed change: route unresolved residuals and connected payment/item episodes, then construct an episode graph of bank lines, invoices, credit notes and source documents within identified party/group and currency scopes. Include quarterly rebate credits as well as directly linked credits, and exclude cancellation credits that should never clear through bank. Use integer-cent flow or bounded joint allocation with source amounts, partial balances, signed credits and policy adjustments. FIFO is an available tie-break only where the official policy applies. If several feasible allocations exist, source references, advice entries or comparable history must disambiguate them; amount feasibility alone is not correctness.

### Service month: missing text/period structure

V5 parses named months, has limited date forms, uses cached service clauses and stops when more than one candidate matches. The review packet exposes only the first 1,800 cached text characters and depends on an item's stored PDF source link. Many reviewed items lacked useful cached text. Only **ten** automatic service-period recoveries and a small LLM cohort were applied, so moving 48.9% to 49.3% is unsurprising.

Proposed change: repair document-to-item links with entity + party + printed number + document date, including short supplier references; retrieve relevant clauses from the full cached text rather than its prefix. Extract structured service start/end periods with multilingual, numeric, compact-month and year-rollover support. Rank the named service period separately from issue/due month and use pre-payment balances. Send conflicting period interpretations to the LLM after expanding the right candidate pool.

### Advance, replacement and duplicate refund: event relationships

Proposed changes:

- Advance: link the proforma/advance receipt to the later invoice and extract the actual deducted advance amount. A proforma receipt is a category event; the later invoice payment follows the challenge's PARTIAL rule. A boolean `advance` flag alone is insufficient.
- Replacement: build dated old-document → cancellation → replacement links and suppress obsolete/cancelling items. V5's lookup is triggered mainly by unresolved or already-cancelled current matches; a plausible wrong non-cancelled incumbent can prevent the search. Trigger from a cited replacement-chain reference as well.
- Duplicate refund: link supplier, account, currency, amount and earlier duplicate payment; distinguish a cash duplicate refund category from an incoming payment settling a supplier credit note (APC). Avoid classifying every incoming supplier refund identically.

These are hypotheses supported by the implementation and aggregate feedback, not identified per-row LIVE error causes. Row-level LIVE gold is unavailable.

## Will TRAIN help without model training? Yes

Keep the existing model weights. Use TRAIN as **reference history, a supervised casebook, and an evaluation resource**:

1. **Original-operation lookup.** Query already-indexed TRAIN invoices and relevant historical bank/payment/receipt/card/cheque source records for missing prior operations. Some LIVE returns may originate before July; availability must be checked rather than assumed. A small filtered lookup index may be needed, but this is not model fitting or a feature rebuild. Avoid scanning years of files separately for every query.
2. **Casebook per low-performing family.** Inspect up to 20–30 labeled examples per family where available, alongside raw source evidence and existing wrong/correct output. Determine whether each failure is recognition, retrieval, grouping, amount, state or exception. Include correct examples and lookalikes. Derive general source/format rules rather than memorizing transaction/item IDs.
3. **LLM retrieval examples.** Supply a few clearly labeled older TRAIN examples with relevant source clauses and policy reasoning, plus the new case's unlabeled evidence. This is in-context supervision/retrieval, without updating model weights. Do not retrieve the evaluated case or its connected golden episode, or expose hidden LIVE truth. Validate with time/group-disjoint examples and follow competition data rules.
4. **Small regression evaluation.** Use an untouched complement and controls with the official scorer. Historical golden is for supervision and evaluation, not an oracle for selecting the current case's allocation. Preserve temporal boundaries: no later labels or held-out case answers in inference context.

No retraining does not mean no overfitting: repeatedly tuning rules/prompts on the same inspected cases can still overfit. The existing 7,500-case fixture is development evidence, not a fresh blind test. Full TRAIN's size is not a reason to rebuild all its features; start with the relevant cached records and a bounded casebook.

## Recommended next work, without launching it now

1. **Return/fee diagnostic pack:** trace the rare return families through recognition → routing/budget → source lookup → item resolution → amount/exception, and audit SHORT_BANK_CHARGES separately. Reuse original-operation/settlement indexes and cached documents. Fix router reachability before judging a handler's effectiveness; reserve budget for rare families rather than allowing service-period cases to consume the global cap.
2. **Group recovery:** implement signed credit groups and a bounded N-to-M episode solver. This directly targets the large missing-allocation population.
3. **Period/document recovery:** repair PDF lookup and extract full service periods before expanding LLM volume.
4. **Relationship recovery:** typed advance/replacement/refund links from sources and earlier TRAIN examples.
5. **One-family ablations:** compare each module alone on a fixed small mixed cohort with genuine unidentified, legitimate partial, ordinary bank-fee, APC-refund and high-accuracy AP multi-payment controls. Route LIVE by observable evidence, never by unavailable website segment names.

Report candidate coverage, accepted recoveries, correct item/amount pairs, complete-transaction accuracy, per-exception P/R/F1, regressions and runtime. Then score the complete development fixture with the complement unchanged. Do not average subgroup composite scores or promise a 90-point result. Do not increase LLM calls merely to revisit the same incomplete hypotheses.

This stage saves feedback and analysis only. No solver edits, new training, inference, evaluation, tests, LLM judgments or new submission generation were performed.
