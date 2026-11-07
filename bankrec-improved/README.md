# Bank reconciliation: sample solver and full TRAIN evaluation

本项目改进 `bankrec-docs-and-masters/sample` 的匹配分数。保留官方 starter 和数据原样，在独立目录中实现新程序。没有调用收费 API，也没有提交 LIVE/FINAL。

## 结果

所有得分均由数据包自带的 `starter/bankrec_score.py` 计算，输出通过官方格式验证。

| 方法 | 开发段 6/2–6/20（5,346 笔） | 验证段 6/21–6/30（3,153 笔） | 全 sample（8,499 笔） |
|---|---:|---:|---:|
| 官方 starter | 11.46 | 11.00 | 11.28 |
| 主数据＋匹配规则（masters 模式） | 59.13 | 60.84 | 59.52 |
| 再加入批次、付款通知和 PDF 条款（full 模式） | 84.66 | 76.14 | 81.28 |

全样本提升 70.00 分。完整方案的 allocation precision 为 99.6884%，recall 为 72.6801%，allocation F1 为 84.0683%，transaction accuracy 为 87.3044%，exception macro-F1 为 65.2546%。不要把 precision 当成整个任务的准确率。

masters 模式相对 starter 同时改变了资料使用与匹配算法，因此不是“只增加 masters 文件”的严格单变量实验。full 与 masters 模式共用主匹配逻辑，full 额外读取辅助文件与发票 PDF。

## masters 探索结论

`masters_profile.json` 包含每张表、每个字段的非空数、空值数、不同值数量，以及低基数字段的分布。`profile_masters.py` 可以重现这些统计，不读取标签。

| 文件 | 行数 | 检查结果与使用方式 |
|---|---:|---|
| customers.csv | 55,672 | customer_id 唯一；name 只有 36,981 个不同值，不能将名称当唯一键。trade_name 有 3,275 条；IBAN 有 24,324 条且非空值唯一；SEPA mandate 有 26,081 条且非空值唯一。结合实体、历史发票名称、当前名称、别名、IBAN 与 mandate 定位客户。 |
| suppliers.csv | 12,831 | supplier_id 唯一；name 有 10,859 个不同值。IBAN 有 6,844 条，account_number 有 5,987 条，两者的非空值各自唯一。结合供应商身份解决发票号码冲突。 |
| entities.csv | 17 | 集团自身 17 个法人，分布在 15 个国家。用 entity 限定多数候选单据的归属范围。 |
| bank_accounts.csv | 47 | account_id 唯一；47 个账户属于 12 个银行代码，涉及 11 种账户币种。账户身份、币种、归属及批次账户用于关联和分类。opened 全空，不能依赖它判断历史有效性。 |
| payment_terms.csv | 13 | 4 个代码含提前付款折扣，分别涉及 1%、2%、3%，折扣天数 8、10、15 天；按开票日期、银行记账日期和规则中的 3 天宽限判断。 |
| categories.csv | 21 | 使用官方允许的类别；gl_account 只有 18 个不同值，因此不能用会计科目唯一反推类别。 |
| fx_rates.csv | 13,706 | 11 种非 EUR 币种、1,246 个日期，范围 2021-02-22 至 2025-12-31。units_per_eur 是 1 EUR 对应多少该币种；非交易日回退到之前最近日期，EUR 设为 1。 |

客户集团字段：506 条客户记录有 group_id，覆盖 178 个组；331 条有 parent_customer_id。程序通过 group_id 扩展付款方的集团成员候选。名称去重音、统一大小写和标点，并保留发票上的历史名称作为别名。

客户有 10,627 条 blocked_since 非空，供应商有 1,754 条；这不代表其历史发票不能被结清，程序没有粗暴地排除这些对象。masters 是快照，也不能用当前名称/账户否定历史付款。

## 匹配流程

1. 读取主数据、样本发票和流水，构建单据号码、订单号、客户/供应商、账号、授权号索引。
2. 识别手续费、税费、资金归集、内部转账等无单据类别。明确的银行错误冲正与相反金额原流水一起分类。
3. full 模式优先匹配直接扣款批次、银行卡结算、支票存款及供应商付款批次。批次先核对账户、金额、币种与日期，再定位明细单据。
4. full 模式解析付款通知的 CSV（逗号或分号）、XLSX、TXT、PDF，使用支付参考号、付款方、金额与日期关联；有明确扣减原因的行标为 SHORT_DISPUTE。
5. 对剩余流水，结合身份与号码线索匹配；在已识别付款方范围内做有界金额组合搜索，支持贷项抵扣。不会仅凭全局金额相等强行匹配。
6. 用付款条件判断折扣及逾期折扣，使用汇率判断 FX_DIFFERENCE；处理退回和重复付款，并维护本阶段内已知余额。
7. full 模式读取应收发票 PDF 中的替换单据、保证金和分期条款；服务月份还结合规则中“次月开票”的关系消歧。
8. 每笔流水输出分配结果或分类，另写 trace.jsonl 记录采用的匹配方法。

PDF 是文字型文件，使用 pypdf 提取文字，无 OCR、无 LLM。只对需要的 invoice 类型提取条款，不宣称已经支持所有 PDF 类型或所有语言布局。缓存以 PDF 内容 SHA-256 为键，默认在 /tmp 中，不包含在交付包。

## 运行

已验证环境为 Python 3.12.14；masters 模式仅依赖标准库。full 模式另需 requirements.txt 中的两个依赖。建议把本目录放在原始 bankrec-docs-and-masters 目录旁边。

