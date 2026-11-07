# Codex reviews and code-edition records

This folder contains Codex's own assessment of its implementation. It is separate from user instructions and independently authored proposals.

Current review: `2026-11-07_baseline_review.md`, referring to commit `17ce829`, tag `v0.1.0-baseline`.

For each future code edition, add a dated review with:

1. Base commit, scope and the user decision/request that triggered the edition.
2. Observed evidence, including whether results are saved measurements or new experiments.
3. Concrete code locations, proposed mechanism, uncertainties and alternative explanations.
4. Expected behavior changes and possible precision/recall or completeness tradeoffs.
5. Smallest relevant check and dataset; record what actually ran.
6. Files changed, experiment result and unresolved issues after the edition.

Use `docs/strategy.md` for the current proposed architecture. Keep historical reviews intact. Do not label an unrun hypothesis as a verified fix, or an inspected sample as a blind holdout. Before a chosen code change, write the hypothesis; after it, record the evidence.
