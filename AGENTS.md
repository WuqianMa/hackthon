## Current working direction — user update, 2026-11-07

Latest authorized stage: the user requested implementation and execution of `v3/` on the starter sample, with aggressive competition matching, meaningful commits, and a push to remote `q` after each completed stage. This supersedes the proposal-only restriction below for that scope. The measured selected v3 score is 78.65; continue starter development toward 90+ before expanding to TRAIN/LIVE. See `v3/README.md`, `v3/POLICY.md`, `v3/TASKS.md`, `v3/RESULTS.md` and `human_comments/2026-11-07_v3_execution.md`. Do not push remote `main`.

The user is comparing system strategies before selecting the next implementation. Read `human_comments/2026-11-07_workflow.md`, `docs/strategy.md`, and `self_review/2026-11-07_baseline_review.md` first. This update takes precedence over the older recommended execution sequence below.

- Keep `v0.1.0-baseline` as the initial implementation reference. The existing sample and LIVE measurements are historical evidence, not a request to rerun them.
- During this comparison stage, review code, feedback and saved results; write proposals and reviews. Do not launch whole-pipeline, LIVE, FINAL, or full-TRAIN runs as a default next step, or change the solver before the strategy decision.
- When an experiment is requested, use the smallest starter/sample dataset for fast design feedback. Identify sample-dependent heuristics and avoid claiming that a repeatedly inspected sample proves generalization.
- Full TRAIN is primarily for a justified model-training step. State the model's task and evaluation split before using it; a whole-corpus run is not required to discuss or compare architecture.
- Keep human comments in `human_comments/`, Codex's code/design reviews in `self_review/`, and separately authored proposals in `strategy_proposals/`. The user will obtain Claude and Gemini proposals; do not fabricate their positions.

---

From GPT5.6 on description of dataset without exploring data
# Bank Reconciliation Challenge — Agent Collaboration Guide

> **Purpose:** Shared context and execution instructions for multiple coding/AI agents working on the bank-reconciliation challenge. Read this document before starting any task. The organizer's `README.md`, `POLICIES.md`, `FORMAT.md`, and local scorer are authoritative wherever this guide is incomplete or differs.
>
> **Status:** This guide is based on the challenge description provided by the team. It is **not** a replacement for inspecting the actual archives and rules.

## 1. Mission

Build a reliable bank-reconciliation pipeline that maps bank statement transactions to receivables/payables/open items, classifies non-item transactions, and generates a **valid, high-scoring submission CSV** for the designated phase.

### Success criteria

1. Ingest normalized bank transactions and relevant accounting/document sources.
2. Use the labeled **TRAIN** data to develop and evaluate matching and exception-handling methods.
3. Produce allocations covering **every** bank line in the selected **LIVE** or **FINAL** phase.
4. Meet all submission-schema, ID, numeric, file-size, and row-count constraints.
5. Validate locally and avoid spending leaderboard submissions on preventable errors.

**Do not invent policies, tolerances, exception labels, or scoring weights.** Obtain them from `POLICIES.md`, `FORMAT.md`, `categories.csv`, and the bundled scorer.

## 2. Challenge phases and scale

| Phase | Coverage | Bank lines | Additional information | Labels / availability |
|---|---|---:|---|---|
| **TRAIN** | 2021-07 → 2025-06 | 1.49 M | 3.96 M AR invoices; 1.53 M AP invoices; 131 k PDFs | Golden allocations available |
| **LIVE** | 2025-07 → 2025-12 | 203 k | 16.7 k PDFs; `open_items_at_start.csv` | No golden; public leaderboard |
| **FINAL** | 2026-01 → 2026-06 | 220 k | Same general input families as LIVE | Released near event end; scores hidden until reveal |

- Approximately **70 segments** and **1.91 M bank lines** in total across phases.
- The organizer states **FINAL is released at 18:00 Madrid time**; confirm actual availability on the event site.
- A submission contains **one phase only**: **LIVE** *or* **FINAL**, never both.

### Download bundles

| Bundle | Description | Download size | SHA-256 |
|---|---|---:|---|
| `bankrec-docs-and-masters.zip` | Documentation, masters, one-month sample with golden, Python starter and scorer | 10 MB | `210b2404efd011af248a251db2bc0ee85a2ddaa1d56a7a0ca0b95ede18cc1071` |
| **TRAIN lite** (`train-lite`) | Every table with golden; raw bank statements and PDFs only from 2024-07 onward; laptop-friendly | 460 MB | `71defe3aa552855daae9338d83234438f1de40f0d7b7ec7cdb56327b4c11df1e` |
| **Full TRAIN** (`train`) | All four years of labeled training data and supporting documents | 657 MB | `163f51a818193f6310b6fba96e3830e4347c883b0b84bc070153f5018e3f06b8` |
| **LIVE** (`live`) | Unlabeled 2025-07 → 2025-12 inputs, including opening items | 87 MB | `eec490d7c605048d0d3a8400af97ee13c9fe49e68dfeb3d68546daf50d8af520` |
| **FINAL** (`final`) | 2026-01 → 2026-06 inputs | Not yet provided in the brief | Not provided in the brief |

