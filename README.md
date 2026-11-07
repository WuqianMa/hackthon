# Talky bank reconciliation

The `jiahua` branch contains an independent rule-based solver in
[`bankrec-improved`](bankrec-improved/README.md). Original challenge data and the
official starter are not included or modified.

## Main files

- `bankrec-improved/matcher.py`: identity, invoice reference, amount, batch,
  remittance and accounting-exception matching.
- `bankrec-improved/train_runner.py`: full TRAIN execution with entity groups,
  reusable checkpoints and a guard against reading golden labels.
- `bankrec-improved/evaluate_train.py`: separate evaluation with the original
  official scorer. Only offline file-size/row limits are enlarged for TRAIN.
- `bankrec-improved/test_matcher.py`: independent accounting cases.

The solver uses `pypdf` for PDF text and `openpyxl` for Excel templates; it does
not use OCR or an LLM. See the detailed README for supported cases and limits.

## Run

Python 3.12 is the verified runtime. Install dependencies with:

```bash
python3 -m pip install -r bankrec-improved/requirements.txt
python3 -m unittest discover -s bankrec-improved -p 'test_*.py'
```

If the original data folders are alongside this repository:

```bash
python3 -u bankrec-improved/train_runner.py \
  --train ../train --docs ../bankrec-docs-and-masters --workers 2

python3 -u bankrec-improved/evaluate_train.py \
  bankrec-improved/train_results/train_predictions.csv.gz \
  --train ../train --docs ../bankrec-docs-and-masters --by-group
```

The sample experiment scored **81.28/100**. Full TRAIN results will be recorded
after its ongoing run completes. No LIVE submission has been made.

Raw datasets, temporary partitions and large prediction files are excluded
from Git. Small evaluation JSON files and reports can be committed.
