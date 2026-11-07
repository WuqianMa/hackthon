# Version 4 — TRAIN-fitted static + ML decisions

**LIVE edition 001 is ready:** repository-root `v4-submission.csv`, with identical copies in `submission/` and `submission/v4-strategy/`. See [LIVE_EDITION_001.md](LIVE_EDITION_001.md). All 203,083 bank lines are covered; 642,703 rows. Website feedback is pending.

Current edition uses **no LLM judgment**. Two gradient-boosted models fitted on TRAIN score **79.05** on 7,500 temporal holdout cases, versus **73.34** for static reconstruction on the same cases (**+5.71**). See [TRAIN_RESULTS.md](TRAIN_RESULTS.md) for metrics, sampling, regressions and limitations, and [TRAIN_EXECUTION.md](TRAIN_EXECUTION.md) for the production protocol.

The preserved model is `models/train_001.joblib`. With the docs and LIVE archives in the repository root:

```sh
python3 -m pip install -r version-4/requirements.txt
# Apply the fitted model without reading TRAIN:
python3 version-4/train_live.py --mode live --workers 3
# Reproduce the bounded TRAIN fit/evaluation and then apply to LIVE:
python3 version-4/train_live.py
```

The LIVE runner covers every bank line and publishes `submission/submission_v4_live_001.csv` plus an identical tracking copy in `submission/v4-strategy/`. Upload the CSV itself. Edition metadata records the model/submission hashes and validation; website feedback is tracked separately. The local 79.05 is **not a LIVE website score**. Data/context scans use the full archive; supervised fitting selects 70,500 bank cases across 47 months before temporal purging, rather than fitting every TRAIN bank line.

## Earlier starter experiment

Selected direction: [STRATEGY.md](STRATEGY.md). Original dialogue plan: [PROPOSAL.md](PROPOSAL.md). Measured experiment: [RESULTS.md](RESULTS.md), protocol [EXPERIMENT.md](EXPERIMENT.md).

**Starter score: 80.95**, versus **78.65** for static v3 on the same 8,499 cases. This is pooled group-held-out prediction from two HistGradientBoostingClassifier models, not an in-sample score or a LIVE result. No deep network or LLM revisions contribute to 80.95.

From the repository root, using the versions in requirements.txt:

```sh
python3 version-4/build_candidates.py
python3 version-4/test_experiment.py
python3 version-4/run.py
```

Candidate generation verifies/extracts only the 10 MB docs bundle and never reads labels. The training program attaches sample labels after candidate generation, uses disjoint model/calibration/test groups, and scores with the unchanged official scorer. Rebuild the candidate cache after modifying generation. `run.py` otherwise reuses it. Data and models stay in `work/version-4`; source and measured results are versioned here.

`results/submission_v4_sample_oof.csv` contains **sample-only** predictions, not a LIVE submission. Fold assignments, feature definitions, model hashes and validation are in results/.

Tier 3 is allowed. `tier3.py` exports label-free evidence packets and validates explicit revisions to existing hypotheses. Current run: 1,125 eligible cases, 200 exported to `work/version-4/tier3_review_queue.jsonl`, zero external LLM calls. New extracted facts require candidate regeneration. Provider selection and a scored revision experiment remain to be implemented.

User-provided website feedback for static v3 is **77.46** on LIVE. The older `submission_v4.csv` listed in that report is not this ML experiment. No TRAIN or LIVE input was run during the earlier starter experiment. The TRAIN-fitted execution above is a separate measured stage.
