# Static bank reconciliation

Latest requested edition: [version-3](version-3/README.md) runs the frozen aggressive strategy on LIVE and publishes direct upload CSV editions in `submission/`. Use `python3 version-3/run.py --phase live --edition 001`. The user handles website upload and supplies feedback. The hybrid [version-4 proposal](version-4/PROPOSAL.md) is saved for later and has not been implemented or trained.

Current executable experiment: [strategy v3](v3/README.md), including [competition policy](v3/POLICY.md), [task chain](v3/TASKS.md) and [measured results](v3/RESULTS.md). `python3 -m v3 --speculative` scores **78.65** on the starter, versus **71.32** for the preserved baseline. All 8,499 starter transactions are covered; 710 remain unresolved. This is an improvement, with lower pair precision, and the 90+ target remains unmet. No new TRAIN/LIVE run was made. Completed stages are pushed to remote `q`.

An offline, deterministic Python program turns verified challenge archives into `final_submission/<phase>/submission.csv`. It uses CSVs, structured payment evidence, native PDF text and a chronological open-item ledger. No model, agent, service credential or network access is used during reconciliation.

See [the detailed proposal](reports/static_system_proposal.md), [verified run results](reports/run_results.md), and [the rule register](docs/rules_register.md). The organizer's documents inside the docs archive remain authoritative.

Earlier stage: **strategy comparison**. The [Codex proposal](docs/strategy.md) and [baseline self-review](self_review/2026-11-07_baseline_review.md) document the reasoning before the user authorized v3 implementation. Full TRAIN remains reserved for a justified model-training step. Existing LIVE results are historical measurements; they do not require repeating the full run now.

The initial implementation is preserved at Git tag `v0.1.0-baseline` (commit `17ce829`). [Human comments](human_comments/README.md), [Codex reviews](self_review/README.md), and [independent strategy proposals](strategy_proposals/README.md) have separate locations. The final strategy decision remains open for the user's comparison with Claude and Gemini.

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

The current implementation is a measured baseline, not a claim of complete accounting-policy coverage. Unresolved lines use `UNIDENTIFIED` as a schema-valid fallback and are separately listed for review. The detailed proposal records current limitations, including unavailable historical clearing/source records and incomplete specialized PDF interpretation. The FINAL archive is not present; the delivered production-phase file is **LIVE**, never a mixture of LIVE and FINAL. This program does not upload to the leaderboard.
