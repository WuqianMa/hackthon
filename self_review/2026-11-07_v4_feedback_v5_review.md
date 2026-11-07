# V4 website review → V5 proposal

Read-only code/report review on 7 November 2026. No solver code, model weights, submission CSVs or working caches were changed; no training, inference, evaluation, tests or LLM calls were executed. Two independent internal reviews examined feedback/scoring and implementation/cache reuse.

The user-provided LIVE report improves from 77.46 to 79.05, with both precision and recall higher. Retention, AP partial and late-discount losses require attention despite the aggregate gain. Identical TRAIN and LIVE headline scores are separate results.

The strongest code-level concern is using exception-insensitive allocation confidence to select exception variants, including `static_blank`. State-sensitive amount/exception semantics need a separate decision layer. The sampled TRAIN ledger and opening-balance alternatives also differ from the full static LIVE history. These mechanisms are supported by inspection and the earlier 31 invalid blank duplicate proposals; aggregate website feedback alone cannot prove each individual failure's cause.

The v5 design retains the 49/81-feature frozen models and all PDF/source/catalog caches. First repair observable policy/state disagreements, then add targeted group/period/return/category candidates. LLM judgment is proposed for ambiguous clauses, choices and retrieval expansion, with a real fact-to-candidate regeneration loop and a bounded later pilot. Competition guesses remain eligible; they are not treated as verified documentary facts.

Do not trust the report's scenario-as-macro-class explanation, projected score gains, or the local mining note's claim that FX original amounts are unused. Claude's earlier oracle counterfactuals concern the 71.32 starter baseline, not current LIVE routing. Detailed evidence and implementation order are preserved in `version-5/FEEDBACK_REVIEW.md`, `STRATEGY.md`, and `LLM_REVIEW.md`.
