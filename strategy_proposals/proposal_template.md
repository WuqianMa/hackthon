# Strategy proposal — AUTHOR / DATE

Status: proposal, not an implementation decision. Baseline reviewed: COMMIT/TAG.

## Evidence reviewed

List official local docs, code and saved metrics. State which data were inspected and whether any new experiment was explicitly requested and actually run. Do not attribute another branch's results to this baseline.

## Proposed architecture

Describe candidate generation, group completeness, policy arithmetic, ledger/history, uncertainty, conflict handling and export. Identify what stays static and why a model or agent is needed, if proposed.

## Main failure hypotheses

For each, distinguish observed metrics/code from a suspected cause. Give competing explanations and the evidence needed to distinguish them.

## Overfitting controls and fast feedback

Describe the smallest sample/fixture checks, how related events stay together, how inspected development data are labeled, and which rules come from policy/schema versus sample patterns. Full TRAIN is primarily for a justified model-training step, not the routine design-feedback loop.

## First proposed experiment

One mechanism, exact scope, expected tradeoffs, acceptance criteria, runtime/dependencies and keep/revert criteria. This is a proposal only until requested.

## Tradeoffs and unknowns

List complexity, performance, missing history, drift, potential false matches, agent/model dependencies and migration costs. State what the proposal does not yet demonstrate.
