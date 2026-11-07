# V6 website review

The user-reported LIVE score is **81.39**, up **2.05 points** from v5's **79.34**, and **3.93 points** above v3's 77.46. The full transcribed report is in [v6_website_feedback_2026-11-07.md](../feedback-evaluation/v6_website_feedback_2026-11-07.md). This stage records and analyzes feedback only; no solver edits, model fitting, inference, evaluation, tests or new LLM judgments were run.

## What improved

| Website metric | V5 | V6 | Change |
|---|---:|---:|---:|
| Score | 79.34 | 81.39 | +2.05 points |
| Allocation F1 | 85.0% | 85.4% | +0.4 pp |
| Precision | 94.6% | 94.9% | +0.3 pp |
| Recall | 77.3% | 77.7% | +0.4 pp |
| Transaction accuracy | 87.5% | 88.7% | +1.2 pp |
| Exception macro-F1 | 52.9% | 60.3% | +7.4 pp |
| Amount-weighted accuracy | 83.6% | 83.7% | +0.1 pp |

Using the displayed rounded metrics, the score gain decomposes into approximately **+0.20 allocation points**, **+0.36 transaction points**, and **+1.48 exception points**. The sum is 2.04 rather than the exact 2.05 because the website rounds its component metrics. About 72% of the gain therefore comes through exception macro-F1. The report does not identify each exception class's contribution.

Both allocation precision and recall increased. V6's improvement did not require exchanging precision for recall at the aggregate level. It mainly recovered missing document/source mechanisms and repaired exception decisions. The small amount-weighted gain shows that this release solved scoring-relevant errors without a corresponding large change in total cash accuracy.

| Targeted family | V5 accuracy | V6 accuracy | Change |
|---|---:|---:|---:|
| Service month | 49.3% | 89.2% | +39.9 pp |
| Bank-charge shortfall | 8.8% | 76.9% | +68.1 pp |
| Returned cheque | 9.7% | 77.8% | +68.1 pp |
| Rejected supplier transfer | 5.2% | 66.7% | +61.5 pp |
| Card chargeback | 0.0% | 61.3% | +61.3 pp |
| Supplier duplicate refund | 34.3% | 88.1% | +53.8 pp |
| Replaced invoice | 44.0% | 78.2% | +34.2 pp |
| Advance deduction | 40.7% | 70.0% | +29.3 pp |
| Invoice/credit-note group | 40.8% | 47.7% | +6.9 pp |
| N-to-M | 16.3% | 24.1% | +7.8 pp |

These changes are consistent with the v6 mechanisms: next-month invoice selection, typed source-linked returns, multilingual PDF clauses, and signed credit arithmetic. They support the underlying-rule approach. Aggregate results cannot isolate every module's causal contribution or prove that the full synthetic generator has been recovered.

The main AP controls remain unchanged at the displayed precision: multi-payment 98.3%, single-payment 99.5%, paid-by-holding 98.8%, credit-note netting 98.2%, AP partial 89.2%. Cash pool and card settlements remain 100%. There are small regressions in AR short discount **90.6% → 90.4%** and instalments **76.2% → 76.1%**. That is roughly 11 and 5 additional wrong transactions using the approximate segment sizes; exact counts and causes are unavailable. The local development result of zero previously correct transactions becoming wrong did not establish zero LIVE regressions.

## What is still holding the score back

Only two displayed segments remain below 50%:

| Family | Accuracy | Approximate lines | Estimated wrong transactions |
|---|---:|---:|---:|
| Invoice/credit-note groups | 47.7% | 3,300 | 1,726 |
| N-to-M | 24.1% | 1,800 | 1,366 |

Together they leave roughly **3,092 wrong bank transactions**. These estimates are not counts of missing allocation pairs: a multi-invoice group can contain many pairs, so group recovery may affect allocation recall more than its transaction count suggests.

V6's group changes are deliberately bounded. Referenced credit netting requires usable party-scoped references and a small exact subset; related-credit recovery starts from a documented parent or the incumbent invoice set. It cannot generally reconstruct an entirely missing large invoice group. The partial-group rule requires at least two usable invoice references and a restricted newest-invoice residual; it is not a general multi-bank allocation solver. The weak group results are therefore consistent with incomplete candidate construction, source coverage and balance history. Hidden row-level labels would be needed to assign exact causes.

Allocation recall is still only **77.7%**, with precision already **94.9%**. If recall stayed fixed and precision became perfect, allocation F1 would reach only about **87.45%**, adding about **1.0 overall point** through the allocation component. Reaching 90 requires more than improving precision. Exception macro-F1 at 60.3% also has substantial headroom, but website segments are not independent exception classes; the three rare return families all share RETURNED.

The high-volume reference-noise family remains **86.1% on about 42,000 lines**, or roughly **5,838 wrong transactions**, exceeding the two below-50% groups combined. Other remaining volumes include returned DDs (~1,208 wrong), instalments (~1,123), FIFO (~928), and DD batches (~558). Prioritizing only the smallest percentage would overlook these pools.

## Recommended next decision

Keep v6 as the incumbent. The next proposal should prioritize **candidate coverage and joint group allocation**, reusing existing weights and caches:

1. **Audit credit-group construction end to end.** Measure whether the true invoices and credits are retrieved, whether remittance rows are fully resolved, whether quarterly rebates and cancellation credits are distinguished, and whether the group is rejected by a size limit or by stale balance state. A better ranker cannot select a missing full-group candidate.
2. **Build a bounded party/currency allocation component across relevant bank events.** Include invoices, credit notes, remittance lines, partial balances and returns; solve signed integer-cent allocations with document/source constraints. Preserve competing feasible candidates rather than assuming the newest invoice must absorb every residual. Allow items to remain open: an observed episode need not close within the selected period, and all available invoices need not belong to that episode. Arithmetic feasibility alone does not identify the true group.
3. **Treat reference noise as a separate recovery problem.** Test candidate expansion for omitted prefixes/zeros, digit swaps, truncated references and PO links, using party and date evidence. Retain the existing model for ranking these expanded candidates before considering retraining.
4. **Repair return/plan state interactions and protect monetary policies.** DD return/re-presentation and instalment/remaining-balance decisions need observed event history. Include timely-discount, late-discount, fee, withholding and disputed-payment lookalikes as controls, especially after the small LIVE discount/instalment regressions.
5. **Use LLM judgment for missing semantic evidence.** A cached remittance or PDF clause that cannot be parsed reliably is a useful tier-3 target. Give the LLM expanded source-linked candidates and require a structured fact or choice. Do not ask it to compensate for an absent group or guess arbitrary subsets from hundreds of invoices.

These are next-step hypotheses, not an implemented v7 or a forecast of its score. If execution is requested, first use a small mixed labeled cohort with unrelated controls and a reserved temporal/group complement. The existing 7,500-case set is inspected development data. Do not refit the model or rescan/re-extract full TRAIN by default.

The local gain was **+2.12** (79.29 → 81.41); the LIVE gain is **+2.05** (79.34 → 81.39). That is encouraging transfer of this selected release's improvement, not proof that the local evaluator is calibrated for future editions. The nearly equal final scores conceal different component metrics and populations.
