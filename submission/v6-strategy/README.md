# V6 submission

Upload `submission_v6_live_001.csv` from this folder, or the identical root `v6-submission.csv`.

- 203,083 LIVE bank lines; 643,231 allocation/category rows; 27,800,155 bytes.
- Hard contract checks and the organizer's schema parser pass.
- SHA-256: `1cd50662ec853537e33e40c1ac2c5a640953f87784ffa92d0aa7c91b78a8e9f6`.
- Cached development: **81.41 vs v5 79.29**. LIVE website score pending.

The strategy recovers service months, return-source links, advance/replacement clauses and credit/group arithmetic. It preserves the model and prior LLM decisions, with no retraining or new LLM calls. See [strategy](../../version-6/STRATEGY.md), [results and limitations](../../version-6/RESULTS.md) and `live_001.json`. Save website feedback in `feedback.md`; preserve the CSV.
