# V4 LIVE edition 001 — ready for upload

The actual upload CSV is **`v4-submission.csv` at the repository root**. Identical edition copies are `submission/submission_v4_live_001.csv` and `submission/v4-strategy/submission_v4_live_001.csv`.

- Phase: LIVE only; all **203,083** bank lines covered.
- Rows: **642,703**; uncompressed bytes: **27,781,139**.
- Exactly the five official columns; known IDs, dates, numeric amounts, categories, exceptions and duplicate/coverage checks pass.
- Official schema validation passes. It uses a bank registry only; no LIVE golden or invented LIVE score is used.
- LLM calls/judgments: **zero**.
- Final decisions changed versus static edition: **10,018**.
- CSV SHA-256: `f3f9262153d47c927a96da78d2df9821cdb73738db698fbfb6acc5c7a37113f1`.
- Frozen model SHA-256: `a883a203fc5bc694812895a14cbd8b125870f435a67bc5e7627ab42e4526eccb`.

The frozen TRAIN temporal holdout is **79.05**, versus **73.34** for static on the same 7,500 cases. This is not the LIVE website score. Website feedback is pending the user's upload; record it in `submission/v4-strategy/feedback.md`.

Initial validation caught 31 transactions where a learned alternative removed a duplicate exception while retaining cash above the document total. A deterministic source-total guard restores the complete validated static decision for these transactions. It preserves the original amounts and does not clamp duplicate cash. No labels, refitting or LLM decisions are used. The same guard changes zero held-out cases, so the measured 79.05 remains unchanged. All repairs are retained in `training-results/live_amount_contract_guard.json`.

The competition profile retains 150 diagnostic ledger warnings (aggregate balance/return history); these are separate from hard submission checks, which have zero errors. The source parser reports zero issues. Independent workers match the first 1,000 LIVE serial decisions exactly.

Edition provenance is in `editions/live_001.json`, with a tracking copy in the submission strategy folder. Raw model-prediction identity is retained separately from final contract-guard code, allowing cached finalization without another inference run:

```sh
python3 version-4/train_live.py --mode live --finalize-only
```

For a fresh working cache, `python3 version-4/train_live.py --mode live --workers 3` applies the preserved model using only the docs and LIVE archives. The edition is immutable: different output must receive a new edition number. This program does not upload to the website.
