# Version 6

V6 adds source-linked returns, service-month selection, multilingual PDF facts, credit-net arithmetic and bounded partial-group candidates to the frozen v5 edition. It reuses the fitted model and text caches, without retraining or new LLM calls.

- [Strategy and policy provenance](STRATEGY.md)
- [Execution and measured results](RESULTS.md)
- [Official development scoring](results/development_score.json)
- [Tracked upload and feedback](../submission/v6-strategy/)

Run `python3 version-6/run.py --phase test`, then `--phase live`, then `--publish`. Existing local archives, catalogs, PDF text caches and the immutable v5 CSV are required. See the strategy for tests and exact scope. LIVE inference reads no golden labels. The local development score must not be described as a website score.
