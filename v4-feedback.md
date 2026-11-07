# Submission Feedback Report: `submission_v4`

**Phase:** LIVE  
**Score:** **79.05 / 100** (+1.59 vs previous 77.46)  
**Status:** Scored  

---

## 1. Executive Summary & Key Metrics Comparison

| Metric | Current Run (v4) | Previous Run (v3_live_001) | Delta | Weight | Notes |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **Overall Score** | **79.05 / 100** | **77.46 / 100** | **+1.59** | — | **New High Score** |
| **Allocation F1** | **85.0%** | 83.3% | **+1.7%** | 50% | Strong gain; both precision and recall rose |
| — *Precision* | *94.5%* | *92.4%* | *+2.1%* | — | Fewer false-positive allocations |
| — *Recall* | *77.3%* | *75.8%* | *+1.5%* | — | Found more valid matches |
| **Transaction Accuracy** | **86.8%** | 86.8% | 0.0% | 30% | Flat line-level accuracy |
| **Exception Macro-F1** | **52.4%** | 48.9% | **+3.5%** | 20% | Meaningful improvement in exception handling |
| **Amount-Weighted Accuracy** | **78.5%** | 78.5% | 0.0% | — | Volume/value weighting remained stable |

### File & Volume Stats
* **Bank lines in phase:** 203,083
* **Rows in file:** 642,703 (*-4,239 rows vs v3_live_001, reflecting tighter allocation precision*)
* **Bank lines missing:** 0 (100% coverage preserved)

---

## 2. Key Movers: What Changed Since Last Run?

### 🟢 Biggest Improvements
* **`ar_dd_returned` (\~3,500 lines):** **56.7% $\rightarrow$ 65.5% (+8.8%)** — Substantial bounce in direct debit return handling.
* **`ar_dd_represented_transfer` (\~980 lines):** **61.9% $\rightarrow$ 66.3% (+4.4%)**
* **`ar_dispute_settlement` (\~1,300 lines):** **89.3% $\rightarrow$ 92.1% (+2.8%)**
* **`ar_1toN_text` (\~6,500 lines):** **86.0% $\rightarrow$ 87.5% (+1.5%)**
* **`ar_partial` (\~3,900 lines):** **77.5% $\rightarrow$ 79.0% (+1.5%)**
* **`ap_payment_multi` (\~25,000 lines):** **98.3% $\rightarrow$ 98.8% (+0.5%)**

### 🔴 Regressions to Investigate
* **`ar_retention` (\~1,000 lines):** **79.6% $\rightarrow$ 62.6% (-17.0%)** — *Major drop; review retention/warranty withholding rules.*
* **`ap_partial` (\~2,700 lines):** **89.2% $\rightarrow$ 75.7% (-13.5%)** — *Severe regression on AP partial allocations.*
* **`ar_discount_late` (\~830 lines):** **57.4% $\rightarrow$ 49.0% (-8.4%)**
* **`ar_instalment` (\~4,700 lines):** **77.9% $\rightarrow$ 75.4% (-2.5%)**
* **`ar_same_amount_month` (\~4,400 lines):** **50.8% $\rightarrow$ 48.9% (-1.9%)**
* **`ar_same_amount_fifo` (\~6,400 lines):** **87.3% $\rightarrow$ 85.5% (-1.8%)**
* **`ar_duplicate_payment` (\~590 lines):** **64.1% $\rightarrow$ 62.3% (-1.8%)**
* **`ar_advance_deduction` (\~260 lines):** **40.7% $\rightarrow$ 38.8% (-1.9%)**
* **`ar_n_to_m` (\~1,800 lines):** **17.9% $\rightarrow$ 16.3% (-1.6%)**

---

## 3. Full Segment Performance Breakdown

### High-Volume Segments ($\ge$ 5,000 Lines)

| Segment | Bank Lines | Accuracy (v4) | Prior (v3) | Status / Movement |
| :--- | :--- | :--- | :--- | :--- |
| `ar_ref_noise` | \~42,000 | 86.1% | 86.1% | Stable |
| `ap_payment_multi` | \~25,000 | 98.8% | 98.3% | 🟢 Improved (+0.5%) |
| `ar_1to1` | \~19,000 | 98.8% | 98.5% | 🟢 Improved (+0.3%) |
| `ap_payment_single` | \~18,000 | 99.6% | 99.4% | 🟢 Near ceiling |
| `nonitem_bank_fees` | \~6,700 | 99.3% | 99.3% | Stable |
| `ar_1toN_text` | \~6,500 | 87.5% | 86.0% | 🟢 Improved (+1.5%) |
| `ar_same_amount_fifo` | \~6,400 | 85.5% | 87.3% | 🔴 Regressed (-1.8%) |
| `ap_direct_debit` | \~5,600 | 89.5% | 89.5% | Stable |
| `ar_short_discount` | \~5,500 | 90.6% | 90.6% | Stable |

### Low Performers & Hard Exceptions (< 60% Accuracy)

