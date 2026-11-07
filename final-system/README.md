# FINAL submission system

Self-contained execution folder for the unseen FINAL phase. Includes the frozen trained model, its pinned dependencies, the base masters, official policy/format documents, and the V3–V6 source needed by the runner. It does not depend on a `q` checkout or a TRAIN archive.

VV1's historical database migration was stopped at the user's request. This release uses the existing competition strategy: **V3 static matching → frozen V4 model → V5 policy recovery → V6 source/document mechanisms**. V6's historical LIVE website score is **81.39**; no FINAL score is known. No training, labeled evaluation, database migration or LLM judgment runs here.

## Run when the FINAL file arrives

From the repository root:

```bash
python3 final-system/run_final.py --archive /path/to/bankrec-final.tar.gz
```

ZIP and TAR archives are supported. If the organizer provides a SHA-256, add `--expected-sha256 HASH`. For an already extracted phase folder:

```bash
python3 final-system/run_final.py --phase-dir /path/to/final
```

Outputs:

- **`final-submission.csv`** at the repository root — the upload file.
- Identical `final-system/output/final-submission.csv` and its run manifest.
- `final-system/work/runs/final_<fingerprint>/run_status.json` must say `complete` and its SHA-256 must match the CSV.

Upload only the CSV. The program does not submit to the website. The official FINAL competition permits one scored submission per team.

## Runtime and resume

The first run extracts only the unseen phase, builds that phase's operational item/opening-balance catalog, parses its sources, and applies existing trained weights. It does **not** copy millions of historical TRAIN rows into a new database. New PDFs use native text extraction in parallel; existing content-hash text is reused. On this workspace, the runner automatically finds `work/cache/pdf_text` in the repository root. Elsewhere, use `--pdf-cache /path/to/existing/pdf_text`.

Progress prints after PDF/cache chunks, static matching and ML batches. Re-run the exact same command to resume completed static/source/ML checkpoints. Input, model and vendored-source fingerprints isolate datasets; never reuse a LIVE output as a FINAL prediction.

Default: three model/PDF workers. Use `--workers 2` on a memory-limited laptop. Default ML inference processes all bank lines. If the competition clock demands a cutoff, `--ml-budget-minutes 20` stops scheduling new ML waves after that budget; the remaining lines retain static decisions and still receive V5/V6 recovery. The manifest records that reduced ML coverage. The budget applies to the model stage, not total end-to-end time; an in-flight wave is allowed to finish.

`masters_final/` overrides baseline master rows by stable IDs, retaining old records and allowing added columns. FINAL's own opening balances and invoice history are used. The runner checks booking dates against the selected phase and supports updated entities/currencies through those masters. Required normalized input files are bank transactions, AR/AP invoices, credit notes and opening items, plus their payment/document source directories.

## Dependencies and startup check

The current machine already has the required packages. On a fresh Python 3.9+ environment:

```bash
python3 -m pip install -r final-system/requirements.txt
python3 final-system/run_final.py --check-environment
```

The startup check verifies the frozen model checksum and loads both fitted models. It does not process a dataset or compute a score. The command and model loading were checked during packaging. No end-to-end FINAL run can be reported before its input is released. Per the deadline instruction, no new scoring experiment or validation suite was run for this packaging change.

The output writer makes fast, single-pass upload-contract checks: exact five columns, complete phase coverage, IDs, dates, nonnegative item-currency amounts, duplicate pairs, categories/exceptions, and file/row limits. It does not perform a labeled evaluation or a full aggregate-ledger audit. These checks prevent a malformed upload from consuming the FINAL attempt.

## Files and provenance

- `run_final.py`: archive/phase entry point, orchestration, checkpoints, publication.
- `version-3/`, `version-4/`, `version-5/`, `version-6/`, `bankrec/`: frozen dependency source copied from `q` commit `01d19d1`.
- `version-4/models/train_001.joblib`: the existing two-head fitted model; SHA-256 `a883a203fc5bc694812895a14cbd8b125870f435a67bc5e7627ab42e4526eccb`.
- `resources/masters/`: baseline master snapshot; FINAL overrides it.
- `resources/POLICIES.md`, `FORMAT.md`, `DATA_DICTIONARY.md`: official input/output rules.
- `VENDORED_SOURCES.json`: original file hashes and strategy provenance.

The original V6 manual LIVE LLM decisions are specific to those LIVE transaction IDs and are not applied to unseen FINAL IDs. No new LLM calls are made. The runner therefore preserves the automatic strategy, with frozen ML inference and source/period/relationship recovery, without claiming an identical score on a new phase.
