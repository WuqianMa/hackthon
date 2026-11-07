from __future__ import annotations

import csv
import gzip
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import shutil
import tarfile
import zipfile
import xml.etree.ElementTree as ET
from decimal import Decimal, ROUND_HALF_UP
import re
import unicodedata

FIELDS = ["bank_txn_id", "item_id", "amount", "category", "exception"]
EXCEPTIONS = {"PARTIAL", "OVERPAYMENT", "SHORT_DISCOUNT", "SHORT_BANK_CHARGES",
              "SHORT_WITHHOLDING", "SHORT_DISPUTE", "DUPLICATE_PAYMENT", "UNIDENTIFIED",
              "RETURNED", "FX_DIFFERENCE"}
HASHES = {
    "docs": "210b2404efd011af248a251db2bc0ee85a2ddaa1d56a7a0ca0b95ede18cc1071",
    "train": "163f51a818193f6310b6fba96e3830e4347c883b0b84bc070153f5018e3f06b8",
    "live": "eec490d7c605048d0d3a8400af97ee13c9fe49e68dfeb3d68546daf50d8af520",
}


def norm(value):
    s = unicodedata.normalize("NFKD", value or "").encode("ascii", "ignore").decode().upper()
    return re.sub(r"[^A-Z0-9]", "", s)


def plain(value):
    return unicodedata.normalize("NFKD", value or "").encode("ascii", "ignore").decode().upper()


def cents(value):
    value = str(value or "0").strip().replace(",", "")
    n = Decimal(value)
    if not n.is_finite():
        raise ValueError("non-finite amount")
    return int((n * 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def money(n):
    return f"{n // 100}.{n % 100:02d}"


def rows(path):
    path = Path(path)
    op = gzip.open if path.suffix == ".gz" else open
    with op(path, "rt", encoding="utf-8-sig", newline="") as f:
        yield from csv.DictReader(f)


def table(folder, name, required=True):
    for ext in (".csv.gz", ".csv"):
        p = Path(folder) / (name + ext)
        if p.exists():
            return p
    if required:
        raise FileNotFoundError(f"missing {name}.csv[.gz] in {folder}")


def is_data_file(path):
    """macOS AppleDouble resource forks retain data suffixes but contain binary metadata."""
    path = Path(path)
    return path.is_file() and not any(p.startswith("._") or p == "__MACOSX" or p == ".DS_Store" for p in path.parts)


def digest(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def write_json(path, value):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    tmp = Path(str(path) + ".tmp")
    tmp.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    os.replace(tmp, path)


def extract(archive, destination, expected):
    """Verify before extraction; reject links/traversal; publish a complete tree atomically."""
    archive, destination = Path(archive).resolve(), Path(destination).resolve()
    actual = digest(archive)
    if actual != expected:
        raise ValueError(f"SHA-256 mismatch for {archive.name}: expected {expected}, got {actual}")
    marker = destination / ".archive.json"
    if marker.exists() and json.loads(marker.read_text()).get("sha256") == actual:
        return destination, actual
    if destination.exists():
        raise ValueError(f"refusing to replace an unverified extraction: {destination}")
    stage = destination.with_name(destination.name + ".extracting")
    if stage.exists():
        shutil.rmtree(stage)
    stage.mkdir(parents=True)
    total, names = 0, set()

    def target(name, size):
        nonlocal total
        p = PurePosixPath(name)
        if p.is_absolute() or ".." in p.parts or "\\" in name or not p.parts:
            raise ValueError(f"unsafe archive path: {name}")
        normalized = str(p)
        if normalized in names:
            raise ValueError(f"duplicate archive path: {name}")
        names.add(normalized)
        total += size
        if total > 30 * 1024 ** 3:
            raise ValueError("archive exceeds 30 GiB extraction guard")
        return stage.joinpath(*p.parts)

    try:
        if zipfile.is_zipfile(archive):
            with zipfile.ZipFile(archive) as z:
                for m in z.infolist():
                    if (m.external_attr >> 16) & 0o170000 == 0o120000:
                        raise ValueError("archive symlinks are forbidden")
                    out = target(m.filename, m.file_size)
                    if m.is_dir():
                        out.mkdir(parents=True, exist_ok=True)
                    else:
                        out.parent.mkdir(parents=True, exist_ok=True)
                        with z.open(m) as src, out.open("wb") as dst:
                            shutil.copyfileobj(src, dst)
        else:
            with tarfile.open(archive, "r|*") as t:
                for m in t:
                    if not (m.isdir() or m.isfile()):
                        raise ValueError(f"archive links/special files are forbidden: {m.name}")
                    out = target(m.name, m.size)
                    if m.isdir():
                        out.mkdir(parents=True, exist_ok=True)
                    else:
                        out.parent.mkdir(parents=True, exist_ok=True)
                        with t.extractfile(m) as src, out.open("wb") as dst:
                            shutil.copyfileobj(src, dst)
        write_json(stage / ".archive.json", {"archive": archive.name, "sha256": actual,
                                             "members": len(names), "expanded_bytes": total})
        destination.parent.mkdir(parents=True, exist_ok=True)
        os.replace(stage, destination)
    except Exception:
        shutil.rmtree(stage, ignore_errors=True)
        raise
    return destination, actual


def find_folder(root, child):
    root = Path(root)
    if (root / child).is_dir():
        return root / child
    hits = [p for p in root.glob("*/" + child) if p.is_dir()]
    if len(hits) != 1:
        raise ValueError(f"expected exactly one {child}/ under {root}")
    return hits[0]


def xlsx_rows(path):
    """Read cached cell values from the first worksheet without Excel or formulas."""
    ns = {"s": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
    with zipfile.ZipFile(path) as z:
        shared = []
        if "xl/sharedStrings.xml" in z.namelist():
            shared = ["".join(x.itertext()) for x in ET.fromstring(z.read("xl/sharedStrings.xml"))]
        # Generated challenge workbooks use sheet1. No formula evaluation or macros.
        root = ET.fromstring(z.read("xl/worksheets/sheet1.xml"))
        for row in root.findall(".//s:sheetData/s:row", ns):
            values = {}
            for c in row:
                col = re.match(r"[A-Z]+", c.attrib["r"])[0]
                idx = 0
                for char in col:
                    idx = idx * 26 + ord(char) - 64
                val = c.find("s:v", ns)
                text = val.text if val is not None else ""
                if c.attrib.get("t") == "s":
                    text = shared[int(text)]
                elif c.attrib.get("t") == "inlineStr":
                    text = "".join(c.find("s:is", ns).itertext()) if c.find("s:is", ns) is not None else ""
                values[idx - 1] = text or ""
            yield [values.get(i, "") for i in range(max(values, default=-1) + 1)]


def pdf_text(path, cache):
    key = digest(path)
    cached = Path(cache) / (key + ".txt")
    if cached.exists():
        return cached.read_text(encoding="utf-8")
    from pypdf import PdfReader
    value = "\n".join(page.extract_text() or "" for page in PdfReader(path).pages)
    cached.parent.mkdir(parents=True, exist_ok=True)
    cached.write_text(value, encoding="utf-8")
    return value
