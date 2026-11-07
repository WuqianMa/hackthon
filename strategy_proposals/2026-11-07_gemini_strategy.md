# Strategy proposal — Gemini folder / 7 November 2026

Status: **proposal, not an implementation decision.** Baseline reviewed: commit `17ce829`, tag `v0.1.0-baseline` (HEAD `3e237d4` adds only documentation). Working folder: `../gemini/`. Detailed design: [`../gemini/task_chain_spec.md`](../gemini/task_chain_spec.md).

> **Authorship note (read first).** The user asked for this proposal to be filed under `gemini/` as the third, independent proposal. It was written inside the Antigravity agent session, and **the model selected for that session at writing time was Claude Opus 5.5, not a Gemini model.** Per `AGENTS.md` (“do not fabricate their positions”), the user should decide whether this document stands in for the Gemini proposal or whether a proposal from an actual Gemini model is still wanted. It was written after reading the Claude proposal, so it is *informed by*, not independent of, that proposal.

Headline: **Codex and Claude are describing the same defect from two ends.** Codex says the task chain is oversimplified (wrong representation of the payment event); Claude says retrieval fails (candidates never reach the pool). Most of Claude's refused lines are refused *because* the event representation is too thin — no payer/debtor split, no tranche amounts, no credit links, one grouping level. The fix is not “more retrieval” or “better decisions” but **changing the unit of reasoning from an item to a payment hypothesis**, with stage-level metrics that settle the priority argument by measurement rather than debate.

---

## 1. Evidence reviewed

**Official (read):** `work/archives/docs/POLICIES.md`, `FORMAT.md`, `DATA_DICTIONARY.md` (fields: `related_document`, `parent_customer_id`, `group_id`, `run_type`, `end_to_end_id`, `re_presentation`, advice `payer_name`).

**Code (read):** `bankrec/engine.py`, `bankrec/catalog.py`, structure of `bankrec/sources.py` and `bankrec/cli.py`.

**Team artifacts (read):** `AGENTS.md`, `human_comments/*`, `docs/strategy.md`, `self_review/2026-11-07_baseline_review.md`, `self_review/2026-11-07_why_71_and_path_to_90.md`, `strategy_proposals/2026-11-07_claude_strategy.md`, `claude/README.md`, `strategy_proposals/decision.md`.

**Data touched:** none directly. No TRAIN, LIVE or sample file was opened. No experiment, scorer run or pipeline run was performed. Every number below is **quoted** from the Codex or Claude documents and attributed; derived estimates are labelled as estimates.

---

## 2. Review of the two existing proposals

### 2.1 Where Codex is right

- The diagnosis in `why_71_and_path_to_90.md` is the most accurate description of *why* the system fails: payer ≠ debtor (case B), wrong grouping level (case C), PDF facts read but not applied (D), `related_document` dropped (E), advice deduction parsed as paid amount (F), and excess labelled before completeness is known (A). I verified each against code: `catalog.py:80-83` sets `balance=total` and stores no relationships; `catalog.py:136-141` reduces PDF clauses to booleans; `engine.py:144-146` scopes lookup to the payer; `engine.py:289` excludes credits from subsets; `engine.py:296` gives the whole cash to one item.
- The facts / candidates / decisions / ledger decomposition is correct and I keep it.

### 2.2 Where Claude is right

- The **measured** priority: refused-to-allocate transactions (bucket A, 1,482 txns) hold ~22 of ~29 points of headroom on the sample (Claude `a5`, scorer reproduced at 71.32).
- Retrieval instrumentation (`pair_recall`, `group_completeness`) must be first-class; Codex itself marked it “not currently measured”.
- The `for/else` at `engine.py:197-207` discards a whole container when one entry fails — a code-level defect with a measured footprint (687 multi-item txns emit nothing).
- `UNIDENTIFIED` must be a positively evidenced class, not a sink.

### 2.3 Where I differ from Claude