```bash
python3 -m pip install -r bankrec-improved/requirements.txt

python3 bankrec-improved/profile_masters.py

python3 bankrec-improved/matcher.py --mode masters \
  --out bankrec-improved/sample_masters.csv.gz

python3 bankrec-improved/matcher.py --mode full \
  --out bankrec-improved/sample_improved.csv.gz \
  --trace bankrec-improved/full_trace.jsonl

python3 bankrec-improved/evaluate.py bankrec-improved/sample_improved.csv.gz --split all
python3 bankrec-improved/evaluate.py bankrec-improved/sample_improved.csv.gz --split holdout

python3 -m unittest discover -s bankrec-improved -p 'test_*.py'
```

可以通过 `--data /absolute/path/to/bankrec-docs-and-masters` 指定输入目录。`matcher.py` 的直接命令用于 sample；完整 TRAIN 使用下面的独立 runner。sample 和 TRAIN 预测文件都不能直接提交到 LIVE。

## 全量 TRAIN 复现

```bash
python3 -u bankrec-improved/train_runner.py --workers 2
python3 -u bankrec-improved/evaluate_train.py \
  bankrec-improved/train_results/train_predictions.csv.gz --by-group
```

默认读取同级 `train/`（full 版）与 `bankrec-docs-and-masters/masters/`。可以通过 `--train`、`--docs` 指定路径。首次运行创建按法人划分的临时输入及辅助文件软链接，西班牙付款中心 ES00 与 ES01、ES02、PT01 放在同一组；合计 14 组。组内按记账日期维护余额。分组内使用同一套名称匹配公式，词频权重由该组候选单据计算，不是全集团的词频权重。

`train_work/` 与分组预测是可复用检查点；输入、规则或模式变化后，请指定新的 `--work` 和 `--out` 路径，以免复用旧结果。`train_results/` 保存分组日志、运行统计、完整预测和评分。预测进程安装文件访问保护，禁止打开 golden_allocations；评分进程独立读取标签。

全 TRAIN 跨近四年，输出可能超过线上单阶段上传限制。`evaluate_train.py` 仅在本地放宽官方评分器的文件大小和行数限制；评分公式、金额容差、字段校验均使用原始官方代码。结果是训练语料上的离线评估，不是 LIVE 排行榜分数，也不是参数训练。

规模优化包括流式写出、按金额索引付款批次、名称前缀索引和基于现有阈值的候选剪枝。名称没有额外奖励时，分数达到 4.5 需要覆盖至少 75% 的名称权重，因此权重超过 25% 的词必须出现；利用这一必要条件可以安全过滤候选。保留原候选迭代顺序，避免改变同分候选的选择。各预测子进程固定 `PYTHONHASHSEED=0`。最终代码在完整 sample，以及固定种子的澳大利亚前 2,000 笔流水上通过了优化前后逐行相等检查。

全量数据发现 `IT01-VALD-EUR-2` 出现在历史流水及批次中但缺失于银行账户主数据；现在从流水中明确的 entity 补齐批次所需的法人映射，并检查归属冲突，不修改原始数据。

## 验证与边界

- 独立手工构造了金额解析及端到端会计案例，覆盖一笔多单、部分付款及尾款、折扣、退回、重复支付、未知付款方金额撞单；2 个测试通过。
- 最终两种模式均在 Python audit hook 禁止打开 golden_allocations 的条件下重新运行成功；只有单独的 evaluate.py 读取标准答案。
- 以 6 月 20 日为开发截止日期，最后冻结代码后才查看本轮后段验证指标。此前对话已浏览过全 sample 的汇总与部分样例，因此这是时间分段检查，不是完全盲测，也不是独立外部测试。
- 整个流程是阶段内离线对账：可以使用同阶段稍后到达的付款通知和冲正信息，不是只允许当时已知资料的严格在线回测。
- sample 的候选单据和覆盖范围与完整 TRAIN/LIVE 不同；这里只有三个法人，不能据此承诺 LIVE 也达到 81.28 分。
- sample 没有完整期初余额。本程序不能从本月以前的完整流水恢复所有旧账状态；某些尾款和重复付款仍会误判。
- 名称模糊匹配、金额组合搜索、有限的银行文本规则仍是启发式；全量运行成本记录在 train_results 的各组统计文件中。
- 11 份付款通知没有解析到可唯一定位的单据，程序会输出提示而不会伪造单据。
- 主数据中新 IBAN 通知、供应商保理通知、部分多语言条款等尚未全面纳入。原始银行格式解析不在这一版范围内。
- 仍明显不足的场景包括 N:M 付款（本样本准确率 0%）、confirming（0%）、部分付款（36.78%）和某些大批量争议付款。后段 allocation recall 只有 59.76%，是后续重点。
- comparison.json 和各分段 JSON 保留完整官方指标与场景准确率。amount_weighted_accuracy 在官方本地评分器缺少 amount_eur 时使用其 fallback 权重，不应解释成严格 EUR 加权结果。

## 文件

- matcher.py：预测程序；不读取标签。
- evaluate.py：调用官方评分器，可选 dev / holdout / all。
- profile_masters.py、masters_profile.json：主数据画像。
- test_matcher.py：独立会计测试。
- sample_baseline.csv.gz、sample_masters.csv.gz、sample_improved.csv.gz：三版样本预测。
- comparison.json、各分段 JSON：官方分数及分场景结果。
- masters_trace.jsonl、full_trace.jsonl：每笔流水的匹配路径。

数据源：本地已校验的 bankrec-docs-and-masters.zip；SHA-256 为 210b2404efd011af248a251db2bc0ee85a2ddaa1d56a7a0ca0b95ede18cc1071。规则以该包的 POLICIES.md / FORMAT.md / DATA_DICTIONARY.md 为依据。
