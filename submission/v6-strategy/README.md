# V6 submission

Upload `submission_v6_live_001.csv` from this folder, or the identical root `v6-submission.csv`.

- 203,083 LIVE bank lines; 643,231 allocation/category rows; 27,800,155 bytes.
- Hard contract checks and the organizer's schema parser pass.
- SHA-256: `1cd50662ec853537e33e40c1ac2c5a640953f87784ffa92d0aa7c91b78a8e9f6`.
- User-reported LIVE website score: **81.39 vs v5 79.34**. Cached development: **81.41 vs v5 79.29**, a separate population.

The strategy recovers service months, return-source links, advance/replacement clauses and credit/group arithmetic. It preserves the model and prior LLM decisions, with no retraining or new LLM calls. See [strategy](../../version-6/STRATEGY.md), [results and limitations](../../version-6/RESULTS.md), [website review](../../version-6/WEBSITE_REVIEW.md) and `live_001.json`. Website feedback is in `feedback.md`; the CSV and original release metadata remain immutable.