| Segment | Bank Lines | Accuracy (v4) | Prior (v3) | Primary Bottleneck |
| :--- | :--- | :--- | :--- | :--- |
| `ar_card_chargeback` | \~31 | **0.0%** | 0.0% | Unhandled exception |
| `ap_returned_transfer` | \~170 | **4.6%** | 4.6% | Return debit offset failure |
| `ar_short_bank_charges` | \~150 | **8.8%** | 8.8% | Fee threshold parsing |
| `ar_cheque_returned` | \~72 | **9.7%** | 9.7% | Unmatched bounce record |
| `ar_n_to_m` | \~1,800 | **16.3%** | 17.9% | Complex subset matching |
| `ap_duplicate_refund` | \~67 | **34.3%** | 34.3% | Duplicate handling logic |
| `nonitem_cash_pool` | \~1,600 | **37.2%** | 37.2% | Sweeping transaction routing |
| `ar_advance_deduction` | \~260 | **38.8%** | 40.7% | Prepayment offset logic |
| `ar_1toN_credit_note` | \~3,300 | **40.6%** | 40.4% | CN netting calculation |
| `ar_replaced_invoice` | \~260 | **44.0%** | 44.4% | Re-issue link missing |
| `ar_same_amount_month` | \~4,400 | **48.9%** | 50.8% | Monthly periodicity matching |
| `ar_discount_late` | \~830 | **49.0%** | 57.4% | Grace period tolerance |
| `ar_third_party_agency` | \~350 | **49.6%** | 49.9% | Agency collection routing |
| `ap_confirming` | \~850 | **51.3%** | 51.3% | Confirming platform match |
| `ar_fx` | \~760 | **55.9%** | 55.8% | FX variance threshold |

### Moderate Performers (60% – 85% Accuracy)

| Segment | Bank Lines | Accuracy (v4) | Prior (v3) | Movement |
| :--- | :--- | :--- | :--- | :--- |
| `ar_duplicate_payment` | \~590 | 62.3% | 64.1% | 🔴 -1.8% |
| `ar_retention` | \~1,000 | 62.6% | 79.6% | 🔴 -17.0% |
| `ar_dd_batch` | \~1,600 | 65.1% | 65.1% | Flat |
| `ar_dd_returned` | \~3,500 | 65.5% | 56.7% | 🟢 +8.8% |
| `ar_dd_represented_transfer` | \~980 | 66.3% | 61.9% | 🟢 +4.4% |
| `ar_short_dispute` | \~1,100 | 70.9% | 70.8% | Flat |
| `ar_overpayment` | \~340 | 73.6% | 74.2% | -0.6% |
| `ap_factored` | \~1,400 | 74.7% | 74.6% | Flat |
| `ar_instalment` | \~4,700 | 75.4% | 77.9% | 🔴 -2.5% |
| `ap_partial` | \~2,700 | 75.7% | 89.2% | 🔴 -13.5% |
| `ap_duplicate_payment` | \~70 | 77.1% | 77.1% | Flat |
| `ar_short_withholding` | \~1,400 | 77.2% | 77.4% | Flat |
| `ar_partial` | \~3,900 | 79.0% | 77.5% | 🟢 +1.5% |
| `customer_refund` | \~390 | 80.0% | 80.0% | Flat |
| `nonitem_insurance` | \~32 | 81.2% | 81.2% | Flat |
| `ar_1toN_remittance` | \~1,200 | 82.6% | 82.6% | Flat |

### High Performers ($\ge$ 85% Accuracy)

| Segment | Bank Lines | Accuracy (v4) | Prior (v3) | Movement |
| :--- | :--- | :--- | :--- | :--- |
| `ar_third_party_parent` | \~190 | 88.8% | 88.8% | Flat |
| `ar_third_party_confirming` | \~690 | 89.1% | 89.1% | Flat |
| `ar_new_iban` | \~290 | 91.0% | 91.4% | -0.4% |
| `ar_dispute_settlement` | \~1,300 | 92.1% | 89.3% | 🟢 +2.8% |
| `ap_fx` | \~1,300 | 94.8% | 94.8% | Flat |
| `ar_credit_note_paid_out` | \~43 | 95.3% | 95.3% | Flat |
| `ar_retention_release` | \~720 | 96.4% | 96.7% | -0.3% |
| `nonitem_intercompany` | \~380 | 96.5% | 96.5% | Flat |
| `ap_supplier_refund` | \~2,600 | 97.4% | 97.4% | Flat |
| `customer_advance` | \~280 | 98.6% | 100.0% | -1.4% |
| `ap_credit_note_netted` | \~2,700 | 98.6% | 98.2% | 🟢 +0.4% |
| `ar_cheque_deposit` | \~2,000 | 98.7% | 98.7% | Flat |
| `ap_paid_by_holding` | \~4,800 | 99.2% | 98.8% | 🟢 +0.4% |
| `nonitem_bank_fees_intl` | \~3,300 | 100.0% | 100.0% | Flat |
| `ar_card_settlement` | \~1,300 | 100.0% | 100.0% | Flat |
| `nonitem_bank_reversal` | \~330 | 100.0% | 100.0% | Flat |
| `nonitem_fx_deal` | \~210 | 100.0% | 100.0% | Flat |
| `nonitem_card_expenses` | \~97 | 100.0% | 100.0% | Flat |
| `nonitem_interest_expense` | \~28 | 100.0% | 100.0% | Flat |
| `ar_1to1_remittance` | \~5 | 100.0% | 100.0% | Flat |

---

## 4. Next Step Strategy to Break 80+

1. **Revert / Repair `ap_partial` (-13.5%) and `ar_retention` (-17.0%):**
   * These two regressions lost roughly ~0.5 to 0.7 total score points. Recovering them alone gets the score near **79.6–79.8**.
2. **Unlock the Micro-Exception Classes for Macro-F1 (Currently 52.4%):**
   * Macro-F1 treats `ar_card_chargeback` (31 lines, 0.0%) and `ap_returned_transfer` (170 lines, 4.6%) with the exact same weight as 42,000-line segments.
   * Adding targeted classification rules for the bottom 4 zero/single-digit classes will push Exception Macro-F1 above 60%, adding ~1.5 net weighted points.