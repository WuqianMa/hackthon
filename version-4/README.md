# Version 4 — static + ML decisions + LLM revision

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

User-provided website feedback for static v3 is **77.46** on LIVE. The older `submission_v4.csv` listed in that report is not this ML experiment. No TRAIN or LIVE input was run during the starter experiment; TRAIN is the selected next learning source under STRATEGY.md.