**(a) The 0 % break-even is an oracle-selected result.** `a6` sweeps guessing only over the 1,482 lines *known from golden* to have items. A real system cannot tell those apart from the ~218 genuinely unidentified lines that share the same fallback today and are currently scored correct (Claude reports both unidentified segments at 100 %). Guessing on the *whole* fallback population would also:

- turn ~218 correct transactions wrong (≈ −2.6 pp transaction accuracy ≈ −0.8 points), and
- drive the `UNIDENTIFIED` class F1 toward 0 instead of toward ~0.9, which reverses most of the macro-F1 gain `a6` credits.

A back-of-envelope estimate using the `a6` slope (~0.2 points per percentage point of hit rate) puts the realistic break-even somewhere around **high single digits to low teens percent**, not 0 %. This is an estimate, not a measurement. It does not overturn Claude's conclusion — a decent retriever will clear that bar easily — but it means the headline must not be used to justify blanket guessing, and the positive-evidence `UNIDENTIFIED` profile is load-bearing, not optional.

**(b) “Best-explained subset = explains the most cash” is dangerous in deep pools.** Subset search inside a 15.7× deeper LIVE pool (Claude's own figure) finds coincidental sums. I would allow subset generation **only inside one resolved debtor scope**, and rank hypotheses lexicographically by evidence tier before cash coverage (spec S5–S6).

**(c) Retrieval is not a separate layer to bolt on.** Of Claude's two strongest mechanisms, M1 (truncated name) is a party-role problem and M2 (reference expansion) is a reference-form problem; Codex's parent-payer, run-level and credit-link cases are also retrieval failures that land in bucket A (case B is literally an `UNIDENTIFIED` output). Building a retrieval layer without changing the representation would retrieve items for a payer-scoped, total-amount, flat-list model of the world and still fail on those.

### 2.4 Where I differ from Codex

- **Completeness as a veto is too strict.** Codex's decision layer outputs “an accepted complete proposal or an explicit reason for uncertainty”. I agree with Claude that an incomplete but evidenced hypothesis should be **emitted**, with only the label uncertainty invalidates (`OVERPAYMENT`) withheld (`INCOMPLETE_EXCESS` in the spec).
- **The two-stage decision needs a concrete shape.** I specify it as phase-wide batch: generate for all lines, then commit by evidence tier, then chronologically (spec S7). This also handles advices that arrive after the cash (§5.4), which a streaming waterfall cannot.
- **Measure before ordering editions.** Codex's current edition 1 (structured evidence fixes) is plausible, but neither Codex's scenario taxonomy nor Claude's buckets attribute a failure to the *stage* that caused it. I propose that measurement first (§5).

---

## 3. Proposed architecture: the non-simplified task chain

Full specification: [`../gemini/task_chain_spec.md`](../gemini/task_chain_spec.md). Summary:

| Stage | Output object | What it restores (POLICIES ref) |
|---|---|---|
| S0 Ingest | normalized tables (keep) | — |
| S1 Bank event facts | `BankEvent`: channel candidates, remitter span, typed reference spans, period phrase, markers | Channel before category (§4 card ≠ fee); reference forms (§5.5) |
| S2 Party roles | remitter, intermediary, **debtor scope** | Parent/group, confirming ORD., EXPTE, payment factory (§5.1–5.2) |
| S3 Item graph | **settlement units** per item + relationship edges | Instalments, retention, advance, dispute residual (§3, §5.8); credit links (§5.9); replacement (§5.7); returns (§5.10) |
| S4 Containers | multi-level, self-reconciling parsed sources | Run / maturity / EndToEndId levels (§5.3); advice gross–deduction–net (§5.4) |
| S5 Hypotheses | `PaymentHypothesis` set, nothing committed | Partial container resolution; credit closure; service month before FIFO (§5.6) |
| S6 Explanation | residual class + lexicographic order | Policy arithmetic applied **after** membership is known (§2–§3) |
| S7 Resolution | two-pass, tier-ordered commitment | Conflicts and late advices handled phase-wide |
| S8 Ledger | per-unit state machine | `DUPLICATE_PAYMENT`, remainder-after-partial, final instalment, `RETURNED` from state |
| S9 Output | allocations or evidenced `UNIDENTIFIED`; export (keep) | §3 “do not force a match” scoped to its real meaning |

Three design principles:

1. **The decision unit is a payment hypothesis**, not an item. Items remain the submission unit.
2. **PDF facts become arithmetic.** An instalment clause produces tranche amounts that the cash can match, rather than a boolean that nothing reads.
3. **Lexicographic, policy-ordered ranking** replaces tuned integer weights; fewer free parameters means less to overfit.

### What stays static, and where models or agents could help

Static and non-negotiable: ingest and hashes, identifiers, integer-cent and FX arithmetic, policy mapping (S6/S8), ledger, export and validation. All of S1–S9 can be deterministic.

Later model tasks, each only with a stated schema, target, baseline and temporal split on TRAIN:

- **Remitter → debtor-scope ranking** from noisy, truncated, renamed bank text (labels: golden item → party). This is the same task Claude identifies; it plugs into S2 without touching anything else.
- **Hypothesis ranking inside a bounded set** — only once S5 metrics show the golden set is usually present.

Agents, offline only: proposing parsers for unseen advice layouts (the September 2025 relayout, §6), with **container self-reconciliation (S4) as the automatic acceptance check**. An agent-proposed parser that fails its own total check is rejected without human review.

---

## 4. Main failure hypotheses (stage-attributed)

| # | Observed (quoted source) | Stage hypothesis | Competing explanation | Distinguishing evidence |
|---|---|---|---|---|
| H1 | 1,482 refused txns; N43 refusal 25.6 % vs camt 9.8 % (Claude `a2`/`a3`) | S2: no debtor scope from truncated remitter text | Lines genuinely carry no information | Debtor-scope recall on refused lines with an oracle-free resolver; Claude's M1 already reaches 27.9 % |
| H2 | Parent-payer advice with 36 docs output as `UNIDENTIFIED` (Codex case B) | S2: scope not expanded via `parent_customer_id` | Advice parsing failed | Advice parses and reconciles; lookup scoped to payer removes subsidiary item |
| H3 | 67/67 `ap_confirming` fail; 42 have run refs (Codex case C) | S4: wrong grouping level | Missing prior-month files | Level-specific sums equal bank cash in the cited example |
| H4 | 228 of 231 false `OVERPAYMENT` on multi-item goldens (Codex case A) | S6 runs before S5 completeness | Overpayment policy misimplemented | Re-label with completeness gating; check true overpayments survive |
| H5 | Final instalment labelled `PARTIAL` (Codex case D) | S3: no tranche units | History missing | PDF schedule alone identifies the final tranche |
| H6 | 687 multi-item txns emit nothing (Claude `a3`) | S5: all-or-nothing container resolution | Groups genuinely fail cash reconciliation | Log per discarded group which entry failed and whether the total matched |

---

## 5. First proposed experiment — E0: stage-attribution harness (measurement only)

**Why first.** Codex and Claude disagree on order mostly because neither can attribute a wrong transaction to the earliest stage that caused it. E0 produces that table and changes no decision.

- **Scope.** Add instrumentation that, for each sample transaction, computes golden-derived stage facts (channel, debtor party, unit amounts, container level, golden set) and checks whether the baseline's internal artifacts (`evidence.jsonl`, candidate sets) contained them. Assign each wrong transaction to the earliest failing stage S1…S8. Starter sample only. Golden is read only by the harness, never by the solver.
- **Pre-registered acceptance.** (1) Official sample score unchanged at 71.32 (any change means leakage). (2) Every one of the 2,045 wrong transactions is assigned exactly one earliest stage. (3) Stage totals reconcile with Claude's buckets and Codex's failure table (e.g. bucket A + D + E split across S1–S5). (4) Runs in minutes, standard library only.
- **Output.** A points-at-stake table **per stage**, using Claude's verified counterfactual scorer method (replace that stage's failures with golden, re-score). The edition order is then read off that table.
- **Revert.** Pure addition; delete if not useful.

