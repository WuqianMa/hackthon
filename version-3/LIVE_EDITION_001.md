# Version 3 — LIVE edition 001

Selected upload file: `submission/static-strategy/submission_v3_live_001.csv`. Identical direct copy: `submission/submission_v3_live_001.csv`.

| Property | Result |
|---|---:|
| LIVE bank lines covered / expected | 203,083 / 203,083 |
| CSV allocation/category rows | 646,942 |
| Uncompressed bytes | 28,008,037 |
| Unresolved bank lines | 13,491 |
| Local upload-contract validation | Pass |
| LIVE website score | Pending user feedback |

SHA-256: `3927ffc1f7f81c234844fbaeb68b97d2f53c4fc85d8bc8c33cc7253a261d8d05`.

The docs and LIVE archive checksums matched the published values. No TRAIN data or v4 model was used. The version-3 entry point was checked against the previous starter output and reproduced 78.65 before LIVE inference. The production correction described below affects no starter row, because that output already passed the same per-document amount check.

## Production correction 3.0.1

The initial LIVE inference completed, but local validation found ten `RETURNED` rows whose applied cash exceeded the document total. Returned rows describe the reopened item amount, so excess cash must not reopen more than the document. The production policy now returns `min(paid, document_total)` for these rows. A new regression test covers full and partial returns; all 12 version-3 mechanism tests pass.

The cached CSV was corrected on exactly those ten rows. No candidate membership or exception label changed. BaseCatalog.apply already updates return balances using `min(total, balance + returned)`: both the old oversized amount and the corrected full-document amount produce the same resulting balance. Therefore later matching decisions remain unchanged and a full LIVE inference rerun was unnecessary.

`editions/live_001.json` records all ten before/after amounts, original and corrected CSV hashes, original inference source hashes, production source hashes, input hashes and validation. Original pre-correction output and full evidence stay under `work/version-3/artifacts/live/`. `finalize_live.py` reproduces this bounded correction and publication from those cached inputs.

Aggregate cross-bank balance warnings remain disclosed diagnostics in the speculative competition profile; the official upload format does not impose that rejection check. The local contract check still enforces IDs, phase, required fields, precision, allowed labels, duplicates, mixed rows, row/byte limits and coverage. Passing these checks is not an assertion of a particular LIVE score.

## Feedback

The user will upload the CSV and provide website feedback. Record it in `submission/static-strategy/feedback.md`, preserving the filename and hash. Do not overwrite edition 001 after submission; generate a new edition for a changed strategy or output.
