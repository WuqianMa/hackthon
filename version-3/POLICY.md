# v3 rules and scoring policy

The organizer's docs in the verified archive remain the accounting authority. Competition strategy controls which hypotheses to predict; it does not change those definitions.

| Rule | Implementation |
|---|---|
| Cash versus item amount | Integer cents; submissions remain positive in item currency, including credits. |
| Netting | Related credit notes subtract from group cash and produce positive allocation rows. |
| Partial/dispute | Applied cash is the row amount. Stated advice deductions produce disputes. |
| Full clearing differences | Eligible discount/withholding/bank-charge/FX/overpayment use remaining open amount; baseline policy arithmetic is reused. |
| Final instalment/remainder | Explicit final markers, plan tranches and settlement/release phrases can imply an empty exception despite incomplete earlier sample history. A known closed balance remains a duplicate. |
| Parent payment | Distinguish payer from debtor; expand stored parent/group relationships. |
| Grouping | Preserve whole run, transfer/beneficiary and maturity hypotheses. Maturity uses the latest unambiguous invoice due date within a transfer; this is an empirical interpretation of available fields, checked by source sums and sample results. |
| Returns | Prefer original receipt evidence; add mandate-to-party lookup and exact document amount hypotheses. |
| Production return bound (3.0.1) | Reopened amount cannot exceed the document total; excess paid cash is not itself an additional reopened item balance. |
| Partial container | Emit resolved item rows even if another entry is unresolved. This can earn pair credit while failing complete-transaction accuracy. |
| Unknown/ambiguous case | Use ranked party-scoped hypotheses, then partial reference sets. Unknown payer controls stay in the evaluated population; no golden-based choice of which transactions to guess. |

## Empirical search decisions, not official accounting thresholds

Name prefixes use 8–40 normalized characters, with up to eight matching parties per prefix. Broad document prefixes participate in group generation; stronger exact/suffix references support partial output in the balanced profile. Party subset search is bounded at 32 candidates; an anchored residual can search up to 60 candidates for up to three additional invoices. Generic single-item ratio candidates use a 0.1–1.05 band for ranking. These are implemented search bounds, not organizer-defined tolerance rules.

The `--speculative` profile emits broader prefix groups and defers their ledger effects, alongside deferring generic party-ranked effects. This protects subsequent stronger evidence from weak early hypotheses. It is a limited confidence-aware ledger strategy, **not a completed phase-wide optimizer**. The measured sample tradeoff is recorded in RESULTS.md.

## Validation boundary

Both profiles enforce phase coverage, known IDs, five canonical fields, numeric precision, allowed labels, duplicate/mixed-row rules and size limits. The unchanged official scorer also validates the output when evaluating sample.

The baseline adds an aggregate cross-bank balance rejection not present in the official upload rules. Under `--speculative`, this check becomes a diagnostic warning: speculative allocations may compete for an item, and only the scorer determines which receive credit. It is recorded rather than hidden. Other local validation errors still stop publication. This profile is competition inference and does not claim a fully reconciled accounting ledger.

Golden labels are read only by post-inference evaluation. No bank-ID answer tables, new labels or hidden-phase labels are permitted. The inspected sample is development data, and improvements here do not establish future-period performance.
