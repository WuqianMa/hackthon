# 全量 TRAIN 实验结果

最终得分：**72.48 / 100**。全部 1,489,931 笔流水均有输出，且通过官方字段与分配格式校验。

范围：2021-07-01 至 2025-06-30，17 个法人，14 个处理分组；使用 full 版 TRAIN。

候选单据：AR 3,963,735，AP 1,530,203，贷项 150,215。

## 与 sample 对照

| 指标 | sample | 全量 TRAIN |
|---|---:|---:|
| 总分 / 100 | 81.28 | 72.48 |
| 分配 Precision | 99.69% | 95.49% |
| 分配 Recall | 72.68% | 65.15% |
| 分配 F1 | 84.07% | 77.45% |
| 整笔流水完全正确率 | 87.30% | 81.57% |
| 异常类型 Macro-F1 | 65.25% | 46.43% |

两者的数据范围、历史余额和候选单据集合不同；这个对照不等于控制其他条件不变的实验。TRAIN 包含 sample 对应时段，不是独立测试集。

## 分组得分

| 分组 | 流水数 | 总分 / 100 | 整笔准确率 |
|---|---:|---:|---:|
| ES_PAYMENT_FACTORY | 320,718 | 63.25 | 68.29% |
| US01 | 452,690 | 68.96 | 80.73% |
| BR01 | 48,591 | 73.85 | 89.11% |
| MX01 | 46,265 | 77.09 | 77.40% |
| CH01 | 28,300 | 78.64 | 88.73% |
| MA01 | 28,179 | 79.26 | 82.96% |
| UK01 | 36,123 | 79.40 | 77.85% |
| AU01 | 121,560 | 79.55 | 88.26% |
| IT01 | 57,840 | 80.73 | 88.23% |
| CN01 | 80,252 | 81.06 | 92.94% |
| DE01 | 66,998 | 85.27 | 89.87% |
| FR01 | 120,442 | 86.73 | 89.38% |
| NL01 | 45,339 | 86.95 | 89.16% |
| PL01 | 36,634 | 89.76 | 92.74% |

ES_PAYMENT_FACTORY 包含 ES00、ES01、ES02、PT01。总分直接在全量输出上计算，不是分组分数的平均值。

## 场景准确率

