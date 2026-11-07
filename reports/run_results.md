# Verified run results — 7 November 2026

The program completed sample and LIVE generation locally. No leaderboard upload was performed. FINAL inputs were not available.

| Check | Sample | LIVE |
|---|---:|---:|
| Bank lines represented / total | 8,499 / 8,499 | 203,083 / 203,083 |
| CSV data rows | 26,030 | 561,520 |
| Uncompressed bytes | 1,119,074 | 24,300,308 |
| Local validation | Pass | Pass |
| Unresolved review lines | 1,721 (20.25%) | 30,794 (15.16%) |
| Advice files parsed / parser issues | 331 / 0 | 6,889 / 0 |
| Unchanged official scorer | 71.32 / 100 | Unavailable: no golden labels |
| Recorded runtime, latest run | 10.252 seconds | 334.488 seconds |

The final measured runs reused extracted archives and previously cached PDF text. LIVE timing includes input verification, catalog rebuilding, source preparation, reconciliation, validation and manifest generation. It is not a cold-cache or full TRAIN benchmark. A cached sample run also completed in 7.208 seconds earlier. Peak memory was not instrumented.

LIVE loaded 487,243 AR invoices, 199,414 AP invoices, 19,500 credit notes and 325,419 opening items; it uniquely linked/read 15,877 indexed document PDFs. Structured inputs produced 1,590 DD batches plus individual receipt records, 1,265 card settlement groups, 1,968 cheque deposits, 55,457 payment-run groups and 6,889 advice groups. Parsing a source group does not prove its allocations were all recovered or matched correctly.

The sample has 18 validation warnings about returns whose prior clearing history is outside the observed period. LIVE stores the first 50 analogous warnings; the warning list is capped, so 50 is not a claimed total. These are disclosed history limitations rather than format/coverage errors. Both validation reports have empty error lists. Unresolved lines receive a valid `UNIDENTIFIED` fallback and remain visible in `unresolved.jsonl`.

Submission SHA-256:

```text
sample  6af440b170cf306c7828cbe51e241b41f1a2909f10e0d1126eaa58b762b4d3b2
live    e33d9b6e97e61cd313510d6b98eb5cb6c1e73065f38d83052b4dbec49d3a5cb6
```

Four completed sample runs produced identical CSV hashes. The suite has 30 passing tests; Python compilation also passed. The official starter scored 11.28 on the same sample. The current sample result is a development-set measurement, not a held-out estimate of LIVE performance.

Production artifact: `final_submission/live/submission.csv`. Sample artifact: `final_submission/sample/submission.csv`. Each directory also has `run_status.json`, `validation.json`, `manifest.json`, evidence and review output. Hash agreement among the CSV, manifest and completed run status was checked after generation.

Reproduce from the repository root with installed `requirements.txt`:

```sh
python3 -m bankrec --phase sample
python3 -m bankrec --phase live --phase-archive bankrec-live.tar.gz
python3 -m unittest discover -s tests -v
```

Machine-readable measurements: `reports/starter_sample_score.json`, `reports/sample_score.json`, `reports/sample_profile.json`, `reports/sample_error_analysis.json`, `reports/sample_run_summary.json`, `reports/live_run_summary.json`, and the respective validation reports. Full input hashes are retained in each output manifest.