**Suggested initial path:** Download docs/masters and TRAIN lite first. Start with the one-month sample and local scorer; expand to full TRAIN if more raw statements/PDF history is needed.

**Integrity:** Check each archive against its published SHA-256 before processing. These hashes are **checksums, not download URLs**; retrieve archives from the event's official download controls.

## 3. Files and data model

### Authoritative docs and reference tables

| Path | Purpose |
|---|---|
| `README.md` | Challenge overview and general rules |
| `POLICIES.md` | Accounting and matching policies, including tolerances and discounts |
| `FORMAT.md` | Submission format and validation requirements |
| `masters/entities` | Legal/accounting entities |
| `masters/bank_accounts` | Bank-account reference data |
| `masters/customers` | Customer master data |
| `masters/suppliers` | Supplier master data |
| `masters/categories` | Permitted **non-item** category values |
| `masters/payment_terms` | Terms relevant to due dates/discounts |
| `masters/fx_rates` | Daily reference FX rates |

*The exact file extensions under `masters/` were not specified in the brief; inspect the archive before coding paths.*

### TRAIN and related inputs

| Path | Content / usage |
|---|---|
| `train/bank_statements/` | Raw bank statements: Norma 43 (`.txt`), MT940 (`.sta`), camt.053 (`.xml`), organized by bank/account/month |
| `train/bank_transactions.csv` | Normalized view of the same bank lines, including raw text fields |
| `train/ar_invoices.csv` | Accounts receivable invoices |
| `train/ap_invoices.csv` | Accounts payable invoices |
| `train/credit_notes.csv` | Credit notes |
| `train/remittance_advices/` | Remittance records in CSV, XLSX, PDF and email-like text |
| `train/payment_runs/` | Outgoing payment files |
| `train/direct_debit_batches/` | Direct-debit batches |
| `train/card_settlements/` | Card settlement data |
| `train/pdfs/` | Source documents; sometimes the only place containing essential context |
| `train/golden_allocations.csv` | Ground-truth allocations for TRAIN only |
| `sample/` | One-month example with golden labels |
| `starter/starter.py` | Baseline that writes a valid CSV |
| `starter/scorer` | Local scorer using the leaderboard formula |

The `live/` and `final/` directories contain equivalent phase inputs; **LIVE** explicitly includes `open_items_at_start.csv`. Inspect real filenames/schemas before relying on any assumed paths.

### Identifier rules

- Every bank line has a unique `bank_txn_id`, e.g. `BT-2025-0001234`.
- Each open item has an `item_id`, e.g. `ARI-…`, `API-…`, or `ARC-…`.
- Documents also have **printed document numbers**. Bank narratives may mention these printed numbers rather than internal `item_id` values.
- Build a lookup from normalized printed document identifiers to candidate items; **never assume a printed invoice number is the same as `item_id`**.
- Preserve identifiers exactly as strings, including leading zeros.

## 4. Submission contract — MUST FOLLOW

Submit one UTF-8 CSV with a header, using commas, named `submission.csv` (or optionally `submission.csv.gz`).

**Columns, in order:**

```csv
bank_txn_id,item_id,amount,category,exception
BT-2025-0001234,ARI-2025-0456789,1210.00,,
BT-2025-0001234,ARI-2025-0456790,605.00,,
BT-2025-0001240,,,BANK_FEES,
BT-2025-0001300,ARI-2025-0400001,980.00,,SHORT_DISCOUNT
BT-2025-0001301,,,UNIDENTIFIED,UNIDENTIFIED
```

### Semantics

- **One row per allocation.** A bank transaction may allocate to several items, using multiple rows.
- `bank_txn_id`: ID of the bank transaction to which the row belongs.
- `item_id`: matched item; leave empty if the bank line does **not** clear an item.
- `amount`: **amount of the item cleared**, expressed in the **item currency**, to **two decimal places**. This is not necessarily the amount of cash in the bank line.
- `category`: fill **only when the row settles no item**; value must be listed in `masters/categories` / `categories.csv`. Otherwise leave empty.
- `exception`: use only values in the challenge's **closed exception list**. Consult the rules; examples shown here include `SHORT_DISCOUNT` and `UNIDENTIFIED` but are **not** a full enumeration.
- **Early-payment discounts or eligible charges within tolerance:** the item is considered **fully cleared**, so `amount` must equal its open amount; `exception` indicates why bank cash differs from the cleared item amount.

