# V6 LIVE website feedback — user-provided report

Source: website results pasted by the user, received 7 November 2026. No website timestamp was included. Values below are transcribed from that report, not a new evaluation run. Segment counts are the website's approximate values.

- Phase: **LIVE**
- File: **v6-submission.csv**
- Status: **Scored**
- Score: **81.39 / 100**
- Allocation F1, weight 50%: **85.4%**
- Precision: **94.9%**
- Recall: **77.7%**
- Transaction accuracy, weight 30%: **88.7%**
- Exception macro-F1, weight 20%: **60.3%**
- Amount-weighted accuracy: **83.7%**
- Bank lines in phase: **203,083**
- Rows in file: **643,231**
- Bank lines missing: **0**

| Segment | Bank lines | Accuracy |
|---|---:|---:|
| ar_ref_noise | ~42,000 | 86.1% |
| ap_payment_multi | ~25,000 | 98.3% |
| ar_1to1 | ~19,000 | 98.8% |
| ap_payment_single | ~18,000 | 99.5% |
| nonitem_bank_fees | ~6,700 | 99.3% |
| ar_1toN_text | ~6,500 | 87.5% |
| ar_same_amount_fifo | ~6,400 | 85.5% |
| ap_direct_debit | ~5,600 | 89.5% |
| ar_short_discount | ~5,500 | 90.4% |
| ap_paid_by_holding | ~4,800 | 98.8% |
| ar_instalment | ~4,700 | 76.1% |
| ar_same_amount_month | ~4,400 | 89.2% |
| ar_partial | ~3,900 | 79.1% |
| ar_dd_returned | ~3,500 | 65.5% |
| ar_1toN_credit_note | ~3,300 | 47.7% |
| nonitem_bank_fees_intl | ~3,300 | 100.0% |
| ap_credit_note_netted | ~2,700 | 98.2% |
| ap_partial | ~2,700 | 89.2% |
| ap_supplier_refund | ~2,600 | 97.4% |
| ar_cheque_deposit | ~2,000 | 98.7% |
| ar_n_to_m | ~1,800 | 24.1% |
| ar_dd_batch | ~1,600 | 65.1% |
| nonitem_cash_pool | ~1,600 | 100.0% |
| ap_factored | ~1,400 | 74.6% |
| ar_short_withholding | ~1,400 | 77.2% |
| ap_fx | ~1,300 | 94.8% |
| ar_card_settlement | ~1,300 | 100.0% |
| ar_dispute_settlement | ~1,300 | 92.1% |
| ar_1toN_remittance | ~1,200 | 82.6% |
| ar_short_dispute | ~1,100 | 70.9% |
| ar_retention | ~1,000 | 64.4% |
| ar_dd_represented_transfer | ~980 | 66.3% |
| ap_confirming | ~850 | 51.3% |
| ar_discount_late | ~830 | 57.1% |
| ar_fx | ~760 | 56.0% |
| ar_retention_release | ~720 | 96.4% |
| ar_third_party_confirming | ~690 | 89.1% |
| ar_duplicate_payment | ~590 | 62.8% |
| customer_refund | ~390 | 80.0% |
| nonitem_intercompany | ~380 | 96.5% |
| ar_third_party_agency | ~350 | 50.1% |
| ar_overpayment | ~340 | 73.6% |
| nonitem_bank_reversal | ~330 | 100.0% |
| ar_new_iban | ~290 | 91.0% |
| customer_advance | ~280 | 98.6% |
| ar_advance_deduction | ~260 | 70.0% |
| ar_replaced_invoice | ~260 | 78.2% |
| nonitem_fx_deal | ~210 | 100.0% |
| ar_third_party_parent | ~190 | 88.8% |
| ap_returned_transfer | ~170 | 66.7% |
| ar_short_bank_charges | ~150 | 76.9% |
| nonitem_card_expenses | ~97 | 100.0% |
| ar_cheque_returned | ~72 | 77.8% |
| ap_duplicate_payment | ~70 | 77.1% |
| ap_duplicate_refund | ~67 | 88.1% |
| ar_credit_note_paid_out | ~43 | 95.3% |
| nonitem_insurance | ~32 | 81.2% |
| ar_card_chargeback | ~31 | 61.3% |
| nonitem_interest_expense | ~28 | 100.0% |
| ar_1to1_remittance | ~5 | 100.0% |

No row-level LIVE labels, per-exception confusion matrix or exact per-segment counts were provided. These results belong to the LIVE website population. The separate cached v6 development score was 81.41 on 7,500 labeled TRAIN bank lines.
