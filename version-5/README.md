# V5 proposal — reuse the model, recover candidates, review ambiguous cases

**LIVE edition 001 is complete, 7 November 2026.** Upload repository-root [`v5-submission.csv`](../v5-submission.csv). Copies and feedback are under `submission/v5-strategy/`. All 203,083 LIVE bank lines are covered; 642,703 rows. Website score is pending.

The cached 7,500-case development score is **79.29**, versus v4 **79.05**. Policy/recovery alone scored 79.25; the 24-case LLM pilot improved it to 79.29. LIVE used 48 separate LLM reviews, changing 23 decisions. No learned weights were retrained and no bulk PDF extraction was performed. See [RESULTS.md](RESULTS.md).

Run from the repository root with the pinned v4 dependencies and existing caches:

```sh
python3 version-5/run.py --phase test --packet-limit 24
python3 version-5/run.py --phase live --packet-limit 48
# Replay the preserved, hash-bound LLM decisions:
cp version-5/llm/live_001.jsonl work/version-5/llm_decisions.jsonl
python3 version-5/run.py --phase live --publish
```

The runner consumes the existing v4 model-generated CSV, catalogs and source/PDF caches; it does not rebuild TRAIN or refit a model. LLM reviews were performed through isolated Codex reviewer agents and are cached for deterministic replay. A standalone provider API adapter is not included. Changed packet context requires a new review rather than accepting a stale cached decision.

The design below preceded execution. Its broad retrieval/LLM roadmap includes future work; RESULTS.md states precisely what this edition implements.

Decision: retain the trained v4 models and PDF cache; improve the decision/policy layer and targeted retrieval; add a bounded LLM revision actor. No new ML/DL training is planned.

- [FEEDBACK_REVIEW.md](FEEDBACK_REVIEW.md): v4 versus v3 website results, precision/recall interpretation and evidence-backed diagnosis.
- [STRATEGY.md](STRATEGY.md): selected architecture, priorities, cache reuse, and staged validation plan for later authorization.
- [LLM_REVIEW.md](LLM_REVIEW.md): routing, permitted decisions, fact regeneration and proposed pilot budget.

The new source report is `../v4-feedback.md`, found through Git's untracked-file listing. It reports **LIVE 79.05 versus v3 LIVE 77.46**. The earlier TRAIN holdout also scored 79.05, coincidentally; its population and components differ.

The first edition repairs evidence-backed amount/exception decisions and adds bounded relationship/period/category recovery and LLM choices. General multi-bank N-to-M optimization and provider-driven catalog tools remain future work. Completed stages are committed/pushed to `q`; `main` is unchanged.
