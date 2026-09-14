#!/usr/bin/env python3
"""Check that CT-Prover's step-3 marks land on the statements they target.

findbuginboogie.trans_bool_to_shadow() collects line numbers from Boogie reports
on the *bool* program (<stem>-bool-N.bpl, built by bam-7) and inserts
`assume {:VFCTMarked} true;` before the same line numbers of the *shadow*
program (<stem>-tmp.bpl, built by bam-5). bam-991 --process_mark then keeps only
marked shadow assertions and rewrites every unmarked one to `x := x.shadow`.
The marks are only meaningful if both files are line-aligned.

This script re-derives the mark set exactly as the driver does and reports:
  marks          number of distinct line numbers marked
  on_assert      how many of them hit an `assert` line in <stem>-tmp.bpl
  first_div      first line where bool/shadow files differ structurally
                 (ignoring .dup/.shadow renaming); '-' if none

Usage:
  check_mark_alignment.py <one_and_two_and_three dir> <stem> [tmp.bpl override]
  check_mark_alignment.py --all <bech root | raw/run2-fixed/outputs>
"""
from __future__ import annotations

import glob
import gzip
import re
import sys
from pathlib import Path

CASES = [
    ("P4_3", "Tongsuo/AES", "decrypt"),
    ("P4_4", "Tongsuo/AES", "encrypt"),
    ("P5_1", "Mbed-tls/RSA", "decrypt"),
    ("P5_11", "Mbed-tls/DES", "crypt_cbc"),
    ("P6_1", "BearSSL/AES_small", "decrypt"),
    ("P6_2", "BearSSL/AES_small", "encrypt"),
    ("P6_5", "BearSSL/RSA_i15", "decrypt"),
    ("P6_13", "BearSSL/AES_big_cbc", "key_schedule"),
    ("P6_14", "BearSSL/AES_big_cbc", "decrypt"),
    ("P6_15", "BearSSL/AES_big_cbc", "encrypt"),
    ("P6_16", "BearSSL/RSA_i15_pkcs1", "sign"),
    ("P6_17", "BearSSL/DES_table", "cbc_decrypt"),
    ("P6_18", "BearSSL/DES_table", "cbc_encrypt"),
    ("P6_19", "BearSSL/RSA_i31_pkcs1", "sign"),
    ("P6_27", "BearSSL/RSA_i32", "decrypt"),
]


def find(p: Path) -> Path | None:
    if p.exists():
        return p
    gz = p.with_name(p.name + ".gz")
    return gz if gz.exists() else None


def read_lines(p: Path) -> list[str]:
    if p.suffix == ".gz":
        with gzip.open(p, "rt", errors="ignore") as f:
            return f.read().splitlines()
    return p.read_text(errors="ignore").splitlines()


def key(line: str) -> str:
    s = line.strip()
    for p in ("requires", "assert", "havoc", "call", "goto", "return",
              "modifies", "axiom", "function", "const", "type", "{", "}"):
        if s.startswith(p):
            return p
    if s.startswith("assume"):
        return s
    if s.startswith("var"):
        return "var " + re.sub(r"\.(dup|shadow)", "", s.split(":")[0])
    if s.startswith("procedure"):
        m = re.match(r"procedure (?:\{[^}]*\} )*([^(]+)", s)
        return "proc " + (m.group(1) if m else "")
    if ":=" in s:
        return "asg " + re.sub(r"\.(dup|shadow)", ".S", s.split(":=")[0])
    return s


def error_lines(path: str, pattern: str) -> set[int]:
    out = set()
    for line in read_lines(Path(path)):
        if re.match(pattern, line):
            m = re.search(r"bpl\((\d+),", line)
            if m:
                out.add(int(m.group(1)))
    return out


def marks(outdir: Path, stem: str) -> set[int] | None:
    first = find(outdir / f"{stem}-bool-0.txt")
    if first is None or not read_lines(first):
        return None
    rounds = sorted(
        int(re.search(r"bool(\d+)\.txt(\.gz)?$", p).group(1))
        for p in glob.glob(str(outdir / f"{stem}-bool[0-9]*.txt*"))
    )
    txts = [str(first)] + [str(find(outdir / f"{stem}-bool{n}.txt")) for n in rounds]
    el: set[int] = set()
    for t in txts[:-1]:
        el |= error_lines(t, r".*Error:.*This loop invariant might not.*")
    el |= error_lines(txts[-1], r".*Error:.*This assertion might not.*")
    return el


def check(outdir: Path, stem: str, tmp_override: str | None = None) -> dict:
    boolf = find(outdir / f"{stem}-bool-0.bpl")
    tmpf = Path(tmp_override) if tmp_override else find(outdir / f"{stem}-tmp.bpl")
    if boolf is None or tmpf is None:
        return {"status": "missing bpl"}
    b = read_lines(boolf)
    t = read_lines(tmpf)
    first_div = next((i + 1 for i, (x, y) in enumerate(zip(b, t)) if key(x) != key(y)), None)
    el = marks(outdir, stem)
    if el is None:
        return {"status": "no bool report", "bool_lines": len(b), "tmp_lines": len(t),
                "first_div": first_div}
    on_assert = sum(1 for n in el if n <= len(t) and t[n - 1].lstrip().startswith("assert"))
    return {"status": "ok" if on_assert == len(el) else "MISALIGNED",
            "bool_lines": len(b), "tmp_lines": len(t), "first_div": first_div,
            "max_mark": max(el) if el else 0, "marks": len(el), "on_assert": on_assert}


def main() -> int:
    if len(sys.argv) >= 3 and sys.argv[1] == "--all":
        root = Path(sys.argv[2])
        print("id,bench,stem,bool_lines,tmp_lines,first_div,max_mark,marks,on_assert,status")
        for pid, d, stem in CASES:
            outdir = root / d / "one_and_two_and_three"
            if not outdir.is_dir():
                outdir = root / d.replace("/", "_")      # submission raw layout
            r = check(outdir, stem)
            print(",".join(str(v) for v in (
                pid, d, stem, r.get("bool_lines", ""), r.get("tmp_lines", ""),
                r.get("first_div") or "-", r.get("max_mark", ""), r.get("marks", ""),
                r.get("on_assert", ""), r["status"])))
        return 0
    if len(sys.argv) < 3:
        print(__doc__)
        return 2
    print(check(Path(sys.argv[1]), sys.argv[2], sys.argv[3] if len(sys.argv) > 3 else None))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