| 场景 | 流水数 | 整笔准确率 |
|---|---:|---:|
| ar_ref_noise | 312,717 | 81.27% |
| ap_payment_multi | 174,406 | 97.65% |
| ar_1to1 | 141,038 | 99.20% |
| ap_payment_single | 139,376 | 99.18% |
| ar_same_amount_fifo | 49,049 | 70.86% |
| nonitem_bank_fees | 46,984 | 100.00% |
| ar_1toN_text | 46,644 | 76.98% |
| ar_short_discount | 42,704 | 81.70% |
| ap_direct_debit | 41,335 | 87.30% |
| ar_same_amount_month | 33,429 | 90.05% |
| ap_paid_by_holding | 33,363 | 0.00% |
| ar_instalment | 33,008 | 83.30% |
| ar_partial | 27,750 | 59.79% |
| ar_dd_returned | 26,397 | 49.09% |
| unidentified | 24,299 | 94.79% |
| ar_1toN_credit_note | 23,466 | 49.31% |
| nonitem_bank_fees_intl | 23,168 | 100.00% |
| ap_credit_note_netted | 18,475 | 88.38% |
| ap_partial | 18,131 | 80.25% |
| ap_supplier_refund | 17,795 | 79.13% |
| ar_cheque_deposit | 15,231 | 65.98% |
| ar_n_to_m | 13,904 | 0.00% |
| nonitem_cash_pool | 12,576 | 25.38% |
| ar_dd_batch | 12,505 | 96.28% |
| ap_factored | 10,934 | 85.10% |
| unidentified_lookalike | 10,354 | 94.02% |
| ar_short_withholding | 10,148 | 77.62% |
| ar_card_settlement | 10,051 | 99.98% |
| ar_1toN_remittance | 9,423 | 53.62% |
| ap_fx | 8,604 | 78.39% |
| ar_dispute_settlement | 7,784 | 69.08% |
| ar_dd_represented_transfer | 7,568 | 47.30% |
| ar_short_dispute | 7,553 | 52.15% |
| ar_retention | 6,643 | 85.37% |
| ap_confirming | 6,387 | 0.00% |
| ar_fx | 6,146 | 38.71% |
| ar_discount_late | 5,837 | 53.55% |
| ar_third_party_confirming | 4,998 | 84.87% |
| ar_duplicate_payment | 4,436 | 81.92% |
| ar_retention_release | 4,145 | 84.54% |
| nonitem_payroll | 3,897 | 19.94% |
| nonitem_intercompany | 3,187 | 49.89% |
| nonitem_leasing | 2,832 | 76.27% |
| ar_overpayment | 2,817 | 35.85% |
| nonitem_bank_reversal | 2,664 | 98.91% |
| ar_third_party_agency | 2,636 | 59.03% |
| customer_refund | 2,611 | 79.36% |
| ar_replaced_invoice | 2,024 | 57.41% |
| customer_advance | 2,008 | 100.00% |
| ar_advance_deduction | 2,003 | 29.41% |
| nonitem_internal_transfer | 1,936 | 100.00% |
| nonitem_fx_deal | 1,551 | 63.89% |
| ar_third_party_parent | 1,298 | 74.19% |
| ap_returned_transfer | 1,192 | 32.30% |
| ar_new_iban | 1,122 | 84.76% |
| ar_short_bank_charges | 1,121 | 50.94% |
| nonitem_tax_payment | 957 | 54.44% |
| nonitem_loan_repayment | 832 | 60.58% |
| nonitem_social_security | 816 | 93.01% |
| nonitem_card_expenses | 718 | 100.00% |
| ar_cheque_returned | 538 | 0.00% |
| ap_duplicate_payment | 491 | 65.38% |
| ap_duplicate_refund | 483 | 38.30% |
| ar_credit_note_paid_out | 325 | 95.08% |
| nonitem_interest_income | 320 | 0.00% |
| ar_card_chargeback | 289 | 0.00% |
| nonitem_insurance | 220 | 0.00% |
| nonitem_interest_expense | 181 | 0.00% |
| ar_1to1_remittance | 60 | 98.33% |
| nonitem_loan_drawdown | 32 | 0.00% |
| ap_payment_run_aggregated | 5 | 0.00% |
| nonitem_tax_refund | 4 | 0.00% |

## 实验与复现说明

- 直接运行既有规则，没有训练神经网络，也没有用 TRAIN 标准答案调参。每个预测子进程均禁止打开 golden_allocations；只有独立评估脚本读取答案。
- 全量运行增加了流式输出、金额索引及数学上等价的名称候选过滤；完整 sample 和澳大利亚前 2,000 笔固定种子实验通过逐行一致性检查。
- 修复了 IT01-VALD-EUR-2 不在账户主数据快照中的兼容问题：从历史流水明确的 entity 补齐批次归属映射。
- 各组词频权重由该组的候选单据计算；子进程固定 PYTHONHASHSEED=0。
- 使用原始官方 bankrec_score.py。仅本地放宽文件体积和行数限制，以评分跨四年的 TRAIN 输出；金额容差与评分公式未修改。
- 这是离线对账，允许读取同阶段稍后到达的辅助文档；不能解释成只使用当时已知信息的在线回测。
- 预测共有 3,900,195 行；辅助文档解析警告 0 条。

```bash
python3 -u bankrec-improved/train_runner.py --workers 2
python3 -u bankrec-improved/evaluate_train.py bankrec-improved/train_results/train_predictions.csv.gz --by-group
```

代码、逐组运行统计及官方评分 JSON 随报告保存在仓库。完整预测保存在本地 train_results/train_predictions.csv.gz，未纳入 Git。原始 TRAIN 与 masters 数据也不纳入 Git。
