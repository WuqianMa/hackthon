# v3 implemented task chain

1. **Archive → inputs:** existing checksum verification, safe extraction, CSV/gzip loading, master snapshot and SQLite item index.
2. **Facts and roles:** current/historical names plus truncated prefix retrieval; parent/group expansion; mandate index; retained credit-to-invoice metadata; PDF instalment amounts.
3. **Containers:** corrected mail gross/deduction arithmetic; existing PDF/CSV/XLSX adapters; whole run, transfer and maturity units.
4. **Hypotheses:** baseline full structured match; partial container recovery; reference groups with credit closure; party subsets; anchored residual search; ranked single-item and partial reference candidates.
5. **Policy/event:** item-currency clearing arithmetic, final instalment/remainder phrases, credit payouts and mandate returns.
6. **Decision/ledger:** chronological selection, with weak speculative hypotheses deferred from ledger mutation in the aggressive profile. A full phase-wide competition between all hypotheses is not yet implemented.
7. **Export/evaluation:** temporary CSV, contract validation, artifact hashes, evidence and unresolved records; unchanged official scoring after inference.

Entry point: `python3 -m v3 --speculative`. Artifact: `final_submission/v3/sample/submission.csv`. Runtime code imports no analysis scripts, golden lookup tables, Claude artifacts or Gemini artifacts. The original `bankrec` implementation is unchanged.

## Remaining work before the 90+ gate

The first v3 implementation tests concrete improvements rather than rebuilding every proposed S1–S9 module. Rich retention/advance/service-month schedules, full return-event graphs, a global conflict pass, complete candidate-stage recall instrumentation, and learned ranking remain incomplete. Large missing groups, confirming, DD returns and N-to-M allocations still need starter-level investigation. Re-evaluate the next mechanism using the same full sample and genuine unidentified controls; do not launch TRAIN or LIVE merely because v3 improved.
