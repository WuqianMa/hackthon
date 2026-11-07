# V5 LLM judgment contract — design only

## Purpose and route

Add LLM judgment for semantic ambiguity and candidate recovery while keeping existing trained weights. Do not send all 203,083 bank lines to an LLM. No provider calls, API setup or new evaluation are performed by this proposal.

Route using information available at inference: v3/v4 disagreement on item/amount/exception, plan/retention/advance facts, ambiguous service month, unexplained residual, competing party identities, linked return evidence, or absent credible candidates. Low model margin is useful only after it has been obtained through targeted rescoring; existing raw LIVE prediction caches do not contain it. Website segment labels and known golden failures are not routing inputs.

Prioritize expected repair value and shared document reuse. Include both state-sensitive regression cases and recall-recovery cases. Sampling a few ordinary agreements and genuine unidentified/lookalike controls detects an actor that simply forces matches. Do not route only transactions known wrong from labeled analysis.

## Packet

Each packet contains the bank ID and original normalized fields; incumbent v3/v4 rows; candidate IDs/item amounts/currencies/dates; source group links; before-event balance with uncertainty/provenance; payment terms and prior/later connected events; and bounded cached document excerpts. Distinguish bank cash, item-cleared amount and contractual balance. Add bank/format context where relevant.

Attach document content hashes and stable character spans/line spans. Exclude golden allocations, hidden segment/difficulty labels and statements that a case is already known wrong. Uncertainty and model scores are inputs, not truth.

## Decisions

| Action | Effect |
|---|---|
| KEEP | Retain the current valid decision |
| CHOOSE | Select a listed, valid hypothesis with reasoning |
| REQUEST_RETRIEVAL | Request a typed, bounded query for a party/alias, document fragment, service period, related credit/replacement, original operation or account relationship |
| EXTRACT_FACT | Return a structured interpretation and source span, such as retained percentage, service period, tranche completion, advance deduction or voucher-to-invoice link |
| PROPOSE_GROUP | Choose known item IDs from the expanded pool for an episode/group interpretation; deterministic code constructs amounts and valid hypotheses |
| ABSTAIN | Leave the incumbent intact when the revision is not useful |

The actor may prefer a plausible competition guess without a document explicitly naming the final allocation. Record its rationale and uncertainty. Such a judgment is not promoted to a verified documentary fact. IDs must resolve to actual source items; the system constructs numeric rows, applies official policies and checks membership/coverage. Do not invent IDs or modify the closed exception/category lists.

Source-fact loop: cached excerpt → extracted fact → validate source span and parse typed values → regenerate affected candidates → optional second review → deterministic policy/CSV output. A verified quote establishes the quoted clause, not that the LLM's entire interpretation is correct. Check dates, conflicting sources and episode state. Facts about one invoice or party must not be propagated globally without scope.

Existing `version-4/tier3.py` is only a boundary: top-three choice is supported, and EXTRACT_FACT currently preserves the old decision. The retrieval/regeneration loop, provider adapter, bounded queue and evaluation must still be implemented. No score gain is claimed from the existing adapter.

## Proposed initial budget and evidence

- **Pilot: at most 200 routed cases and 400 total LLM calls**, including document extraction and any second round. Maximum two case-review rounds; shared document extraction is cached. These are proposed caps, not an execution instruction today.
- Read cached text first; avoid re-extracting PDFs. If useful text is missing, log/defer that case in the first pilot rather than launch bulk extraction.
- Use one configured provider/model/prompt version initially. Cache requests and structured responses; maintain deterministic reuse. Record input/output tokens, latency, calls, retry counts and cost when the provider reports it. No time or dollar saving is assumed before measurement.
- Record malformed/unsupported revisions, KEEP/ABSTAIN, correct/regressed cases and candidate recovery. A positive routed-case accuracy alone is insufficient: compare the official composite on the same scope and unchanged complement.
- Expand beyond the pilot only after evidence of net benefit and an explicit execution budget. Do not use model self-confidence as the acceptance metric or silently apply repeated reviews until a preferred answer appears.

All changes remain reversible overlays with the incumbent preserved. This is a competition decision workflow; mandatory human accounting approval is not added to each transaction.
