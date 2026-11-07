# FINAL edition 001 — completed

The FINAL archive supplied by the user was processed on 7 November 2026 using the packaged frozen strategy. The upload file is **[final-submission.csv](../final-submission.csv)** at the repository root. Identical copies are tracked under `submission/` and `submission/final-strategy/`.

| Result | Value |
|---|---:|
| FINAL bank lines covered | 220,256 / 220,256 |
| Missing bank lines | 0 |
| CSV rows | 678,040 |
| Uncompressed bytes | 29,273,654 |
| Frozen-model coverage | 220,256 bank lines |
| Failed model batches | 0 |
| Model-stage amount fallbacks | 20 transactions to static decisions |
| Final recovery amount fallbacks | 0 |
| End-to-end processing time | 1,200.96 seconds (about 20 minutes) |
| New model training / LLM calls | None / 0 |
| Labeled FINAL evaluation | Not available; not run |

The writer passed the single-pass upload-contract checks for five columns, full phase coverage, catalog IDs, dates, amounts, categories/exceptions, duplicates and limits. No new validation experiment or full aggregate-ledger audit was run, following the deadline instruction. No website upload was performed by the agent.

- CSV SHA-256: `88bff25e848c75cf96ddd711ff7401f470c71d86fd54ea908884d7b5c5cdd4d0`.
- Input archive SHA-256: `04083d6a0b7aa38629a6275399c25b6e3d9444fcd384fdcff25051e09dfac534` (recorded from the supplied archive; no separately published checksum was supplied).
- Frozen model SHA-256: `a883a203fc5bc694812895a14cbd8b125870f435a67bc5e7627ab42e4526eccb`.
- Source system commit: `c487a2a41e53a7a471b6affa9f0fd55bd1382582`.
- Full input hashes, routing counts, timing and source fingerprint: [release manifest](../submission/final-strategy/final_001.json).
- Website feedback: [feedback.md](../submission/final-strategy/feedback.md). No FINAL score is claimed; the prior 81.39 was a separate LIVE result.

Command used:

```bash
python3 final-system/run_final.py --archive /Users/q/Desktop/hackthon/bankrec-final.tar.gz --workers 3
```

The run used FINAL's own opening balances and `masters_final/` overrides, including its updated entities, bank accounts, customers, suppliers and FX rates. No historical VV1 database migration was resumed.
