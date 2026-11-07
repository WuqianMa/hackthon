# User direction — TRAIN-fitted v4 and LIVE submission

User: “run strategy on training dataset and then apply to live without llm judgement.for v4 submission”

This authorizes TRAIN model fitting and full LIVE inference, superseding the previous starter-only execution limit. LLM judgment is disabled for this edition. Generate a submission CSV for the user to upload; website feedback remains separate from local validation.

Implementation choice communicated during execution: scan all 1,489,931 TRAIN bank lines and retain a deterministic, label-independent 1,500-per-month sample over 47 months (70,500 cases before episode purging). Keep full invoice history and PDF clauses searchable. Fit the two models and calibrate on separate temporal periods; reserve January–May 2025 for evaluation. The same frozen bundle is then applied to every LIVE bank line. This sampling is an implementation choice, not a claim that the user requested this specific sample size.

Preserve prior submissions. Track the new edition and feedback under `submission/v4-strategy/`, with a direct upload copy in `submission/`. Commit and push completed stages to remote `q`; leave `main` and the other authors’ working files unchanged.
