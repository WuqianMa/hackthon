"""Package the completed TRAIN run and its official scores for review."""
import hashlib
import json
import platform
import zipfile
from collections import Counter
from pathlib import Path


def main():
    here = Path(__file__).resolve().parent
    results = here / 'train_results'
    score = json.loads((results / 'full_train_score.json').read_text())
    if not score['ok']:
        raise RuntimeError('Full TRAIN did not pass official validation')
    grouped = json.loads((results / 'train_group_scores.json').read_text())
    stats = {p.name.split('.')[0]: json.loads(p.read_text()) for p in results.glob('*.csv.gz.stats.json')}
    inputs = json.loads((here / 'train_work/prepared.json').read_text())
    counts = {k: sum(v.values()) for k, v in inputs['tables'].items()}
    assert score['metrics']['txns_covered'] == score['metrics']['txns_total'] == counts['bank_transactions']
    assert sum(s['transactions'] for s in stats.values()) == counts['bank_transactions']
    assert all(s['label_access_guard'] for s in stats.values())
    methods = Counter()
    for s in stats.values():
        methods.update(s['methods'])
    summary = {
        'input_counts': counts,
        'python': platform.python_version(),
        'platform': platform.platform(),
        'prediction_access_to_labels': False,
        'methods': dict(methods.most_common()),
        'warning_count': sum(len(s['warnings']) for s in stats.values()),
        'successful_worker_seconds_sum': round(sum(s['total_seconds'] for s in stats.values()), 2),
        'max_single_worker_rss_native': max(s['max_rss_native'] for s in stats.values()),
        'source_code_sha256': {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in here.glob('*.py')},
        'score': score['score'],
    }
    (results / 'run_summary.json').write_text(json.dumps(summary, indent=2))
    sample = json.loads((here / 'improved_all.json').read_text())
    lines = [
        '# 全量 TRAIN 实验结果', '',
        f"最终得分：**{score['score']:.2f} / 100**。全部 {counts['bank_transactions']:,} 笔流水均有输出，且通过官方字段与分配格式校验。", '',
        '范围：2021-07-01 至 2025-06-30，17 个法人，14 个处理分组；使用 full 版 TRAIN。', '',
        f"候选单据：AR {counts['ar_invoices']:,}，AP {counts['ap_invoices']:,}，贷项 {counts['credit_notes']:,}。", '',
        '## 与 sample 对照', '',
        '| 指标 | sample | 全量 TRAIN |', '|---|---:|---:|',
        f"| 总分 / 100 | {sample['score']:.2f} | {score['score']:.2f} |",
    ]
    for key, title in [('precision','分配 Precision'),('recall','分配 Recall'),('allocation_f1','分配 F1'),
                       ('txn_accuracy','整笔流水完全正确率'),('exception_macro_f1','异常类型 Macro-F1')]:
        lines.append(f"| {title} | {100*sample['metrics'][key]:.2f}% | {100*score['metrics'][key]:.2f}% |")
    lines += ['', '两者的数据范围、历史余额和候选单据集合不同；这个对照不等于控制其他条件不变的实验。TRAIN 包含 sample 对应时段，不是独立测试集。', '',
              '## 分组得分', '', '| 分组 | 流水数 | 总分 / 100 | 整笔准确率 |', '|---|---:|---:|---:|']
    for name, r in sorted(grouped.items(), key=lambda kv: kv[1]['score']):
        lines.append(f"| {name} | {r['metrics']['txns_total']:,} | {r['score']:.2f} | {100*r['metrics']['txn_accuracy']:.2f}% |")
    lines += ['', 'ES_PAYMENT_FACTORY 包含 ES00、ES01、ES02、PT01。总分直接在全量输出上计算，不是分组分数的平均值。', '',
              '## 场景准确率', '', '| 场景 | 流水数 | 整笔准确率 |', '|---|---:|---:|']
    for name, r in sorted(score['segments'].items(), key=lambda kv: (-kv[1]['n'], kv[0])):
        lines.append(f"| {name} | {r['n']:,} | {100*r['accuracy']:.2f}% |")
    lines += ['', '## 实验与复现说明', '',
              '- 直接运行既有规则，没有训练神经网络，也没有用 TRAIN 标准答案调参。每个预测子进程均禁止打开 golden_allocations；只有独立评估脚本读取答案。',
              '- 全量运行增加了流式输出、金额索引及数学上等价的名称候选过滤；完整 sample 和澳大利亚前 2,000 笔固定种子实验通过逐行一致性检查。',
              '- 修复了 IT01-VALD-EUR-2 不在账户主数据快照中的兼容问题：从历史流水明确的 entity 补齐批次归属映射。',
              '- 各组词频权重由该组的候选单据计算；子进程固定 PYTHONHASHSEED=0。',
              '- 使用原始官方 bankrec_score.py。仅本地放宽文件体积和行数限制，以评分跨四年的 TRAIN 输出；金额容差与评分公式未修改。',
              '- 这是离线对账，允许读取同阶段稍后到达的辅助文档；不能解释成只使用当时已知信息的在线回测。',
              f"- 预测共有 {score['metrics']['rows']:,} 行；辅助文档解析警告 {summary['warning_count']:,} 条。", '',
              '```bash', 'python3 -u bankrec-improved/train_runner.py --workers 2',
              'python3 -u bankrec-improved/evaluate_train.py bankrec-improved/train_results/train_predictions.csv.gz --by-group',
              '```', '',
              '代码、逐组运行统计、完整预测及官方评分 JSON 均附于交付包。原始 TRAIN 与 masters 数据不重复打包。']
    report = here / 'TRAIN_REPORT.md'
    report.write_text('\n'.join(lines) + '\n')
    package = Path('/tmp/bankrec_train_evaluation.zip')
    with zipfile.ZipFile(package, 'w', compression=zipfile.ZIP_DEFLATED, compresslevel=6) as z:
        files = list(here.glob('*.py')) + list(here.glob('*.md')) + [here / 'requirements.txt']
        files += [p for p in here.glob('*.json') if p.name != 'full_dev.json']
        files += list(here.glob('*.jsonl')) + list(here.glob('sample_*.csv.gz'))
        files += list(results.glob('*.json')) + list(results.glob('*.log'))
        for p in files:
            z.write(p, 'bankrec-improved/' + str(p.relative_to(here)))
        p = results / 'train_predictions.csv.gz'
        z.write(p, 'bankrec-improved/train_results/' + p.name, compress_type=zipfile.ZIP_STORED)
    print(json.dumps({'package': str(package), 'size_mib': package.stat().st_size/1024**2,
                      'score': score['score'], 'metrics': score['metrics']}, indent=2))


if __name__ == '__main__':
    main()
