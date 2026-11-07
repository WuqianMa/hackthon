# Static bank reconciliation

An offline, deterministic Python program turns verified challenge archives into `final_submission/<phase>/submission.csv`. It uses CSVs, structured payment evidence, native PDF text and a chronological open-item ledger. No model, agent, service credential or network access is used during reconciliation.

See [the detailed proposal](reports/static_system_proposal.md), [verified run results](reports/run_results.md), and [the rule register](docs/rules_register.md). The organizer's documents inside the docs archive remain authoritative.

Python 3.9+; tested with Python 3.9.6. Install the pinned PDF reader in an isolated environment:

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
```

Run these commands from the repository root:

```sh
# Small labeled smoke/evaluation run; evaluates with the official scorer automatically.
.venv/bin/python -m bankrec --phase sample

# Actual available unlabeled phase. Produces final_submission/live/submission.csv.
.venv/bin/python -m bankrec --phase live --phase-archive bankrec-live.tar.gz

# When the FINAL archive and its published checksum arrive:
.venv/bin/python -m bankrec --phase final --phase-archive /path/to/bankrec-final.tar.gz --expected-phase-sha256 PUBLISHED_SHA256

# Optional full TRAIN evaluation. This has not been benchmarked yet.
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
