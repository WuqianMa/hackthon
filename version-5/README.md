# V5 proposal — reuse the model, recover candidates, review ambiguous cases

**Status: design only, 7 November 2026.** No solver changes, training, inference, evaluation, tests or LLM calls were run for this proposal. Existing submissions, weights and caches remain unchanged.

Decision: retain the trained v4 models and PDF cache; improve the decision/policy layer and targeted retrieval; add a bounded LLM revision actor. No new ML/DL training is planned.

- [FEEDBACK_REVIEW.md](FEEDBACK_REVIEW.md): v4 versus v3 website results, precision/recall interpretation and evidence-backed diagnosis.
- [STRATEGY.md](STRATEGY.md): selected architecture, priorities, cache reuse, and staged validation plan for later authorization.
- [LLM_REVIEW.md](LLM_REVIEW.md): routing, permitted decisions, fact regeneration and proposed pilot budget.

The new source report is `../v4-feedback.md`, found through Git's untracked-file listing. It reports **LIVE 79.05 versus v3 LIVE 77.46**. The earlier TRAIN holdout also scored 79.05, coincidentally; its population and components differ.

The first implementation stage should repair evidence-backed amount/exception decisions and retain v4's useful matching improvements. The following stages should widen recall candidates and test LLM revisions on a small, preselected queue. No v5 score or submission exists yet. Completed documentation stages are committed/pushed to `q`; `main` is unchanged.
