# `gemini/` — third-proposal work folder

Created 7 November 2026 at the user's request: *“create a gemini folder for your argument and in english, and propose how to make it not simplified task chain.”*

**Nothing in this folder is part of the solver.** No file here is imported by `bankrec/`. No solver code was changed, no pipeline or scorer was run, and no TRAIN, LIVE or sample data file was opened while writing it.

## Authorship

Written inside the Antigravity agent session. **The model selected for that session at writing time was Claude Opus 5.5, not a Gemini model.** The folder name follows the user's instruction. Following `AGENTS.md` (“do not fabricate their positions”), whether this counts as the Gemini proposal is the user's call. It was written *after* reading the Claude proposal, so it is not independent of it.

## Contents

| Path | Contents |
|---|---|
| `task_chain_spec.md` | The non-simplified task chain: stages S0–S9, their typed outputs, policy references, stage metrics, module map |
| `../strategy_proposals/2026-11-07_gemini_strategy.md` | The proposal itself (template format): review of Codex and Claude, architecture summary, failure hypotheses, first experiment, overfitting controls, tradeoffs |

## One-paragraph argument

Codex (oversimplified event model) and Claude (retrieval failure, costly abstention) describe the same defect from opposite ends. The baseline reasons about **items**: one payer, one open amount, one flat list, one container level, then labels the cash difference. The official policies describe **payment events**: remitter vs debtor, planned tranches, related credits, multi-level payment files, state-dependent exceptions. Changing the decision unit to a `PaymentHypothesis` — built from bank-event facts, debtor scope, settlement units and self-reconciling containers, explained by policy arithmetic, committed phase-wide by evidence tier, and interpreted by a ledger state machine — fixes the retrieval gap and the decision errors together. A measurement-only stage-attribution harness (E0) should run first so the edition order is decided by data, not by whichever proposal argues best.

## Scope constraints followed

- Starter/sample only for any future experiment; TRAIN reserved for a defined model task (`human_comments/2026-11-07_workflow.md`, `2026-11-07_starter_score_target.md`).
- No LIVE/FINAL/full-TRAIN runs; saved artifacts are quoted, not regenerated.
- `strategy_proposals/decision.md` was **not** edited by this work (it has uncommitted edits from the Claude session); the user may add the row when deciding.
