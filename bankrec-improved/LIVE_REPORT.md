# LIVE 提交记录与分析

## 提交历程

| 版本 | 总分 | F1 | Precision | Recall | 准确率 | 异常Macro-F1 | 主要变化 |
|---|---:|---:|---:|---:|---:|---:|---|
| v1 | 72.74 | 73.1% | 95.1% | 59.4% | 85.2% | 46.9% | 基线规则 |
| v2 | 72.11 | 72.2% | 95.2% | 58.2% | 85.2% | 46.6% | 回退：跨实体搜索范围过大 |
| v3 | 73.28 | 74.0% | 95.3% | 60.4% | 85.6% | 47.7% | 修复v2回退 + DD交叉引用 + 多贷项 |
| v4 | 74.14 | 75.5% | 95.5% | 62.1% | 86.3% | 49.3% | 付款工厂 + 确认付款 + 分类模式 |
| v5 | 74.43 | 76.4% | 95.6% | 63.6% | 86.9% | 51.0% | 三层架构重构 |

Sample 对照: v5 在 sample 上得分 **81.47**（v1 基线 81.28）。

## v5 三层架构

### 设计

```
Layer 1 (强证据 → 直接输出):
  for each transaction (时间顺序):
    1. category() 门卫 → 非单据类别直接输出
    2. batch_match() → DD批次/卡结算/支票/付款指令
    3. advice_match() → 汇款通知
    4. confirming_match() → 确认付款子集
    5. generic_match() returns only → DD退回

Layer 2 (候选生成):
  for each unresolved transaction:
    generate_candidates() → list of (rows, score, method)
    策略:
      - 完整引用匹配 (score=80)
      - 引用+贷项净额 (score=75)
      - 身份+金额 (score=60+)
      - 折扣/预扣/FX/银行费用 (score=50-55)
      - 分期/保留金 (score=52)
      - 客户子集求和 (score=45+)
      - 客户净额子集 (score=38-42)
      - 引用部分付款 (score=35)
      - 超额付款 (score=35)
      - 重复付款 (score=25)

Layer 3 (冲突解决):
  按交易时间顺序处理 (保持 FIFO 余额消耗语义)
  对每笔交易选最高分且余额可用的候选
  未匹配 → UNIDENTIFIED
```

### 关键设计决策

1. **Category 保持门卫** — 尝试过将 category 降为低优先级候选（score=15），导致异常 Macro-F1 从 65.25% 降至 56.85%。原因：高分但错误的发票匹配覆盖了正确的分类。已回退。

2. **Layer 3 按时间顺序** — 尝试过全局按分数排序贪心分配，导致 FIFO 余额消耗顺序被打破，PARTIAL/DUPLICATE 等依赖余额状态的异常判断大量出错。已修正为按交易时间顺序处理，对每笔交易选最高分候选。

3. **Returns 留在 Layer 1** — DD 退回依赖批次交叉引用数据，是强证据，不需要多候选评分。

## 当前瓶颈分析

### 0 分或极低分场景 (总计约 3,000 笔)

| 场景 | 笔数 | 准确率 | 根本原因 |
|---|---:|---:|---|
| ar_n_to_m | ~1,800 | 8.5% | N-to-M 匹配未实现 |
| ar_cheque_returned | ~72 | 0.0% | 退回支票无专门规则 |
| ar_card_chargeback | ~31 | 12.9% | 信用卡拒付无专门规则 |
| ap_returned_transfer | ~170 | 24.7% | AP退回转账逻辑不足 |
| ar_advance_deduction | ~260 | 21.3% | 预付款扣减需PDF解析 |
| ap_confirming | ~850 | 22.6% | 确认付款子集匹配有限 |

### 中等分数但改进空间大的场景 (总计约 8,000 笔)

| 场景 | 笔数 | 准确率 | 改进方向 |
|---|---:|---:|---|
| ar_short_dispute | ~1,100 | 43.3% | 需解析汇款通知中的争议原因 |
| nonitem_intercompany | ~380 | 48.5% | 需要更好的公司间转账识别 |
| ar_1toN_remittance | ~1,200 | 54.4% | 汇款通知解析成功率不足 |
| ar_1toN_credit_note | ~3,300 | 53.1% | 多贷项组合搜索空间有限 |
| ar_discount_late | ~830 | 52.5% | 过期折扣判断逻辑需优化 |
| ar_overpayment | ~340 | 39.3% | 超额付款检测条件过严 |
| ap_paid_by_holding | ~4,800 | 39.3% | 控股公司付款需更深入的集团关系 |

### 高分场景 (已接近上限)

| 场景 | 笔数 | 准确率 |
|---|---:|---:|
| nonitem_bank_fees | ~6,700 | 100.0% |
| nonitem_bank_fees_intl | ~3,300 | 100.0% |
| nonitem_cash_pool | ~1,600 | 100.0% |
| ar_card_settlement | ~1,300 | 100.0% |
| nonitem_bank_reversal | ~330 | 100.0% |
| customer_advance | ~280 | 100.0% |
| nonitem_insurance | ~32 | 100.0% |
| ar_1to1 | ~19,000 | 99.2% |
| ap_payment_single | ~18,000 | 98.7% |
| ap_payment_multi | ~25,000 | 97.0% |

## 局部最优分析

当前得分 74.43 可能已接近纯规则方法的局部最优。主要受限于：

1. **N-to-M 匹配**（~1,800 笔 × 0% → 潜在 +1-2 分）— 需要图匹配或整数规划
2. **汇款通知覆盖率**（~1,200 笔 54%）— 需更鲁棒的 PDF/文本解析
3. **集团关系深度**（ap_paid_by_holding ~4,800 笔 39%）— 需递归解析集团树
4. **争议/部分付款**（~5,000 笔 40-68%）— 需更细粒度的金额推理
5. **Recall 天花板**（63.6%）— 大量交易因缺乏可用引用/身份信息而无法匹配

进一步突破可能需要：
- 实现 N-to-M 匹配（图模型）
- 引入 LLM 辅助的自然语言理解（银行文本、汇款通知）
- 使用 TRAIN 标注数据学习规则权重或边界条件
- 端到端的候选排序模型替代硬编码分数

## 复现

```bash
python3 -u bankrec-improved/train_runner.py \
  --phase live --data ../live \
  --docs ../bankrec-docs-and-masters \
  --history ../train \
  --work bankrec-improved/live_work \
  --out bankrec-improved/live_results \
  --workers 3
```
