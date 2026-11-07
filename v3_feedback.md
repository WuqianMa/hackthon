# Submission Feedback Report: `submission_v3_live_001.csv`

**Phase:** LIVE  
**Date:** 07/11, 13:22  
**Status:** Scored  

---

## 1. Executive Summary & Overall Score

| Metric | Score / Value | Weight | Notes |
| :--- | :--- | :--- | :--- |
| **Final Scored Score** | **77.46 / 100** | — | Top score in history (+3.32 vs v4) |
| **Allocation F1** | **83.3%** | 50% | Precision: 92.4% \| Recall: 75.8% |
| **Transaction Accuracy** | **86.8%** | 30% | Strong baseline across major high-volume flows |
| **Exception Macro-F1** | **48.9%** | 20% | Primary bottleneck dragging overall score down |
| **Amount-Weighted Accuracy** | **78.5%** | — | Indicates larger value lines have lower accuracy |

### File & Line Coverage
- **Bank lines in phase:** 203,083
- **Rows in file:** 646,942
- **Missing bank lines:** 0 (100% coverage)

---

## 2. Submission History & Progression

| Submission Date & Time | Phase | File | Status | Score | Delta |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **07/11, 13:22** | **LIVE** | `submission_v3_live_001.csv` | **Scored** | **77.46** | **+3.32** |
| 07/11, 13:06 | LIVE | `submission_v4.csv` | Scored | 74.14 | +0.86 |
| 07/11, 11:59 | LIVE | `submission_v3.csv` | Scored | 73.28 | +1.17 |
| 07/11, 11:50 | LIVE | `submission_v2.csv` | Scored | 72.11 | -0.63 |
| 07/11, 10:49 | LIVE | `submission.csv` | Scored | 72.74 | Baseline |

---

## 3. Segment Performance Breakdown

### High-Volume Anchors ($\ge$ 5,000 Lines)
These categories represent the vast majority of lines and dictate foundational score stability.

| Segment | Estimated Lines | Accuracy | Status |
| :--- | :--- | :--- | :--- |
| `ar_ref_noise` | ~42,000 | 86.1% | Good (High-impact opportunity) |
| `ap_payment_multi` | ~25,000 | 98.3% | Strong |
| `ar_1to1` | ~19,000 | 98.5% | Strong |
| `ap_payment_single` | ~18,000 | 99.4% | Strong |
| `nonitem_bank_fees` | ~6,700 | 99.3% | Strong |
| `ar_1toN_text` | ~6,500 | 86.0% | Moderate |
| `ar_same_amount_fifo` | ~6,400 | 87.3% | Moderate |
| `ap_direct_debit` | ~5,600 | 89.5% | Good |
| `ar_short_discount` | ~5,500 | 90.6% | Good |

---

### Critical Bottlenecks & Low-Performing Segments (< 60% Accuracy)
Prioritizing fixes here will yield immediate improvements to the Exception Macro-F1 (20% weight) and Transaction Accuracy.

| Segment | Bank Lines | Accuracy | Issue Category |
| :--- | :--- | :--- | :--- |
| `ar_card_chargeback` | ~31 | **0.0%** | Complete failure / unhandled edge case |
| `ap_returned_transfer` | ~170 | **4.6%** | Return reversal logic failure |
| `ar_short_bank_charges` | ~150 | **8.8%** | Fee tolerance / thresholding error |
| `ar_cheque_returned` | ~72 | **9.7%** | Return matching logic failure |
| `ar_n_to_m` | ~1,800 | **17.9%** | Multi-allocation combinatorial search |
| `ap_duplicate_refund` | ~67 | **34.3%** | Duplicate refund exception handling |
| `nonitem_cash_pool` | ~1,600 | **37.2%** | Balance sweep / pool classification |
| `ar_1toN_credit_note` | ~3,300 | **40.4%** | Split netting / credit note allocation |
| `ar_advance_deduction` | ~260 | **40.7%** | Advance offset deduction |
| `ar_replaced_invoice` | ~260 | **44.4%** | Replaced invoice chaining |
| `ar_third_party_agency` | ~350 | **49.9%** | Third-party routing |
| `ar_same_amount_month` | ~4,400 | **50.8%** | Recurrent fixed-fee chronological tie-break |
| `ap_confirming` | ~850 | **51.3%** | Reverse factoring / confirming match |
| `ar_fx` | ~760 | **55.8%** | FX rate tolerance / exchange difference |
| `ar_dd_returned` | ~3,500 | **56.7%** | Direct debit return reversal |
| `ar_discount_late` | ~830 | **57.4%** | Post-term cash discount exception |

