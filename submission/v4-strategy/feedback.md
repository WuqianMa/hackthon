# Website feedback — v4

Edition 001: **submission_v4_live_001.csv**, generated and validated; user-provided website feedback now reports **LIVE 79.05**, versus v3 LIVE **77.46** (+1.59). Source: [v4-feedback.md](../../v4-feedback.md), found through Git's untracked-file listing. The report's 642,703 rows match this edition; no submission hash is included in the report. LLM judgment was disabled. The repository-root copy is **v4-submission.csv**. All CSV copies have SHA-256 `f3f9262153d47c927a96da78d2df9821cdb73738db698fbfb6acc5c7a37113f1`.

Coverage: 203,083 LIVE transactions, 642,703 rows, 27,781,139 bytes. Frozen TRAIN holdout score: 79.05 versus static 73.34 on the same 7,500 cases. TRAIN and LIVE happen to share the headline value; they have different populations and metrics. Edition provenance and validation at generation are in `live_001.json`; its pending website status is the original release snapshot.

| Website metric | V3 | V4 |
|---|---:|---:|
| Allocation F1 | 83.3% | 85.0% |
| Precision | 92.4% | 94.5% |
| Recall | 75.8% | 77.3% |
| Transaction accuracy | 86.8% | 86.8% |
| Exception macro-F1 | 48.9% | 52.4% |
| Amount-weighted accuracy | 78.5% | 78.5% |

Both precision and recall improved. Retention (−17 pp), AP partial (−13.5 pp) and late discount (−8.4 pp) regressed. DD returned (+8.8 pp) and re-presented transfer (+4.4 pp) improved. See [the v5 feedback review](../../version-5/FEEDBACK_REVIEW.md) for scoring caveats and the [v5 proposal](../../version-5/STRATEGY.md) for the next design. No v5 experiments have been run.

When website feedback arrives, record its exact edition filename, score, component metrics and reported failures. Preserve the original feedback file. Keep the CSV and its metadata immutable; a changed submission gets a new edition.
