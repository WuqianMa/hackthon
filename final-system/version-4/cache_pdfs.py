"""Optional parallel, atomic PDF text prewarming; no targets or model calls."""
from concurrent.futures import ProcessPoolExecutor
import hashlib
import os
from pathlib import Path
import sys

from data import ROOT
from bankrec.io import rows,table,is_data_file


def cache_one(filename):
    path=Path(filename);key=hashlib.sha256(path.read_bytes()).hexdigest()
    dest=ROOT/'work/cache/pdf_text'/f'{key}.txt'
    if dest.exists():return 0
    from pypdf import PdfReader
    value='\n'.join(page.extract_text() or '' for page in PdfReader(path).pages)
    temporary=dest.with_suffix(f'.{os.getpid()}.tmp')
    temporary.write_text(value,encoding='utf-8');os.replace(temporary,dest)
    return 1


def main():
    phase=ROOT/'work/archives/train/train'
    paths=[str(phase/'pdfs'/r['file']) for r in rows(table(phase/'pdfs','index'))]
    paths.extend(str(p) for p in (phase/'remittance_advices').rglob('*.pdf') if is_data_file(p))
    (ROOT/'work/cache/pdf_text').mkdir(parents=True,exist_ok=True)
    new=0
    with ProcessPoolExecutor(max_workers=4) as executor:
        for n,created in enumerate(executor.map(cache_one,paths,chunksize=32),1):
            new+=created
            if n%5000==0:print(f'PDF cache {n:,}/{len(paths):,}; added {new:,}',flush=True)
    print(f'PDF cache complete: {len(paths):,} files, {new:,} added',flush=True)


if __name__=='__main__':main()
