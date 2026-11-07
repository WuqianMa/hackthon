# v4 hybrid strategy — saved dialogue proposal

Saved from the preceding dialogue on 7 November 2026. Status: **deferred proposal, not implemented or run**. The statement about not running experiments below describes that original proposal response, not the subsequently authorized version-3 LIVE execution.

Subsequent update: the user authorized the starter ML implementation and selected the three-tier strategy. See STRATEGY.md and RESULTS.md for the current decision and measured 80.95 result. The dialogue below is retained unchanged as historical planning context.

---

I propose **v4: static payment reconstruction with two learned decision models**. The models choose between plausible explanations; the static system continues to calculate amounts, apply policies and export the CSV.

This is a plan only. The starter observations below come from the existing **78.65** result; I have not changed code or run anything.

## 1. What we should train

Start with **gradient-boosted decision trees**, using two classifiers:

| Model | Decision | Why it is useful |
|---|---|---|
| **Item-allocation model** | “Is this proposed bank–item allocation correct?” | Ranks ambiguous references, parties, amounts and partial allocations. |
| **Payment-hypothesis model** | “Does this proposed set explain the complete transaction correctly?” | Distinguishes a complete payment from several individually plausible invoices. |

The second model is important. Training only an invoice matcher would preserve the simplification that caused many false overpayments.

We should initially compare these models against v3’s manual ranking. A learned model must earn its place through measured improvement.

## 2. Features and labels

For the item-allocation model:

| Feature family | Examples |
|---|---|
| Identity | IBAN/mandate match, payer-name similarity, parent/subsidiary relationship, intermediary indicators |
| References | Exact number, suffix/prefix match, edit distance, PO match, reference truncation |
| Amounts | Cash/open-amount ratio, absolute and relative residual, currency agreement |
| Timing | Invoice age, days before/after due date, discount eligibility |
| Documents | Advice membership, payment-run membership, related credit, replacement link |
| Settlement state | Remaining balance, prior partial payment, return/re-presentation, instalment position |
| Ambiguity | Number of competing items, repeated amounts, strength of the next-best candidate |

Its label is **1 when the proposed item and allocated amount match the golden allocation within official tolerance**, otherwise 0.

Include difficult negatives: same-party invoices, equal-amount alternatives, similar references and genuinely unidentified receipts. Random unrelated invoices would make training artificially easy.

For the payment-hypothesis model, add:

- Aggregated item-model probabilities.
- Proposed item count and competing hypothesis count.
- Signed invoice/credit total and unexplained cash.
- Advice/container completeness and unresolved entries.
- Evidence consistency across documents.
- Proposed exceptions and their policy eligibility.
- Conflicts with other payments and balance events.

Its label is **1 only when the complete proposed transaction matches the golden**, including amounts, exceptions and category where applicable.

Neither model should directly generate monetary amounts. The hypothesis generator supplies policy-consistent amount and exception alternatives.

## 3. How decisions become competition predictions

V4 should generate several alternatives: complete groups, credible partial groups, single-item explanations and non-item classifications.

The models score these alternatives. We then select the operating thresholds using the **official composite score on a calibration set**. We should not assume a probability threshold of 0.5 is optimal.

Partial allocations remain eligible because they can earn allocation credit. However, genuine unidentified cases must participate in calibration—the system cannot learn its guessing policy only from transactions already known to have invoices.

## 4. Proposed TRAIN split

| Purpose | Period |
|---|---|
| Fit model parameters | July 2021–December 2023 |
| Select features and model settings | January–June 2024 |
| Calibrate prediction/abstention thresholds | July–December 2024 |
| Locked temporal evaluation | January–May 2025 |
| Existing starter regression benchmark | June 2025 |

The June starter has already influenced our rules and experiments. Even after training on earlier data, it remains an inspected development benchmark.

The main leakage controls are:

- Keep every transaction’s allocation rows and candidate hypotheses together.
- Generate candidates without consulting golden labels; attach labels afterward.
- Reconstruct balances and payment-history features using only information available before the evaluated event.
- Define each simulated phase’s document-availability cutoff consistently with this offline challenge.
- Fit learned aliases, preprocessing and encodings only on the fitting period.
- Train the hypothesis model using **out-of-fold item-model predictions**, not inflated predictions from a model trained on those same examples.
- Exclude transaction/item IDs as predictors. Use party IDs for retrieval and historical aggregation, initially excluding them as direct predictive features.
- Add a separate customer-group holdout to test unseen counterparties.
- Keep the locked temporal evaluation untouched while tuning.

We also need to document the supplied master snapshot’s historical limitations; a later master snapshot is not automatically a historically accurate feature source.

## 5. What to check on the starter first

The first starter experiment should establish:

1. **Candidate recall:** how often is each correct allocation generated?
2. **Complete-hypothesis coverage:** how often does an entirely correct explanation exist among our alternatives?
3. **Ranking improvement:** when the correct explanation exists, can a small model select it more reliably than v3?
4. **Competition tradeoff:** does the improvement survive evaluation on all transactions, including true unidentified cases?

A grouped starter-only cross-validation can test the mechanics, provided related payment episodes stay together. It would be a development experiment, not evidence of future-period generalization.

**My recommendation:** build this candidate-and-label audit first. If correct hypotheses are usually absent, improve reconstruction. If they are present but selected poorly, train the decision models. That distinction tells us whether additional TRAIN data will address the actual bottleneck.