**Default sequence after E0** (to be re-ordered by its result):

| Order | Edition | Stages | Absorbs |
|---|---|---|---|
| E1 | Flag-off equivalence: chain skeleton reproduces 71.32 bit-for-bit | all | protects baseline comparison |
| E2 | Debtor scope: IBAN/mandate + truncated-name + parent/group/payment-factory expansion | S2 | Claude E1, Codex case B |
| E3 | Containers: level selection + partial resolution + self-reconciling advice parser | S4, S5 | Claude E4, Codex cases C, F |
| E4 | Item graph: credit links, tranche units from PDF clauses | S3 | Codex cases D, E |
| E5 | Explanation + output rule: residual classes, `INCOMPLETE_EXCESS`, evidenced `UNIDENTIFIED` | S6, S9 | Claude E3, Codex case A |
| E6 | Two-pass resolution + ledger state machine | S7, S8 | Codex edition 2 |

Every edition ships behind a flag, reports the stage metrics in the spec §2, and is kept only if its own stage metric improves without regression in the official components.

---

## 6. Overfitting controls and fast feedback

1. **Self-reconciliation over golden.** Container parsers are accepted by internal totals (S4), which do not require labels and carry over to LIVE/FINAL layouts.
2. **Policy-derived synthetic fixtures.** Small hand-built cases written from `POLICIES.md` alone (3-instalment plan, 10 % retention, discount at day +3 and +4, SHA charge at 59 and 61 EUR, parent-pays-subsidiary, credit netting). They test rules independently of the inspected sample.
3. **Decoy-density stress** (Claude C1, adopted): pad the item pool with cloned items at shifted dates; pair precision must hold at 2×/4×/8×. Directly guards the scoped-subset generator.
4. **Format stratification** (Claude C2, adopted): every metric per `statement_format`; N43→camt migration on 2025-10-01 is inside LIVE.
5. **Rule provenance** (Claude C3 / Codex rules register): each rule tagged `POLICY` or `EMPIRICAL`; no customer-ID keyed rules; lexicographic ranking leaves few tunable weights.
6. **Scenario-family holdout for diagnosis.** Develop a mechanism while watching only the families it targets; check the other families for regressions afterwards. Still inspected data — a regression check, not a generalization claim.
7. **Plausibility alarms** (Claude C6, adopted): `UNIDENTIFIED`, `OVERPAYMENT` and generator-mix shares outside expected ranges warn in `validate.json`.
8. **Named blind spots.** Opening-balance path and `SHORT_WITHHOLDING` are not exercised by the sample (both proposals agree); the synthetic fixtures in (2) are the only pre-TRAIN coverage for them.

