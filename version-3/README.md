# Version 3 — LIVE submission edition

Executable copy of the aggressive v3 strategy that scored **78.65** on the starter. `catalog.py`, `engine.py` and `sources.py` are copied unchanged from that measured version. This folder is the requested location for LIVE edition generation. No v4 model is included.

From the repository root:

```sh
python3 version-3/run_tests.py
python3 version-3/run.py --phase sample
python3 version-3/run.py --phase live --edition 001
```

The LIVE command verifies the docs and LIVE archives, prepares inputs, reconciles every LIVE bank transaction, validates the CSV and writes **`submission/submission_v3_live_001.csv`**, plus an identical tracking copy in **`submission/static-strategy/submission_v3_live_001.csv`**. Select the CSV itself in the challenge upload control. The strategy subfolder also holds feedback and edition metadata; do not upload those documents. Sample checks are not published there.

Edition provenance and validation are saved in `version-3/editions/live_001.json`. Full evidence, review output and intermediate files stay in `work/version-3/artifacts/live/`. PDF text is content-hashed and can reuse the existing local cache. Working databases are isolated from the previous runs.

An edition is immutable: a different output requires a new edition number. No website upload occurs automatically. The user will upload this LIVE file and supply leaderboard feedback. Its LIVE score is unknown until that feedback; 78.65 is the starter score only.

Production edition 001 is **3.0.1**: 646,942 rows, all 203,083 LIVE transactions, 28,008,037 bytes, 13,491 unresolved. Final validation exposed ten returned rows above document total; the reopened amount was bounded by the item's total. All original inference and correction details are retained. Because return balance updates were already clamped to total, these ten corrections leave downstream balances and matching unchanged. `finalize_live.py` reproducibly finalizes that cached run without rerunning matching. Normal future runs apply the correction directly in `engine.py`. Details: [LIVE_EDITION_001.md](LIVE_EDITION_001.md).

Policy and task details: [POLICY.md](POLICY.md), [TASKS.md](TASKS.md). Previous starter measurements: [STARTER_RESULTS.md](STARTER_RESULTS.md). The speculative profile retains the competition validation boundary described in those files, including disclosed aggregate balance warnings.
