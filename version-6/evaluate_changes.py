"""Audit cached development changes with the organizer's scorer; no inference."""
from collections import defaultdict
import json
import importlib.util
from pathlib import Path

ROOT=Path(__file__).resolve().parent.parent
spec=importlib.util.spec_from_file_location('v6_pipeline',Path(__file__).parent/'run.py')
pipeline=importlib.util.module_from_spec(spec);spec.loader.exec_module(pipeline)
scoring= pipeline.scoring;WORK=pipeline.WORK;RESULTS=pipeline.RESULTS
from bankrec.io import write_json


def main():
    m,module,g=scoring();groups=defaultdict(list);regressions=[]
    for r in map(json.loads,(WORK/'test_audit.jsonl').open()):
        tid=r['bank_txn_id']
        before=m.score(module,g,{tid:r['before']})['metrics']['txn_accuracy']==1
        after=m.score(module,g,{tid:r['after']})['metrics']['txn_accuracy']==1
        record=dict(bank_txn_id=tid,segment=g.txns[tid][3],before_correct=before,after_correct=after)
        groups[r['reason']].append(record)
        if before and not after:regressions.append(dict(record,reason=r['reason']))
    summary={reason:dict(changed=len(rs),fixed=sum(not r['before_correct'] and r['after_correct'] for r in rs),
        regressed=sum(r['before_correct'] and not r['after_correct'] for r in rs),still_wrong=sum(not r['before_correct'] and not r['after_correct'] for r in rs)) for reason,rs in groups.items()}
    write_json(RESULTS/'development_changes.json',dict(methods=summary,regressions=regressions,scope='Official transaction-correctness checks on already inspected development changes; no LIVE labels.'))
    print(summary)


if __name__=='__main__':main()
