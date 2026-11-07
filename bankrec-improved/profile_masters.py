"""Profile master tables without consulting allocation labels."""
import argparse
import json
from collections import Counter
from pathlib import Path
from matcher import read_csv


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--data', default=str(Path(__file__).resolve().parent.parent / 'bankrec-docs-and-masters'))
    p.add_argument('--out', default=str(Path(__file__).resolve().parent / 'masters_profile.json'))
    args = p.parse_args()
    result = {}
    for path in sorted((Path(args.data) / 'masters').glob('*.csv')):
        rows = read_csv(path)
        fields = {}
        for column in rows[0]:
            counts = Counter(r[column] for r in rows)
            fields[column] = {'filled': len(rows) - counts[''], 'missing': counts[''],
                              'unique_nonempty': len(counts) - int('' in counts)}
            if len(counts) <= 30:
                fields[column]['distribution'] = dict(counts)
        result[path.name] = {'rows': len(rows), 'columns': fields}
    Path(args.out).write_text(json.dumps(result, indent=2, ensure_ascii=False))
    print('Profile written:', args.out)


if __name__ == '__main__':
    main()
