# V4 website feedback review and comparison with v3

## Evidence and comparability

The user added the untracked `v4-feedback.md` at the repository root. It reports LIVE submission score **79.05** and 642,703 rows over 203,083 bank lines, consistent with our v4 edition's saved volume. The report does not supply a CSV hash or row-level labels; attribution to edition 001 follows the user's upload context and matching row count. Preserve it as user-provided website feedback, not an independently queried website result.

Compare with `v3_feedback.md` / `feedback-evaluation/v3-model_evaluation_feedback.md`, which report v3 LIVE edition 001. The older `submission_v4.csv` scoring 74.14 in v3's history is a different submission. The TRAIN holdout's 79.05 is also a separate result; its allocation F1 was 86.19% and transaction accuracy 83.31%, unlike the LIVE components below.

| LIVE metric | V3 | V4 | Change |
|---|---:|---:|---:|
| Overall score | 77.46 | 79.05 | +1.59 points |
| Allocation F1 | 83.3% | 85.0% | +1.7 percentage points |
| Precision | 92.4% | 94.5% | +2.1 pp |
| Recall | 75.8% | 77.3% | +1.5 pp |
| Whole-transaction accuracy | 86.8% | 86.8% | Flat at displayed precision |
| Exception macro-F1 | 48.9% | 52.4% | +3.5 pp |
| Amount-weighted accuracy | 78.5% | 78.5% | Flat at displayed precision |
| Rows | 646,942 | 642,703 | −4,239 |
| Missing bank lines | 0 | 0 | Full coverage retained |

The rounded allocation-F1 change contributes approximately 0.85 score points and the exception change about 0.70, broadly explaining +1.59 after display rounding. Fewer rows alone are not evidence of better decisions; the improved precision and recall establish the useful change here.

## Precision and recall

There is an operating-point tradeoff, but **v4 improved both precision and recall**. Its observed gain did not require sacrificing recall globally. The remaining imbalance is high precision with substantially lower recall: approximately 5.5% of submitted allocation pairs are wrong, while 22.7% of required allocation pairs are missing. Those percentages have different denominators and are not directly comparable error counts. A wrong item can produce both a false positive and a false negative.

V5 should seek more correct proposals and better group/amount interpretation before indiscriminately reducing thresholds. Some precision loss can be worthwhile if recall and the full composite improve; there is no competition rule requiring maximal precision or zero speculative choices. Select changes using the actual 50% allocation-F1 / 30% transaction-accuracy / 20% exception-macro-F1 objective, with unidentified controls included.

Flat transaction accuracy suggests that gains and regressions offset, or that improved partial allocations still leave transactions incomplete. Rounded aggregate feedback cannot identify which individual cases changed.

## What improved and what regressed

| Segment | V3 accuracy | V4 accuracy | Change |
|---|---:|---:|---:|
| DD returned | 56.7% | 65.5% | +8.8 pp |
| DD re-presented by transfer | 61.9% | 66.3% | +4.4 pp |
| Dispute settlement | 89.3% | 92.1% | +2.8 pp |
| AR multi-item text | 86.0% | 87.5% | +1.5 pp |
| AR partial | 77.5% | 79.0% | +1.5 pp |
| AP multi-item payment | 98.3% | 98.8% | +0.5 pp |
| Retention | 79.6% | 62.6% | **−17.0 pp** |
| AP partial | 89.2% | 75.7% | **−13.5 pp** |
| Late discount | 57.4% | 49.0% | **−8.4 pp** |
| Instalment | 77.9% | 75.4% | −2.5 pp |
| Service-month matching | 50.8% | 48.9% | −1.9 pp |
| Same-amount FIFO | 87.3% | 85.5% | −1.8 pp |
| N-to-M | 17.9% | 16.3% | −1.6 pp |

Retain the return and matching gains while investigating the amount/state-sensitive regressions. Do not implement a blanket rollback by website segment: those segment labels are unavailable to the LIVE inference program.

Persistent weak areas include credit-note netting (40.6%), service-month matching (48.9%), N-to-M (16.3%), cash pool (37.2%), short bank charges (8.8%), rejected AP transfers (4.6%), cheque returns (9.7%) and card chargebacks (0% on only about 31 lines). High-volume reference noise remains at 86.1%, so apparently respectable accuracy still leaves substantial error volume. Segment counts are approximate; these percentages do not reveal the exact item, amount or exception confusions.

## Code-level explanations to test

1. **Item correctness and exception correctness are coupled incorrectly.** `version-4/data.py` adds blank-exception variants for static PARTIAL/DUPLICATE_PAYMENT/OVERPAYMENT rows. `run.py` chooses a best variant per item using an allocation classifier whose target ignores exceptions, and also creates `static_blank` hypotheses. A good item probability therefore cannot justify erasing an exception. The 31 over-total blank duplicate proposals repaired at publication provide a concrete example; the wider segment regressions are consistent with this mechanism but do not prove it caused every loss.
2. **The ledger context differs between fitting and LIVE.** TRAIN static replay used sampled bank history. Additional alternatives use opening amounts, and LIVE workers do not advance a shared chronological v4 ledger. In the saved TRAIN holdout, FIFO improved from 14.4% to 45.3%; on LIVE the stronger v3 baseline was already 87.3%, and v4 reduced it to 85.5%. This is evidence of a likely transfer problem, not proof that another training run is required.
3. **The ranker cannot choose an absent explanation.** The saved TRAIN candidate pool contained 22,383 of 26,528 required item/amount pairs (84.375%). This is not a LIVE ceiling or a data-availability ceiling. The top-36 additional-item cap, limited subset construction, document interpretation and missing links leave opportunities for targeted recovery.
4. **Category alternatives are restricted.** V4 generally offers the static category or UNIDENTIFIED. The decision model cannot recover a missing CASH_POOL category if no such alternative is proposed. Zero source-parser exceptions also do not establish complete source interpretation or allocation resolution.

## Corrections to the supplied recommendations

- Exception macro-F1 averages the actual exception labels present in golden, not scenario segments. Card chargebacks, rejected AP transfers and cheque returns all contribute to **RETURNED**; they are not three separate equal-weight macro classes. The official scorer and FORMAT are authoritative.
- The report's promised macro-F1 above 60% and predicted 79.6–79.8 score after specific repairs are unverified. Restoring AP partial and retention corresponds to roughly 535 additional correct transactions using the report's approximate counts; transaction accuracy alone contributes only about **0.079 overall score points**. Larger gains require allocation/exception effects that the segment table cannot quantify.
- `feature_mining_results-otheragent.md` says original-currency fields are unused. Existing `bankrec/engine.py` already uses `orig_amount` / `orig_currency`, and v4 has corresponding features. Audit failure paths rather than presenting this as an absent implementation.
- That mining note supplies no reproducible scope for its proposed 19,000 amount-only matches. Entity-unique amounts and bank codes are useful candidate/routing signals, not automatic truth. The organizer explicitly includes unidentified lookalikes.
- Claude's saved analyses concern the older **71.32 starter baseline**. Its operating-point counterfactual selects already-known errors using golden; it cannot justify guessing on all current UNIDENTIFIED cases. Its a4 probe is explicitly superseded. Reachability results are leads rather than deployable accuracy estimates.

No inference, evaluation, training, tests or LLM calls were performed during this review. Findings use existing reports and code inspection only.
