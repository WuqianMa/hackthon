# V5 website feedback

Edition 001: **v5-submission.csv** at repository root, with edition copies in `submission/` and this folder. The user supplied the website result dated **07/11, 16:12**: **LIVE score 79.34**, versus v4 LIVE 79.05 (+0.29). Full transcribed feedback is in [v5_website_feedback_2026-11-07.md](../../feedback-evaluation/v5_website_feedback_2026-11-07.md).

SHA-256: `2e1e6354334d919d3ffffed42244d4ff3045fded370e2d28572075e7c37bda0b`.

| Website metric | V4 | V5 |
|---|---:|---:|
| Allocation F1 | 85.0% | 85.0% |
| Precision | 94.5% | 94.6% |
| Recall | 77.3% | 77.3% |
| Transaction accuracy | 86.8% | 87.5% |
| Exception macro-F1 | 52.4% | 52.9% |
| Amount-weighted accuracy | 78.5% | 83.6% |

Coverage remains 203,083 bank lines, 642,703 rows, zero omissions. Cash pool reached 100%, AP partial returned to 89.2%, and late discounts rose to 57.1%. Allocation recall remains flat. The [review of segments below 50%](../../version-5/WEBSITE_REVIEW.md) identifies missing routing, source links and group/period mechanisms, and explains using TRAIN without model retraining.

V5 cached development score 79.29 is a separate result on 7,500 inspected cases. Edition JSON records the original release snapshot, where website score was unknown; this feedback file tracks the later result. CSVs and model weights remain unchanged.