Full TRAIN remains reserved for a defined model task (S2 ranker first), with a temporal split.

---

## 7. Tradeoffs and unknowns

- **Nothing here is implemented or measured.** All numbers are quoted from Codex/Claude artifacts; the break-even in §2.3 is a labelled estimate.
- **Complexity.** Seven modules instead of one `engine.py`. Mitigation: each stage has one owner, one typed output and one metric; flags allow incremental rollout; E1 guarantees baseline equivalence.
- **Hypothesis volume.** Generating all hypotheses phase-wide costs memory and time; LIVE ran in 334 s on the baseline, so there is budget, but p99 hypotheses per line must be capped and monitored.
- **Settlement units depend on PDF parsing quality.** A misparsed schedule produces wrong tranche amounts that look exact. Units must carry `history = known | assumed` and source spans.
- **False debtor scopes are the worst failure shape** (confident wrong answer). Scope ambiguity keeps multiple scopes alive into S6 instead of picking one.
- **Renamed customers** (§5.5, §6) cannot be fully solved from current masters; this is where the S2 model trained on TRAIN history earns its place.
- **FINAL drift** (ZA01, ZAR, `KWI…` numbering, updated masters) is untested by design at this stage.

**Migration cost.** Moderate. S0 and S9 are unchanged; S2/S3/S4 are additive; S5–S8 replace `structured`/`reference_match`/`policy` ordering and immediate `apply`. Baseline tag remains the comparison point.
