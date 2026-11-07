# V6 website feedback

Edition 001, **v6-submission.csv**, was scored on LIVE at **81.39 / 100**, according to the website report pasted by the user on 7 November 2026. No website timestamp was included. This is **+2.05 points vs v5 LIVE 79.34**, +2.34 vs v4 LIVE 79.05 and +3.93 vs v3 LIVE 77.46.

Full transcription: [v6_website_feedback_2026-11-07.md](../../feedback-evaluation/v6_website_feedback_2026-11-07.md). Analysis and next priorities: [WEBSITE_REVIEW.md](../../version-6/WEBSITE_REVIEW.md).

| Website metric | V5 | V6 |
|---|---:|---:|
| Allocation F1 | 85.0% | 85.4% |
| Precision | 94.6% | 94.9% |
| Recall | 77.3% | 77.7% |
| Transaction accuracy | 87.5% | 88.7% |
| Exception macro-F1 | 52.9% | 60.3% |
| Amount-weighted accuracy | 83.6% | 83.7% |

203,083 LIVE bank lines, 643,231 rows, zero missing. Service-month accuracy rises 49.3% → 89.2%. All ten previously below-50% targets improve; only credit-note groups (47.7%) and N-to-M (24.1%) remain below 50%. Small regressions: short discount 90.6% → 90.4%, instalments 76.2% → 76.1%.

CSV SHA-256: `1cd50662ec853537e33e40c1ac2c5a640953f87784ffa92d0aa7c91b78a8e9f6`. The CSV and model remain unchanged. Edition JSON preserves the original release snapshot, when the website result was unknown. The local development 81.41 is a separate result on 7,500 labeled TRAIN bank lines.
