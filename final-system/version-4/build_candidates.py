"""Freeze label-free starter candidate data for repeatable model experiments."""
from pathlib import Path
import joblib
from data import prepare,ROOT

if __name__=='__main__':
    work=ROOT/'work/version-4'
    dataset=prepare(work)
    joblib.dump(dataset,work/'candidates.joblib',compress=3)
    print('Saved label-free candidates:',dataset['X'].shape,flush=True)