---

### Moderate Performers (60% – 85% Accuracy)

| Segment | Bank Lines | Accuracy |
| :--- | :--- | :--- |
| `ar_dd_represented_transfer` | ~980 | 61.9% |
| `ar_duplicate_payment` | ~590 | 64.1% |
| `ar_dd_batch` | ~1,600 | 65.1% |
| `ar_short_dispute` | ~1,100 | 70.8% |
| `ar_overpayment` | ~340 | 74.2% |
| `ap_factored` | ~1,400 | 74.6% |
| `ar_short_withholding` | ~1,400 | 77.4% |
| `ar_partial` | ~3,900 | 77.5% |
| `ar_instalment` | ~4,700 | 77.9% |
| `ap_duplicate_payment` | ~70 | 77.1% |
| `ar_retention` | ~1,000 | 79.6% |
| `customer_refund` | ~390 | 80.0% |
| `nonitem_insurance` | ~32 | 81.2% |
| `ar_1toN_remittance` | ~1,200 | 82.6% |

---

### Top Performers ($\ge$ 85% Accuracy)

| Segment | Bank Lines | Accuracy |
| :--- | :--- | :--- |
| `ar_third_party_parent` | ~190 | 88.8% |
| `ar_dispute_settlement` | ~1,300 | 89.3% |
| `ap_partial` | ~2,700 | 89.2% |
| `ar_third_party_confirming` | ~690 | 89.1% |
| `ar_new_iban` | ~290 | 91.4% |
| `ap_fx` | ~1,300 | 94.8% |
| `ar_credit_note_paid_out` | ~43 | 95.3% |
| `nonitem_intercompany` | ~380 | 96.5% |
| `ar_retention_release` | ~720 | 96.7% |
| `ap_supplier_refund` | ~2,600 | 97.4% |
| `ap_credit_note_netted` | ~2,700 | 98.2% |
| `ar_cheque_deposit` | ~2,000 | 98.7% |
| `ap_paid_by_holding` | ~4,800 | 98.8% |
| `nonitem_bank_fees_intl` | ~3,300 | 100.0% |
| `ar_card_settlement` | ~1,300 | 100.0% |
| `nonitem_bank_reversal` | ~330 | 100.0% |
| `customer_advance` | ~280 | 100.0% |
| `nonitem_fx_deal` | ~210 | 100.0% |
| `nonitem_card_expenses` | ~97 | 100.0% |
| `nonitem_interest_expense` | ~28 | 100.0% |
| `ar_1to1_remittance` | ~5 | 100.0% |

---

## 4. Key Takeaways & Action Plan

1. **Boost Exception Macro-F1 (Currently 48.9%, Weight 20%):**  
   Because Macro-F1 averages across classes without weighting by volume, low-volume failure categories (`ar_card_chargeback` at 0%, `ap_returned_transfer` at 4.6%, `ar_short_bank_charges` at 8.8%, `ar_cheque_returned` at 9.7%) heavily suppress this score. Hardcoding regex signatures or specific routing rules for these 4 classes will cause an immediate jump in your Exception Macro-F1.

2. **Address High-Volume Leaks for Allocation Recall (75.8%):**  
   - **`ar_ref_noise` (~42k lines, 86.1%):** Improving noise extraction and fuzzy reference cleaning here moves the needle significantly for overall Transaction Accuracy and Recall.  
   - **`ar_same_amount_month` (~4.4k lines, 50.8%):** Resolve period-matching logic (e.g., matching closest invoice due date or strict FIFO within period).  
   - **`ar_1toN_credit_note` (~3.3k lines, 40.4%):** Incorporate credit note sum netting before matching against remittance totals.

3. **Multi-Allocation Optimization (`ar_n_to_m` at 17.9%):**  
   Subset-sum / knapsack matching heuristics or relaxation of invoice-candidate filters are needed to capture multi-invoice, multi-payment relationships.