# V5 website feedback — low-family review

The user reports LIVE 79.34 (+0.29 over v4), with transaction accuracy 87.5%, exception macro-F1 52.9% and amount-weighted accuracy 83.6%. Allocation recall remains 77.3%. Cash pool and AP partial repairs worked at segment level, but the missing-allocation mechanisms remain largely unimplemented.

The user's priority is the ten segments below 50%, not additional model training. The three large families—service month, AR credit-note groups and N-to-M—contain about 5,692 wrong transactions based on approximate website counts. Rare returns and bank charges warrant targeted resolvers and exception-aware evaluation; return segments share RETURNED rather than separate macro labels.

A concrete integration gap is the different return recognizer and recovery-router keyword sets. CHARGEBACK can be recognized yet miss the capped recovery queue. Resolution also requires a restrictive common-reference/exact-cash earlier operation and does not bridge the parsed source groups (`sources=None`). Only one linked return and three credit-netting recoveries were recorded in v5. The tests cover handler behavior but do not establish all router-to-handler paths.

TRAIN can help through relevant older source lookups, a bounded labeled casebook, carefully separated retrieval examples for LLM review, and independent validation. No weight fitting or full feature rebuild is required. Golden data must not become a current-case oracle; future/held-out answers and overlapping episodes must remain out of inference examples.

No code, weights, CSVs or working caches were changed for this review. No pipeline, tests, training, inference, evaluation or LLM calls were run. The complete feedback and proposed repairs are saved under `feedback-evaluation/` and `version-5/WEBSITE_REVIEW.md`.
