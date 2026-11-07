# Static bank reconciliation

**V4 LIVE submission ready:** [v4-submission.csv](v4-submission.csv) at the repository root. Identical edition copies are under `submission/` and `submission/v4-strategy/`. All 203,083 LIVE transactions are covered; 642,703 rows, no LLM judgment. Website score pending. See [edition details](version-4/LIVE_EDITION_001.md).

Latest completed training stage: [version-4](version-4/README.md) fits two gradient-boosted decision models on a temporal TRAIN sample. The official score is **79.05**, versus **73.34** for static reconstruction on the same 7,500 held-out cases (**+5.71**). The [TRAIN report](version-4/TRAIN_RESULTS.md) documents the 70,500-case sample, complete invoice context, split, candidate limits and regressions. This edition uses **no LLM judgment**.

V4 LIVE workflow: `python3 version-4/train_live.py --mode live --workers 3` applies the preserved trained artifact to all LIVE lines and writes `submission/submission_v4_live_001.csv`, with its tracking copy and feedback under `submission/v4-strategy/`. The TRAIN score is not a LIVE website score. The earlier [starter result](version-4/RESULTS.md) was 80.95 versus 78.65 on a different population.

Previous static LIVE edition: [version-3](version-3/README.md) generated [edition 001](version-3/LIVE_EDITION_001.md), `submission/static-strategy/submission_v3_live_001.csv`. Its [feedback record](submission/static-strategy/feedback.md) reports 77.46. An identical direct copy remains in `submission/`; all 203,083 LIVE bank lines are covered. The original [version-4 dialogue proposal](version-4/PROPOSAL.md) is preserved as historical context.

Earlier executable experiment: [strategy v3](v3/README.md), including [competition policy](v3/POLICY.md), [task chain](v3/TASKS.md) and [measured results](v3/RESULTS.md). `python3 -m v3 --speculative` scores **78.65** on the starter, versus **71.32** for the preserved baseline. All 8,499 starter transactions are covered; 710 remain unresolved. The 90+ target remains unmet. Completed stages are pushed to remote `q`.

The original offline baseline turns verified challenge archives into `final_submission/<phase>/submission.csv`. It uses CSVs, structured payment evidence, native PDF text and a chronological open-item ledger. That original baseline uses no model; the v4 workflow above adds fitted ML decisions and runs offline without an LLM service.

See [the detailed proposal](reports/static_system_proposal.md), [verified run results](reports/run_results.md), and [the rule register](docs/rules_register.md). The organizer's documents inside the docs archive remain authoritative.

Earlier stage: **strategy comparison**. The [Codex proposal](docs/strategy.md) and [baseline self-review](self_review/2026-11-07_baseline_review.md) document the reasoning before the user authorized v3 implementation. The later v4 TRAIN fitting and LIVE application follow the user's explicit execution request.

The initial implementation is preserved at Git tag `v0.1.0-baseline` (commit `17ce829`). [Human comments](human_comments/README.md), [Codex reviews](self_review/README.md), and [independent strategy proposals](strategy_proposals/README.md) have separate locations. V4 is the selected current execution; the Claude and Gemini proposals remain available for future comparisons.

Python 3.9+; tested with Python 3.9.6. Install the pinned PDF reader in an isolated environment:

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
```

Commands below are a runbook for a requested experiment or later production run. They are not the current task queue. Run from the repository root:

```sh
# Small labeled smoke/evaluation run; evaluates with the official scorer automatically.
.venv/bin/python -m bankrec --phase sample

# Actual available unlabeled phase. Produces final_submission/live/submission.csv.
.venv/bin/python -m bankrec --phase live --phase-archive bankrec-live.tar.gz

# When the FINAL archive and its published checksum arrive:
.venv/bin/python -m bankrec --phase final --phase-archive /path/to/bankrec-final.tar.gz --expected-phase-sha256 PUBLISHED_SHA256

# Deferred whole-TRAIN command; use only for a specifically chosen training/evaluation task.
# This is not the default architecture-feedback loop and has not been benchmarked.
.venv/bin/python -m bankrec --phase train --phase-archive bankrec-train.tar.gz --evaluate

.venv/bin/python -m unittest discover -s tests -v
```

Use `--docs-archive`, `--work-dir` or `--output-dir` to override paths. `--no-pdfs` is an explicit reduced-coverage mode and is recorded in the manifest. The program requires the normalized CSV families and opening-items snapshot for LIVE/FINAL; it fails on missing required inputs or incompatible master schemas. It supports ZIP and TAR archives with the documented phase folder inside. FINAL metadata overlays baseline masters by stable primary keys.

Each completed run writes:

| File | Use |
|---|---|
| `submission.csv` | Exactly the five official columns; the only file intended for challenge upload. |
| `validation.json` | Coverage, known IDs, precision, limits, duplicate/mixed rows and aggregate balance checks. |
| `manifest.json` | Input/archive hashes, code version, methods, exceptions, parser issues, runtime and submission SHA-256. |
| `run_status.json` | Only use a file when this says `complete` and its hash matches. A failed rerun may leave the previous successful submission. |
| `evidence.jsonl` | Per-bank-line method, allocations and reference/source evidence. Internal only. |
| `unresolved.jsonl` | Bank-line context for future development or agent review. Internal only. |
| `score.json` | Official score and per-segment metrics, for sample or explicitly evaluated TRAIN only. |

Raw archives are unchanged. Extraction goes into `work/archives/`, native PDF text is cached by content hash, and SQLite indexes/working balances go into `work/runs/<phase>/`. Keep an extracted cache immutable; delete the corresponding extracted directory to rebuild from its verified archive. Do not run two jobs for the same phase/work directory concurrently. Independent phase directories can run separately.

The original baseline does not claim complete accounting-policy coverage. Unresolved lines use `UNIDENTIFIED` as a schema-valid fallback and are separately listed for review. The detailed proposal and v4 TRAIN report record the limitations, including incomplete historical clearing and specialized PDF interpretation. The FINAL archive is not present; production output is **LIVE**, never a mixture of LIVE and FINAL. These programs do not upload to the leaderboard.
