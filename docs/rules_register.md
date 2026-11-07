# Rules register

Authority: the checksum-verified `bankrec-docs-and-masters.zip`, especially `POLICIES.md`, `FORMAT.md`, `DATA_DICTIONARY.md`, and unchanged `starter/bankrec_score.py`. The root `AGENTS.md` and `bank_reconciliation_challenge_analysis.md` are planning notes, not organizer rules. This register separates official rules from implementation decisions.

| Subject | Official rule and source | Current implementation |
|---|---|---|
| Item types | ARI, ARC, API, APC; proformas/advice files are not items. POLICIES §1 | All four prefixes; a proforma payment is a category. |
| Normal amount | Full open amount in **item currency**, positive; credit notes also positive. POLICIES §1–2 | Integer cents; positive credit-note rows; subtract credits only in cash arithmetic. |
| Full clearing | `SHORT_DISCOUNT`, `SHORT_BANK_CHARGES`, `SHORT_WITHHOLDING`, `FX_DIFFERENCE`, `OVERPAYMENT` use full open amount. POLICIES §2 | Policy function returns remaining open amount for these cases. |
| Partial/dispute | `PARTIAL`, `SHORT_DISPUTE` use actually applied amount. POLICIES §2–3 | Subtract actual paid amount from balance; reason-bearing advice deductions become disputes. |
| Discount | Invoice terms must have a discount; booking date ≤ issue date + discount days + 3 grace days; discount on **total**, rounded to cents. POLICIES §3 | Decimal half-up arithmetic; tested at the grace boundary. Opening snapshot lacks invoice terms: historical metadata remains a limitation. |
| Late discount | Difference remains open, so `PARTIAL`. POLICIES §3 | Fails eligibility check and stays partial. |
| Bank charge shortfall | Transfer from outside SEPA; shortfall ≤ EUR 60 equivalent AND ≤ 2% of item. POLICIES §3 | Requires explicit charge narrative and known non-SEPA country as additional conservative evidence. |
| Withholding | Certain customers in MX/BR/MA; rates 1.25%, 1.5%, 10% of total. POLICIES §3 | Checks eligible country and exact rate arithmetic; certificate/customer-specific eligibility still needs richer evidence. |
| Duplicate | Already settled item paid again; amount paid again; no second balance reduction. POLICIES §2–3 | Recognized when earlier clearing is observable. No closed-item history is inferred from missing items. |
| Return | Original allocated amount reopens items; applies to DD, cheque, card and rejected AP transfer. POLICIES §2–3 | Supported when original source/item is available; caps balance and flags incomplete history. |
| FX | Different cash/item currency; reference-rate deviation within 3%; prior available rate on non-business days; original currency amount preferred. Fully cleared invoice rows get FX; partial/dispute keep code; credit rows stay empty. POLICIES §3, dictionary Masters | Original amount/currency then reference-rate check; no FX gain/loss journal. |
| Card settlement | Allocate **gross** orders; contractual net fee is no exception. POLICIES §4–5 | Batch bank amount compared with net total, allocation rows use gross. |
| Credit-note refund | Supplier refund of its credit note clears APC. Duplicate cash refund is a category. POLICIES §4–5 | APC matches supported; explicit refund narratives categorized. Ambiguous refunds remain a limitation. |
| Third-party payer | Parent, factor, collection agency may pay for underlying customer. POLICIES §5.1 | References and full embedded party aliases; no arbitrary cross-party match. |
| Payment factory | ES00 can pay ES01/ES02/PT01 items. POLICIES §5.2 | Structured beneficiary resolution can cross account entity; unscoped cross-entity guesses rejected. |
| Structured batches | DD receipts, card orders, cheques and payment-run documents expand into item rows. POLICIES §5.3 | Explicit source parsers; incomplete/ambiguous expansion abstains as a group. |
| Advice timing | Advice can arrive after cash. POLICIES §5.4 | Parse phase advices before inference; received date does not block use. |
| Noisy references | Prefixes/zeros omitted, truncations, PO references, old numbers. POLICIES §5.5 | Exact normalized, numeric, suffix, PO and replacement indexes; suffix matches require corroboration. |
| FIFO/service month | Same amount: oldest open invoice unless named service month. POLICIES §5.6 | FIFO supported. PDF service-month fact extraction is partial; month-aware resolution is pending. |
| Replacement | Old invoice cancelled; cash citing it clears replacement; old invoice/cancelling credit never bank-cleared. POLICIES §5.7 | Recognized replacement invoice adds old-number alias and marks original cancelled. Cancelling-credit exclusion needs further relation logic. |
| Plans/retention/advance | Non-final instalments, first retention payment, advance deducted are partial; final payments/releases are empty. POLICIES §3, §5.8 | Correct when balance history is present; facts retained for future parsers. Incomplete sample history cannot establish every final instalment. |
| Re-presentation | Re-presented DD or later transfer has no return exception. POLICIES §3, §5.10 | Normal later clearing uses reopened balance. |
| Unidentified | No open item exists: category and exception both `UNIDENTIFIED`; unrelated equal amount is no evidence. POLICIES §3 | No global amount-only matching. Unresolved fallback has these labels but remains explicitly identified as uncertain in review output. |
| Drift | Moncayo changes format Oct 2025; advice layout Sept 2025; FINAL has ZA01/ZAR and updated masters. POLICIES §6 | Normalized bank view, schema checks, FINAL master overlays. Changed layouts are logged, not silently accepted. |
| CSV contract | 5 columns; every target bank ID; no duplicates or mixed category/item rows; ≤ 3M rows; ≤ 60MB. FORMAT | Canonical order, UTF-8 LF, two decimals, stricter catalog membership and full coverage. Scorer code uses **60 × 1024² bytes**. |
| Score | 50% allocation F1, 30% transaction accuracy, 20% exception macro-F1. FORMAT; scorer `_score` | Call organizer scorer unchanged after inference only. |
| Amount scoring tolerance | max(0.01, 0.5% of golden amount). FORMAT; scorer `_tol` | Used for evaluation only. Matching generally requires exact cents; this is **not** a matching-policy tolerance. |

