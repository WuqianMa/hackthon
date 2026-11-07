# Final Evaluation Metrics — Reference for Development Agents

## Purpose

This document explains the bank-reconciliation evaluation metrics exposed by the repository's saved evaluation artifacts and evaluator wrappers. Use it to interpret evaluation feedback and propose improvements. It does **not** assess a particular submission, report anyone's results, or authorize running experiments or modifying the solver.

The reviewed repository exposes an overall score, allocation precision/recall/F1, transaction accuracy, exception macro-F1, amount-weighted accuracy, validation status, coverage counts, and scenario breakdowns. The official scoring implementation and final-phase competition policies were not available in the reviewed branch. Consequently, the exact composite weights, matching tolerance, and certain edge-case definitions must be checked against the official scorer and policies before treating this guide as a final-phase specification.

## 1. Evaluation units

A **bank transaction** is the reconciliation case being evaluated. A **prediction row** expresses an allocation to an item, or a classification for a transaction without an item allocation. One transaction can produce several rows.

An **allocation** associates a transaction with a receivable, payable, or credit note and an allocated amount. A **category** describes a transaction's accounting classification. An **exception** describes a special reconciliation condition, such as a partial payment or return. Categories and exceptions are different fields and must not be treated as interchangeable labels.

The visible prediction schema is:

```text
bank_txn_id,item_id,amount,category,exception
```

The official format rules determine permitted combinations, amounts, signs, identifiers, and labels. A syntactically valid row is not necessarily a correct reconciliation.

## 2. Metric map

| Metric or field | Question it answers | Direction |
|---|---|---|
| Overall `score` | How does the evaluator combine performance into its headline score? | Higher is better |
| Allocation `precision` | How reliable are the allocations the solver predicts? | Higher is better |
| Allocation `recall` | How many required allocations does the solver recover? | Higher is better |
| `allocation_f1` | How well does the solver balance allocation precision and recall? | Higher is better |
| `txn_accuracy` | How often is an entire transaction reconciled correctly? | Higher is better |
| `exception_macro_f1` | How well are exception classes handled when each class has equal weight? | Higher is better |
| `amount_weighted_accuracy` | How accurate is reconciliation after weighting transactions by the evaluator's amount weights? | Higher is better |
| `ok`, `errors` | Did the submission pass the evaluator's validation checks? | Successful validation is required |
| `txns_covered`, `txns_total` | Does the output cover the expected transaction population? | Complete coverage is desirable; correctness is separate |
| `rows` | How many prediction rows were submitted? | No inherently better direction |
| Scenario `n`, `accuracy` | Where does transaction-level performance succeed or fail? | Higher accuracy; interpret alongside count |

Fraction-valued metrics can be displayed as percentages by multiplying by 100. The overall score is reported on a 100-point scale. A percentage-point change in a component is not automatically the same change in the overall score.

## 3. Allocation precision

### Meaning

Precision measures the correctness of predicted allocations. In conventional notation:

$$\text{Precision} = \frac{\text{TP}}{\text{TP} + \text{FP}}$$

- **TP:** predicted allocations accepted as correct under the scorer's matching rules.
- **FP:** predicted allocations not accepted as correct.

The scorer decides what constitutes an accepted allocation match, including identifiers, amount tolerance, and any applicable label requirements. Do not assume that matching an invoice identifier alone is sufficient.

### Interpretation and suggested improvements

High precision means the solver's emitted allocations tend to be reliable. It does not establish that the solver finds all required allocations, classifies non-item transactions correctly, or handles exceptions correctly.

Low precision suggests investigating ambiguous customer identities, repeated invoice numbers, coincidental amount matches, currency or sign errors, stale balances, and unsupported allocations. Suggested changes include stronger evidence requirements and better disambiguation. Review recall at the same time: suppressing predictions can improve precision while reducing useful reconciliation coverage.

## 4. Allocation recall

### Meaning

Recall measures how much of the required allocation set is recovered:

$$\text{Recall} = \frac{\text{TP}}{\text{TP} + \text{FN}}$$

**FN** denotes expected allocations that the solver fails to recover under the scorer's rules. An incorrect predicted allocation can create both a false positive and a false negative if it replaces a required allocation.

Recall concerns allocation units, not necessarily the fraction of transactions with output. A transaction can have an output row while all of its required allocations remain unrecovered.

### Interpretation and suggested improvements

Low recall with high precision often indicates conservative matching or missing scenario support. Suggested investigations include candidate generation, one-to-many and many-to-many allocation, remittance parsing, credit-note netting, partial payments, historical balance state, and cross-entity payments. Increasing candidate coverage should be paired with checks against false matches.

## 5. Allocation F1

### Meaning

F1 is the harmonic mean of allocation precision and recall:

$$\text{F1} = 2 \times \frac{\text{Precision} \times \text{Recall}}{\text{Precision} + \text{Recall}} = \frac{2 \times \text{TP}}{2 \times \text{TP} + \text{FP} + \text{FN}}$$

F1 is low when either precision or recall is low. The evaluator's implementation governs zero-denominator cases and the exact definition of allocation matches.

### Interpretation and suggested improvements

Use F1 to compare the overall allocation tradeoff, then inspect precision and recall separately to identify the cause. Two solvers with similar F1 can have very different error profiles. A change that improves one component but worsens the other should be assessed through both components and the final composite score.

## 6. Transaction accuracy

### Meaning

Transaction accuracy evaluates the entire reconciliation case rather than isolated allocations:

$$\text{Transaction accuracy} = \frac{\text{fully correct transactions}}{\text{evaluated transactions}}$$

Treat this as a strict end-to-end metric. A transaction with several correct allocations and one wrong or missing allocation may fail the complete-transaction check. Category-only transactions also require correct handling under the scorer's rules. The official scorer determines exactly how amounts, categories, exceptions, extra rows, and missing rows affect correctness.

### Interpretation and suggested improvements

High allocation quality can coexist with lower transaction accuracy when small residual errors invalidate otherwise useful reconciliations. Suggested investigations include incomplete batches, missing credit notes, incorrect exception labels, duplicated rows, and incorrect non-item categories. Examine complete transaction outputs rather than only successful individual matches.

## 7. Exception macro-F1

### Meaning

Macro-F1 normally computes F1 separately for each exception class and takes an unweighted mean:

$$\text{Macro-F1} = \frac{1}{K} \sum_{k=1}^{K} \text{F1}_k$$

Each class receives equal weight, so rare exceptions can materially affect this metric even when common transactions are handled well. It is not the same as pooling all exception decisions and computing one micro-F1, or weighting class F1 by frequency.

The evaluator wrappers list these exception labels:

| Label | Business meaning to investigate |
|---|---|
| `PARTIAL` | Payment settles only part of the relevant item balance |
| `OVERPAYMENT` | Payment exceeds the amount needed for settlement |
| `SHORT_DISCOUNT` | Short payment is associated with an early-payment discount |
| `SHORT_BANK_CHARGES` | Short payment is associated with bank charges |
| `SHORT_WITHHOLDING` | Short payment is associated with withholding |
| `SHORT_DISPUTE` | Short payment is associated with a dispute |
| `DUPLICATE_PAYMENT` | Payment repeats an already settled obligation |
| `UNIDENTIFIED` | Reconciliation remains unidentified |
| `RETURNED` | Payment or collection is returned |
| `FX_DIFFERENCE` | Settlement difference is associated with foreign exchange |

These descriptions are explanatory, not replacements for the official label definitions. Confirm the averaging set, treatment of absent classes and blank exceptions, and whether scoring decisions occur per allocation or per transaction in the official scorer.

### Interpretation and suggested improvements

If transaction accuracy is strong but exception macro-F1 is weak, common normal cases may be masking inconsistent exception handling. Request per-class precision, recall, F1, and support counts. Suggested improvements should address class-specific accounting rules, payment state, dates, currencies, and supporting documents rather than merely changing label frequencies.

## 8. Amount-weighted accuracy

### Meaning

The conventional form weights each transaction's correctness by its evaluation weight:

$$\text{Weighted accuracy} = \frac{\sum_t (\text{weight}_t \times \text{correctness}_t)}{\sum_t \text{weight}_t}$$

The official implementation defines both the weight and correctness term. Do not infer whether weights are signed, absolute, converted to EUR, capped, or otherwise transformed without checking the scorer.

The repository documentation specifically warns that the local evaluator can use fallback weights when `amount_eur` is absent. Therefore, do not present this field as verified EUR-weighted accuracy without verifying the actual weight source.

### Interpretation and suggested improvements

If amount-weighted accuracy is materially below ordinary transaction accuracy, larger-weight transactions may be less reliable. Investigate high-value batches and complex settlements after confirming the weight definition. This metric is not automatically the proportion of money correctly allocated or a measure of financial loss.

## 9. Overall score

The overall score is the evaluator's headline composite result. The available artifacts do not establish its exact formula or component weights. Do not average the visible metrics, substitute allocation F1 for the overall score, or invent a weighting formula.

Before optimizing specifically for the final evaluation, consult the official scorer and competition policies for the score formula, validation penalties, rounding, final-phase inputs, and eligibility rules. Evaluate proposed changes against the actual objective while retaining the component metrics needed to explain tradeoffs.

The global score should come from evaluation of the complete submission. An arithmetic or transaction-weighted average of group scores need not reproduce it, particularly when F1 and macro-averaging are involved.

## 10. Validation, coverage, and row counts