### Hard limits and rejection conditions

- Maximum **60 MB uncompressed**.
- Maximum **3,000,000 rows**.
- Every bank line in the target phase must be represented. **Omitting bank lines is scored as wrong.**
- Unknown IDs, duplicate `(bank_txn_id, item_id)` pairs, or invalid numeric values invalidate the submission; row-level errors are reported.
- Follow any additional schema/format rules in `FORMAT.md` and the local validator/scorer. Do not assume the examples constitute the entire specification.

### Critical modeling cautions

1. Separate **bank cash amount** from **item-cleared amount** and track their currencies.
2. Respect opening items, document dates, and phase boundaries; do not assume all relevant invoices were issued in the current phase.
3. Multiple invoices can be matched by one bank line; avoid a forced one-to-one matcher.
4. Classify non-item lines using only permitted categories, not ad hoc labels.
5. Keep uncertain cases visible for debugging; uncertainty/confidence is **internal metadata**, not an extra submission column.
6. Check whether one item can be partially cleared or matched across multiple bank lines according to the actual policies before encoding allocation constraints.

## 5. Recommended processing workflow

### Stage A — bootstrap and rule extraction

- Download docs/masters, verify SHA-256, and read `README.md`, `POLICIES.md`, and `FORMAT.md` end to end.
- Inspect `starter/starter.py` and the scorer to understand required output and the **actual scoring function**.
- Run the starter on `sample/` and reproduce the sample's local evaluation.
- Publish an internal **rules register**: accepted categories/exceptions, tolerances, currency and FX treatment, discount treatment, partial payments, and any allocation constraints. Each entry should cite the source filename/section.

### Stage B — ingestion and indexing

- Parse normalized CSVs first; use raw MT940/Norma 43/camt.053 where they add information.
- Standardize amounts using decimal arithmetic, dates, currencies, counterparty identities, document references, and free-text bank narratives.
- Create indexes for `bank_txn_id`, `item_id`, printed document numbers, account/customer/supplier identifiers, and phase/open-item status.
- Ingest structured remittance, payment-run, debit-batch, and card-settlement files before using costly PDF extraction.
- Extract PDFs only where needed and cache results keyed by document/source ID.

### Stage C — candidate generation and allocation

Use multiple evidence channels, keeping score contributions auditable:

1. Exact references from bank narrative → printed document number → `item_id`.
2. Structured remittance advice → listed document(s) and amounts.
3. Outgoing payment runs / direct debit batches / card settlements → bank transactions and supported groupings.
4. Party identity, account, payment date, currency, and invoice amount.
5. Policy-compliant discounts, bank fees, charges, FX and other exceptions.
6. Fallback classification for transactions that genuinely settle no item.

Produce candidate allocations with supporting evidence. Resolve conflicts globally where necessary, rather than accepting a local match that causes impossible double allocation elsewhere.

### Stage D — training evaluation

- Compare predictions against `train/golden_allocations.csv` using the **provided scorer**, not an improvised replacement.
- Evaluate separately by time period, statement type, account/entity, transaction family, single-vs-multi-item matching, and exception class.
- Use time-based holdouts to approximate behavior on future LIVE/FINAL periods. Prevent golden leakage into validation features.
- Maintain error samples and regression tests for known failures.
- Avoid overfitting solely to superficial ID ordering or training-only patterns.

### Stage E — phase inference and submission

- Run the final pipeline on **LIVE** or **FINAL** with only that phase's legitimately available inputs and previously learned rules/models.
- Check coverage for **every** bank line, duplicates, category/exception membership, amount precision, aggregate allocation constraints, file size, and row count.
- Generate **exactly five columns**, in the required order, with no index column, comments, or debug metadata.
- Self-evaluate on TRAIN before consuming a LIVE leaderboard submission. FINAL scores are hidden until the event reveal.

## 6. Multi-agent collaboration plan

Assign independent workstreams to agents with stable artifacts and clear interfaces. The division below is a **recommended team workflow**, not an organizer requirement.