The closed exception list is: empty, `PARTIAL`, `OVERPAYMENT`, `SHORT_DISCOUNT`, `SHORT_BANK_CHARGES`, `SHORT_WITHHOLDING`, `SHORT_DISPUTE`, `DUPLICATE_PAYMENT`, `UNIDENTIFIED`, `RETURNED`, `FX_DIFFERENCE` (FORMAT).

The category list has 21 codes, read from the master at runtime: `BANK_FEES`, `INTEREST_INCOME`, `INTEREST_EXPENSE`, `PAYROLL`, `SOCIAL_SECURITY`, `TAX_PAYMENT`, `TAX_REFUND`, `LOAN_DRAWDOWN`, `LOAN_REPAYMENT`, `LEASING`, `FX_DEAL`, `CASH_POOL`, `INTERCOMPANY`, `INTERNAL_TRANSFER`, `CUSTOMER_ADVANCE`, `CUSTOMER_REFUND`, `SUPPLIER_REFUND`, `CARD_EXPENSES`, `INSURANCE`, `BANK_REVERSAL`, `UNIDENTIFIED`.

Engineering bounds, **not organizer policy**: one-cent numerical slack for same-currency cash comparisons; 3-day proximity for an amount-linked batch without a reference; 45-day check for referenced non-return groups; subsets of at most 6 invoices from at most 24 party candidates with 20,000 states; full phase source preparation before chronological allocation; lexical bank-ID ordering within a booking day. These settings control computation/ambiguity and need time-based TRAIN validation.

Scorer caveats discovered in code: syntactically valid unknown item IDs are not rejected against an item catalog; omitted bank IDs reduce accuracy rather than reject the file; blank categories and some header irregularities pass weaker checks. Our exporter/validator intentionally enforces a stricter contract. The CSV bank input has no `amount_eur`, so the official local scorer's fallback amount weights are sums of allocation amounts in their original currencies, not a true EUR-weighted cash metric.