- **`ok`:** the recorded evaluator validation outcome. It is not a declaration of perfect matching or deployment readiness.
- **`errors`:** reported validation failures. An empty list does not establish that all business decisions are correct.
- **`txns_total`:** expected transaction population for the evaluated scope.
- **`txns_covered`:** number of transactions represented according to the evaluator's coverage rules.
- **Coverage ratio:** $\frac{\text{txns\_covered}}{\text{txns\_total}}$; use only with a nonzero denominator and consistent evaluation scope.
- **`rows`:** prediction-row count. Multiple allocations per transaction are legitimate, so rows need not equal transactions.

Suggested review: first establish that outputs are valid and cover the intended population, then interpret matching quality. Neither complete coverage nor a larger row count guarantees better reconciliation.

## 11. Scenario and entity breakdowns

Scenario results expose `n` (the number of transactions) and `accuracy` (transaction-level correctness for that scenario). Entity or processing-group results provide a separate view of local operating conditions. These are diagnostic slices, not additional independent validation sets.

Use both rate and volume when proposing improvements:

$$\text{Approximate incorrect transactions in a scenario} = n \times (1 - \text{accuracy})$$

This estimates transaction-error volume from potentially rounded metrics. It does not predict a composite-score gain or an amount-weighted gain. Do not sum slices unless they are known to be disjoint.

A low-accuracy, high-volume scenario may be a strong priority for transaction accuracy. A rare exception class can still be a strong priority for macro-F1. Entity-specific problems can indicate differences in language, payment formats, account mappings, or cross-entity relationships; the metrics alone do not establish the root cause.

## 12. Comparing evaluations correctly

Before interpreting a difference, establish that the evaluated population, golden labels, candidate items, master data, auxiliary documents, and scoring rules are comparable.

- A development result measures performance on a scope used during development.
- A temporal holdout is useful, but is not a blind test if it was previously explored or influenced development.
- A full-TRAIN evaluation measures performance on that corpus; it does not establish unseen final-phase performance.
- A sample-to-full-corpus difference can reflect changes in scenario mix, historical balances, or candidate ambiguity as well as solver behavior.
- An offline evaluation that permits later-arriving documents is different from an online evaluation restricted to information available at transaction time.
- An ablation supports causal interpretation only when the intended component changes and other relevant conditions remain fixed.

Record percentage-point changes for percentage metrics and score-point changes for the overall score. Do not describe a point difference as a relative percentage improvement unless that calculation is explicitly intended.

## 13. How agents should use feedback

When asked to review results, agents should report observations and recommendations separately:

| Observed pattern | Suggested investigation |
|---|---|
| High precision, low recall | Missing candidates, unsupported scenarios, overly restrictive rules |
| Low precision | Ambiguous identities, weak evidence, wrong amounts/currencies, incorrect state |
| Good allocation F1, weaker transaction accuracy | Incomplete multi-row settlements, extra rows, category or exception errors |
| Good transaction accuracy, weak exception macro-F1 | Rare exception classes and class-specific precision/recall |
| Weighted accuracy below ordinary accuracy | Larger-weight transactions, after verifying the weighting rule |
| Strong aggregate, weak scenario or entity slices | Concentrated failure modes hidden by aggregate averages |
| Validation failures or incomplete coverage | Output contract and population alignment before performance interpretation |

For each recommendation, state the observed metric pattern, affected scope, plausible explanation, and evidence needed to distinguish explanations. Do not claim a diagnosis from an aggregate metric alone. Do not run experiments or implement suggested changes unless separately requested.

## Source scope

This guide is based on the metric fields and documentation visible at repository commit `36d15f7e200961df544a9c4e529b8fb1aa46f3a4`:

- [Evaluator wrapper](https://github.com/WuqianMa/hackthon/blob/36d15f7e200961df544a9c4e529b8fb1aa46f3a4/bankrec-improved/evaluate.py)
- [Full-corpus evaluator wrapper](https://github.com/WuqianMa/hackthon/blob/36d15f7e200961df544a9c4e529b8fb1aa46f3a4/bankrec-improved/evaluate_train.py)
- [Metric field structure](https://github.com/WuqianMa/hackthon/blob/36d15f7e200961df544a9c4e529b8fb1aa46f3a4/bankrec-improved/train_results/full_train_score.json)
- [Repository documentation and methodological limitations](https://github.com/WuqianMa/hackthon/blob/36d15f7e200961df544a9c4e529b8fb1aa46f3a4/bankrec-improved/README.md)

The linked JSON identifies the available field structure; this guide intentionally does not reproduce the submission's outcomes. Official `bankrec_score.py`, `POLICIES.md`, `FORMAT.md`, and `DATA_DICTIONARY.md` remain the authorities for exact scoring and final-phase requirements.