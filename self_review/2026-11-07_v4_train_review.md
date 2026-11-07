# V4 TRAIN decision-model review

The fixed TRAIN temporal holdout improves from 73.34 to 79.05 over 7,500 cases. Pair precision rises from 77.54% to 90.46%; 296 whole transactions become correct and 24 regress. This supports using the trained decision layer for the requested no-LLM LIVE experiment. It does not prove a LIVE improvement.

The principal remaining limitation is reconstruction: 4,145 of 26,528 required test pairs are absent from the correct item/amount candidate pool. N-to-M, duplicates, replacement semantics and rare exceptions remain poorly represented. The classifier selects among existing proposals; its categorical output space is not a complete replacement for the source/policy engine.

The training pilot uses 70,500 deterministically sampled bank transactions, 41 purged across temporal roles, with the full invoice catalog. Sampled chronological bank history weakens the static ledger, especially repeated-amount FIFO. LIVE's full static history and opening snapshot differ from this reconstruction. A future experiment should build fuller deterministic history and test candidate/exception expansion before simply increasing tree depth or adding DL. The current edition is frozen; held-out errors have not been used to tune this submission.

Engineering checks preserve starter candidate rows/features, all 8,982 starter source groups (including short supplier references), and exact serial/worker decisions on 1,000 starter transactions. SQLite caching/mapping and a read-only source preloader improve throughput. LIVE workers also matched their first 1,000 decisions exactly against a serial reference. The LIVE source parser reports zero issues. Hard CSV checks remain separate from the disclosed competition aggregate-balance diagnostics.

A diagnostic NumPy int8 positive-count overflow was caught and corrected with int64 summation. This did not modify targets or fitted models. No LLM provider or judgment is used in this stage. Detailed measured evidence and reproduction commands are in `version-4/TRAIN_RESULTS.md`.
