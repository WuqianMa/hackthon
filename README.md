# Bank Reconciliation Hackathon

**Team:** Jiahua Tang · Wuqian Ma  
**Best score:** **81.39/100** (V6 LIVE; 203,083 bank transactions).

## Key idea
Reconstruct **payment events**, rather than just match equal amounts. Link bank lines, invoices, credit notes, batches and multilingual PDF/TXT/XLSX remittances using references, entities, dates, currencies and open balances. Enforce accounting rules for netting, instalments, service periods, returns and exceptions.

## Stack & models
**Python, SQLite**, indexed catalogs, cached native PDF text, file parsers and a chronological integer-cent ledger. V4 trained two **scikit-learn HistGradientBoostingClassifier** models for allocation and payment-hypothesis decisions. V5 added policy/ledger fixes and limited LLM review; V6 used deterministic rules to recover document links and returns without retraining.

## Evolution
**V3 77.46 → V4 79.05 → V5 79.34 → V6 81.39** (LIVE website scores). A parallel high-precision rule-based solver reached **75.29** on the jiahua branch. Our best result combines learned ranking with source-grounded rules.

## Next
Build **VV1**: a country- and language-tagged relational database linking extracted document facts and business entities. Use it for complete payment hypotheses, especially **N:M and invoice–credit-note** matching, and benchmark against V6.

**Implementation:** [q](https://github.com/WuqianMa/hackthon/tree/q) · [jiahua](https://github.com/WuqianMa/hackthon/tree/jiahua).
