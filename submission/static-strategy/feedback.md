# Website feedback

## LIVE edition 001 — version-3 / 3.0.1

- File: `submission_v3_live_001.csv`
- File identity and local validation: `live_001.json`
- Website upload: handled by the user
- Website score: **77.46 / 100**, user-provided report, 07/11 at 13:22
- Reported metrics: allocation F1 83.3%, precision 92.4%, recall 75.8%, transaction accuracy 86.8%, exception macro-F1 48.9%, amount-weighted accuracy 78.5%.
- Website status: scored; zero missing bank lines, 646,942 rows.
- Source: `../../v3_feedback.md` and `../../feedback-evaluation/v3-model_evaluation_feedback.md` (hashes in live_001.json).
- Next strategy: starter-only v4 ML experiment; no new LIVE run yet.

The starter score of 78.65 is not a LIVE website result.

The historical filename `submission_v4.csv` in the report is an earlier submission and is not the current version-4 ML experiment. Segment accuracies are diagnostic slices, not exception-class F1 values; the four low-scoring return/chargeback segments do not constitute four distinct macro-F1 classes. Recommendations to add regexes are hypotheses requiring measurement, not guaranteed score gains.