| Agent | Scope | Expected deliverable |
|---|---|---|
| **A — Rules & scorer** | Read official docs; enumerate valid categories/exceptions; inspect scorer; establish tests | `docs/rules_register.md`, `tests/test_submission_validation.py`, scoring instructions |
| **B — Ingestion & references** | Inspect source schemas; load CSV, bank statements and masters; index printed document numbers | `src/ingest/`, `src/normalize/`, source schema notes |
| **C — Structured matching** | Exact reference matching, remittance, payment runs, debit batches, card settlements | `src/matching/structured.py`, candidate evidence output |
| **D — Long-tail matching** | Ambiguous narratives, PDFs, multi-item allocations, discounts and exception candidates | `src/matching/long_tail.py`, extraction cache, evaluated examples |
| **E — Evaluation & integration** | Merge candidate streams, resolve conflicts, compare with golden, validate and export | `src/reconcile.py`, `src/validate_submission.py`, experiment results |

**If working with fewer agents:** Combine A+E and B+C first. Treat D as a specialized follow-up once a valid baseline works.

### Shared interfaces

To prevent agents from inventing incompatible schemas, agree on these **internal** tables before parallel coding:

**`bank_lines`** — original `bank_txn_id`, amount, currency, date, account, narrative and any original source fields.

**`open_items`** — original `item_id`, document/printed reference, party, item currency, open amount, dates, item type and relevant original source fields.

**`allocation_candidates`** — `bank_txn_id`, `item_id` (nullable), proposed item-cleared amount, category (nullable), exception (nullable), source/evidence label, confidence (optional internal field), and method version.

Internal field names are **suggested**, not source-file schemas. Only the five official fields belong in the exported submission.

### Collaboration rules

1. **One owner per module.** Avoid simultaneous edits to shared files; work in separate branches/worktrees or clearly separated modules.
2. **Source-ground every rule.** Agent A owns the rules register. Other agents must not hardcode assumptions without a reference.
3. **Preserve original data.** Use read-only raw inputs and derived/cached outputs in separate locations.
4. **Define interfaces first.** Agree on candidate schema, currency/decimal types, nullable values, and deduplication logic before merging work.
5. **Record evidence.** Every proposed allocation should be explainable by source file, reference, rule, or matching strategy.
6. **Run tests before handoff.** Submit code + command to reproduce + metrics + unresolved cases; do not hand off vague claims such as “matching is done.”
7. **Control training leakage.** TRAIN golden is for supervision/evaluation only; do not read hidden labels or fabricate LIVE/FINAL goldens.
8. **Never silently drop transactions.** Unresolved bank lines must remain visible and be handled according to the official rules.
9. **Keep output deterministic.** Sorting, tie-breaking and serialization should be reproducible.

### Agent handoff template

Each agent's handoff should contain:

```markdown
## Workstream: <agent / module>
- Implemented: <files, functions, behavior>
- Inputs used: <phase and exact paths>
- Rules relied on: <POLICIES.md / FORMAT.md section>
- Test command: <reproducible command>
- TRAIN score / metrics: <from provided scorer, if available>
- Known limitations: <ambiguous cases and failure modes>
- Files changed: <list>
- Next integration step: <specific action>
```

## 7. Release checklist (blocking)

- [ ] Official `README.md`, `POLICIES.md`, and `FORMAT.md` read; rule register completed.
- [ ] Required archives downloaded and SHA-256 validated.
- [ ] Sample loop reproduced with `starter/starter.py` and bundled scorer.
- [ ] Correct phase selected (**LIVE** or **FINAL**, not a mixture).
- [ ] Every target `bank_txn_id` represented in output.
- [ ] Header exactly `bank_txn_id,item_id,amount,category,exception`.
- [ ] Item currency and two-decimal precision validated for each cleared amount.
- [ ] No unknown `bank_txn_id` or `item_id`; no duplicate `(bank_txn_id, item_id)` pairs.
- [ ] `category` used only for non-item allocations; all values from official list.
- [ ] `exception` values valid; discount/charge rules implemented from policies.
- [ ] Aggregate matching, open-item, and partial-clearance constraints verified against policies.
- [ ] UTF-8 comma-separated valid CSV; no index or extra columns.
- [ ] ≤ 60 MB **uncompressed** and ≤ 3 M rows.
- [ ] TRAIN local scorer results recorded; all submission validation tests pass.

## 8. First actions for the next agent

1. Locate the official download bundles; verify hashes and extract **docs/masters + sample**.
2. Inspect `README.md`, `POLICIES.md`, `FORMAT.md`, `starter/starter.py`, and the scorer; report any requirements missing from this guide.
3. Implement and test a **fully valid sample baseline** before optimizing matching accuracy.
4. Load TRAIN lite; document actual schemas and establish a time-based validation split.
5. Start structured exact-reference matching, evaluate with the official scorer, and hand off reproducible metrics.

**Important unknowns until docs are inspected:** full exception enumeration, exact category values, thresholds/tolerances, FX/discount formulas, detailed scorer behavior, allowed partial-allocation constraints, and any additional format or file validation rules.
