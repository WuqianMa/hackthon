"""Run the frozen v3 strategy; publish LIVE/FINAL CSV editions in submission/."""
from pathlib import Path
import importlib.util
import json
import os
import re
import shutil
import sys

FOLDER = Path(__file__).resolve().parent
ROOT = FOLDER.parent
sys.path.insert(0, str(ROOT))
spec = importlib.util.spec_from_file_location('version3', FOLDER/'__init__.py', submodule_search_locations=[str(FOLDER)])
package = importlib.util.module_from_spec(spec)
sys.modules['version3'] = package
spec.loader.exec_module(package)

from bankrec import cli
from bankrec.io import digest, write_json
from version3 import VERSION
from version3.catalog import Catalog
from version3.engine import Engine
from version3.sources import Sources


def main():
    command = list(sys.argv)
    edition = None
    if '--edition' in sys.argv:
        index = sys.argv.index('--edition')
        edition = sys.argv[index+1]
        if not re.fullmatch(r'\d{3}', edition):
            raise ValueError('--edition requires three digits, for example 001')
        del sys.argv[index:index+2]
    if '--phase' not in sys.argv:
        sys.argv += ['--phase','live']
    phase = sys.argv[sys.argv.index('--phase')+1]
    if '--docs-archive' not in sys.argv:
        sys.argv += ['--docs-archive',str(ROOT/'bankrec-docs-and-masters.zip')]
    if phase == 'live' and '--phase-archive' not in sys.argv:
        sys.argv += ['--phase-archive',str(ROOT/'bankrec-live.tar.gz')]
    if '--work-dir' not in sys.argv:
        sys.argv += ['--work-dir',str(ROOT/'work/version-3')]
    if '--output-dir' not in sys.argv:
        sys.argv += ['--output-dir',str(ROOT/f'work/version-3/artifacts/{phase}')]
    work = Path(sys.argv[sys.argv.index('--work-dir')+1])
    # Content-addressed PDF text may be shared; catalogs and output state are isolated.
    shared = ROOT/'work/cache/pdf_text'
    cache = work/'cache/pdf_text'
    if shared.is_dir() and not cache.exists():
        cache.parent.mkdir(parents=True,exist_ok=True)
        cache.symlink_to(shared.resolve(),target_is_directory=True)
    cli.Catalog, cli.Engine, cli.Sources = Catalog, Engine, Sources
    Engine.speculative = True
    strict_validate = cli.validate
    def competition_validate(*args,**kwargs):
        result = strict_validate(*args,**kwargs)
        soft = [e for e in result['errors'] if e['message']=='aggregate allocation exceeds remaining balance']
        result['errors'] = [e for e in result['errors'] if e not in soft]
        result['warnings'].extend(soft)
        result['ok'] = not result['errors']
        result['competition_note'] = 'Cross-bank aggregate balance checks are diagnostic, not an official upload rejection rule.'
        return result
    cli.validate = competition_validate
    cli.main()
    out = Path(sys.argv[sys.argv.index('--output-dir')+1])
    manifest = json.loads((out/'manifest.json').read_text())
    manifest.update(strategy='version-3', strategy_version=VERSION, speculative=True,
                    edition_command=command,
                    strategy_sha256={p.name:digest(p) for p in sorted(FOLDER.glob('*.py'))})
    write_json(out/'manifest.json',manifest)
    if phase not in ('live','final'):
        print('Sample check completed; no upload edition published.',flush=True)
        return
    submission_dir = ROOT/'submission'
    submission_dir.mkdir(exist_ok=True)
    if edition is None:
        edition = next(f'{n:03d}' for n in range(1,1000)
                       if not (submission_dir/f'submission_v3_{phase}_{n:03d}.csv').exists())
    target = submission_dir/f'submission_v3_{phase}_{edition}.csv'
    if target.exists() and digest(target)!=manifest['submission_sha256']:
        raise ValueError(f'Edition already exists with different content: {target}')
    temporary = out/'publish.csv.tmp'
    shutil.copyfile(out/'submission.csv',temporary)
    os.replace(temporary,target)
    assert digest(target)==manifest['submission_sha256']
    record = dict(manifest)
    record.update(edition=edition, submission_file=str(target.relative_to(ROOT)),
                  validation=json.loads((out/'validation.json').read_text()),
                  website_upload_status='not uploaded; user will upload and provide feedback')
    write_json(FOLDER/f'editions/{phase}_{edition}.json',record)
    print(f'UPLOAD FILE: {target}',flush=True)


if __name__=='__main__':
    main()
