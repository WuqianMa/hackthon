# TRAIN to LIVE edition 001 — no LLM judgment

Authorized 7 November 2026. Execute `python3 version-4/train_live.py` from the repository root with the pinned dependencies in requirements.txt. No LLM provider is imported or called by this runner. Prior static LIVE edition 001 remains an explicit candidate.

## Supervision and validation

Scan the full verified TRAIN normalized bank table. Select the 1,500 smallest SHA-256 hashes per month, with fixed seed text `v4-train-42:`, independently of all labels, segments and difficulty. This bounds fitting cost without privileging easy cases. June 2025 is excluded because the starter was inspected during development. All TRAIN invoices, credit notes and indexed PDF clauses are available for candidate generation; this is not a model trained only on starter data.

| Role | Period | Selected bank lines before episode purge |
|---|---|---:|
| Allocation model fitting | July 2021–December 2023 | 45,000 |
| Complete-payment model fitting | January–June 2024 | 9,000 |
| Official-score calibration | July–December 2024 | 9,000 |
| Locked temporal evaluation | January–May 2025 | 7,500 |

Attach golden targets only after candidate generation. Purge an entire earlier-role transaction when any of its true items is also allocated in a later role. The payment model is fitted on allocation probabilities produced without fitting those transactions. Select alpha and static bonus only on calibration. Freeze the model artifact before evaluating the temporal holdout. Do not tune using that result or LIVE feedback.

Calibration includes static bonus 1.0 as an explicit static-only fallback, alongside the starter's bonuses 0, 0.1 and 0.2. This prevents forcing model overrides when they fail to improve the calibration score. It is declared before the held-out evaluation; no test result selects the operating point.

The final production bundle retains these distinct model-fitting roles. This stage does not refit on the locked test period; the same frozen models are used on LIVE. Numeric evidence features and model settings match the starter architecture. Current master snapshots and shared customers remain limitations. Static TRAIN bank history is replayed only for selected transactions: no golden prior-balance features are injected. The baseline comparison therefore uses this same sampled-history reconstruction, and is not a full-TRAIN leaderboard score.

Additional ML alternatives use phase-opening item amounts, as in the starter and LIVE generator. They do not use a ledger advanced to the end of the current month. The chronological static candidate supplies the sampled-history interpretation as a separate hypothesis.

## Scaling and output

SQLite stores the full invoice/reference catalog; a due-date adapter replaces millions of raw invoice dictionaries. Source groups are loaded by month with surrounding files and remittance advice context. Replacement cancellations become effective at the replacement invoice date, avoiding future cancellations suppressing an earlier candidate. This still permits advices to arrive after cash as specified by POLICIES §5.4.

Process all 203,083 LIVE bank lines in bounded batches, with no sampling. LIVE uses its own invoices, opening snapshot, masters, PDF clauses and structured sources. It never loads TRAIN labels during inference. Cache identity ties predictions to the fitted model, candidate code and LIVE archive hash.

Publish immutable CSV copies directly under `submission/` and `submission/v4-strategy/`; edition metadata and the independent hard-contract validation go under `version-4/editions/` and `version-4/training-results/`. Track feedback separately; a local TRAIN holdout score is never a LIVE score. Cross-bank aggregate balance checks keep the already disclosed competition diagnostic status from v3. Unknown IDs, duplicate rows, coverage, amount formatting, dates and official category/exception checks remain blocking.

Training features, catalogs and cached predictions stay under ignored `work/version-4-train/`. Preserve the compact fitted two-model bundle as `version-4/models/train_001.joblib` with its checksum, pinned library versions, feature schema and source hashes. `python3 version-4/train_live.py --mode live` can apply this bundle using only the docs and LIVE archives, without opening TRAIN. Raw TRAIN and LIVE inputs are not committed. Report model/input/output hashes so the exact edition can be reproduced and audited locally.
