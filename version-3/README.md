# Version 3 — LIVE submission edition

Executable copy of the aggressive v3 strategy that scored **78.65** on the starter. `catalog.py`, `engine.py` and `sources.py` are copied unchanged from that measured version. This folder is the requested location for LIVE edition generation. No v4 model is included.

From the repository root:

```sh
python3 version-3/run_tests.py
python3 version-3/run.py --phase sample
python3 version-3/run.py --phase live --edition 001
```

The LIVE command verifies the docs and LIVE archives, prepares inputs, reconciles every LIVE bank transaction, validates the CSV and writes **`submission/submission_v3_live_001.csv`**. This is the file to select in the challenge upload control. `submission/` contains direct upload CSV editions; no subfolder or report needs to be uploaded. Sample checks are not published there.

Edition provenance and validation are saved in `version-3/editions/live_001.json`. Full evidence, review output and intermediate files stay in `work/version-3/artifacts/live/`. PDF text is content-hashed and can reuse the existing local cache. Working databases are isolated from the previous runs.

An edition is immutable: a different output requires a new edition number. No website upload occurs automatically. The user will upload this LIVE file and supply leaderboard feedback. Its LIVE score is unknown until that feedback; 78.65 is the starter score only.

Policy and task details: [POLICY.md](POLICY.md), [TASKS.md](TASKS.md). Previous starter measurements: [STARTER_RESULTS.md](STARTER_RESULTS.md). The speculative profile retains the competition validation boundary described in those files, including disclosed aggregate balance warnings.
