#!/usr/bin/env python3
"""Derive Table 3 CT-Prover `Time a:b` and `#Src x:y:z` from raw run output.

Usage:
  derive_table3.py <outputs root> <logs dir> [--md OUT.md] [--csv OUT.csv]

<outputs root> is either the live tree (`$CT_ROOT/bech`, files under
`<bench>/one_and_two_and_three/`) or the submission copy
(`raw/run2-fixed/outputs`, files under `<Bench_dir>/`, large files as `.gz`).
<logs dir> holds the timestamped per-directory logs written by run_table3.py.

Definitions (see report Section 2):
  a  step-2 time. If the driver finished the directory: detail CSV
     `1 + product1` (authors' own split, vfct_find_bug.py). If the directory
     was stopped after step 2: elapsed log time from the stem's
     `cp <stem>.json` line to its `bam-991 --process_mark` line, minus the
     bam-5 shadow-product time (the driver books that under step 3).
  b  step-3 time: `1 + product1 + product2`, or TO.
  TO any Boogie call reporting a time-out (`/timeLimit 3600`), or the 7200 s
     wall cap killing the directory before the step finished.
  OOM Boogie `OutOfMemoryException` in that step.
  x  integer after `all taint position!` in `<stem>-taintres.txt` (Phasar).
  y  distinct C source locations (file, line) of `This assertion might not
     hold` errors in the FINAL step-2 round (the round with no failing loop
     invariants). Boogie lines are mapped to the nearest preceding
     `assume {:sourceloc "...", line, col}` in `<stem>-bool-0.bpl`.
  z  same for the final step-3 round (`<stem>-shadow-*.txt`,
     `<stem>-shadow-0.bpl`). If step 3 did not finish, z is taken from the
     last completed shadow round and marked `*` (partial).
Also emitted for audit: bpl-line site counts and Boogie `N errors` footers
for the first and final rounds.
"""
from __future__ import annotations

import argparse
import csv
import gzip
import re
from pathlib import Path

PAPER = {
    "P4_3": ("24.05", "50.84", "49:48:48"), "P4_4": ("21.03", "44.76", "49:48:48"),
    "P5_1": ("TO", "TO", "48:–:–"), "P5_11": ("14.10", "30.68", "26:16:16"),
    "P6_1": ("9.36", "19.27", "12:1:1"), "P6_2": ("8.48", "17.24", "12:1:1"),
    "P6_5": ("983.86", "TO", "107:71:50"), "P6_13": ("8.85", "17.87", "6:4:4"),
    "P6_14": ("13.06", "26.57", "32:32:32"), "P6_15": ("13.06", "26.35", "32:32:32"),
    "P6_16": ("2561.81", "TO", "107:71:53"), "P6_17": ("9.75", "20.31", "11:8:8"),
    "P6_18": ("9.77", "20.12", "13:8:8"), "P6_19": ("3515.77", "TO", "142:70:39"),
    "P6_27": ("131.34", "503.23", "177:45:45"),
}
CASES = [
    ("P4_3", "Tongsuo/AES", "decrypt"), ("P4_4", "Tongsuo/AES", "encrypt"),
    ("P5_1", "Mbed-tls/RSA", "decrypt"), ("P5_11", "Mbed-tls/DES", "crypt_cbc"),
    ("P6_1", "BearSSL/AES_small", "decrypt"), ("P6_2", "BearSSL/AES_small", "encrypt"),
    ("P6_5", "BearSSL/RSA_i15", "decrypt"), ("P6_13", "BearSSL/AES_big_cbc", "key_schedule"),
    ("P6_14", "BearSSL/AES_big_cbc", "decrypt"), ("P6_15", "BearSSL/AES_big_cbc", "encrypt"),
    ("P6_16", "BearSSL/RSA_i15_pkcs1", "sign"), ("P6_17", "BearSSL/DES_table", "cbc_decrypt"),
    ("P6_18", "BearSSL/DES_table", "cbc_encrypt"), ("P6_19", "BearSSL/RSA_i31_pkcs1", "sign"),
    ("P6_27", "BearSSL/RSA_i32", "decrypt"),
]
ERR_ASSERT = re.compile(r".*Error:.*This assertion might not.*")
ERR_INV = re.compile(r".*Error:.*This loop invariant might not.*")
SOURCELOC = re.compile(r'sourceloc "([^"]+)", (\d+), (\d+)')


def find(p: Path) -> Path | None:
    if p.exists():
        return p
    gz = p.with_name(p.name + ".gz")
    return gz if gz.exists() else None


def read_lines(p: Path | None) -> list[str]:
    if p is None:
        return []
    if p.suffix == ".gz":
        with gzip.open(p, "rt", errors="ignore") as f:
            return f.read().splitlines()
    return p.read_text(errors="ignore").splitlines()


class Report:
    """One Boogie stdout report."""

    def __init__(self, path: Path | None):
        self.path = path
        lines = read_lines(path)
        self.sites: set[int] = set()
        self.inv: set[int] = set()
        self.footer = None
        self.n_errors = None
        self.timeout = False
        self.oom = False
        for line in lines:
            m = re.search(r"bpl\((\d+),", line)
            if m and ERR_ASSERT.match(line):
                self.sites.add(int(m.group(1)))
            elif m and ERR_INV.match(line):
                self.inv.add(int(m.group(1)))
            if "Boogie program verifier finished" in line:
                self.footer = line.strip()
                mm = re.search(r"(\d+) errors?", line)
                self.n_errors = int(mm.group(1)) if mm else 0
                if "time out" in line:
                    self.timeout = True
            if "OutOfMemoryException" in line:
                self.oom = True
            if re.search(r"timed out|time out", line, re.I) and "Verifying" in line:
                self.timeout = True
        self.finished = self.footer is not None


def rounds(outdir: Path, stem: str, kind: str) -> list[Report]:
    reps = []
    first = find(outdir / f"{stem}-{kind}-0.txt")
    if first is None:
        return reps
    reps.append(Report(first))
    k = 1
    while True:
        p = find(outdir / f"{stem}-{kind}{k}.txt")
        if p is None:
            break
        reps.append(Report(p))
        k += 1
    return reps


def src_locations(bpl: Path | None, sites: set[int]) -> set[tuple[str, str]]:
    lines = read_lines(bpl)
    out = set()
    for n in sites:
        k = n - 1
        while k >= 0 and "sourceloc" not in lines[k] and not lines[k].startswith("procedure"):
            k -= 1
        m = SOURCELOC.search(lines[k]) if k >= 0 else None
        out.add((m.group(1), m.group(2)) if m else ("?", str(n)))
    return out


def detail_times(outdir: Path, stem: str):
    p = find(outdir / "one_and_two_and_three_detail.csv")
    if p is None:
        return None
    for row in csv.DictReader(read_lines(p)):
        if row.get("algoritm") == stem:
            return float(row["1"]), float(row["product1"]), float(row["product2"])
    return None


def log_marks(log: Path | None, stem: str):
    """Elapsed times from the timestamped log for this stem."""
    res = {"start": None, "step3": None, "end": None, "wall_timeout": False, "oom_in_log": False,
           "log_closed": False, "rc": None, "bam5_s": 0.0}
    if log is None or not log.exists():
        res["log_closed"] = True   # no timestamped log (e.g. run 1): nothing is running
        return res
    cur = False
    bam5_start = None
    for line in log.read_text(errors="ignore").splitlines():
        m = re.match(r"\[t=\s*([\d.]+)\] (.*)", line)
        if "WALL TIMEOUT" in line:
            res["wall_timeout"] = True
        if line.startswith("# end "):
            res["log_closed"] = True
            mrc = re.search(r"rc=(-?\d+)", line)
            res["rc"] = int(mrc.group(1)) if mrc else None
        if not m:
            continue
        t, body = float(m.group(1)), m.group(2)
        # the driver copies every <stem>.ll first, then handles one stem at a
        # time starting with `cp <stem>.json one_and_two_and_three`
        if re.match(r"cp \S+\.json one_and_two_and_three$", body.strip()):
            cur = body.strip() == f"cp {stem}.json one_and_two_and_three"
            if cur:
                res["start"] = t
            continue
        if cur:
            res["end"] = t
            if bam5_start is not None and body.strip():
                res["bam5_s"] = t - bam5_start      # next command starts when bam-5 ends
                bam5_start = None
            if "bam/bam-5/" in body and "--shadowing" in body:
                bam5_start = t
            if "--process_mark" in body and f"{stem}-tmp-2.bpl" in body:
                res["step3"] = t
            if "OutOfMemoryException" in body:
                res["oom_in_log"] = True
    return res


def rel(ours: float | None, paper: str) -> str:
    try:
        p = float(paper)
    except ValueError:
        return "n/a"
    if ours is None:
        return "n/a"
    return f"{100 * (ours - p) / p:+.1f}%"


def derive(root: Path, logs: Path) -> list[dict]:
    rows = []
    for pid, bench, stem in CASES:
        outdir = root / bench / "one_and_two_and_three"
        if not outdir.is_dir():
            outdir = root / bench.replace("/", "_")
        log = logs / (bench.replace("/", "_") + ".log")
        lm = log_marks(log, stem)
        det = detail_times(outdir, stem)
        bools, shadows = rounds(outdir, stem, "bool"), rounds(outdir, stem, "shadow")
        taint = "\n".join(read_lines(find(outdir / f"{stem}-taintres.txt")))
        mx = re.search(r"all taint position!\s*(\d+)", taint)
        x = mx.group(1) if mx else "–"

        step2_oom = any(r.oom for r in bools) or (lm["oom_in_log"] and lm["step3"] is None)
        step2_to = any(r.timeout for r in bools)
        step2_done = bool(bools) and bools[-1].finished and not bools[-1].inv and not step2_oom \
            and not step2_to and (det is not None or lm["step3"] is not None)
        step3_to = any(r.timeout for r in shadows)
        step3_oom = any(r.oom for r in shadows)
        step3_done = step2_done and det is not None and bool(shadows) and shadows[-1].finished \
            and not shadows[-1].inv and not step3_to and not step3_oom

        a_val = b_val = None
        if step2_done:
            # log fallback: the driver books the bam-5 shadow product (t6) under
            # step 3, so remove it to stay on the authors' split
            a_val = det[0] + det[1] if det else lm["step3"] - lm["start"] - lm["bam5_s"]
            a = f"{a_val:.2f}"
        else:
            a = "OOM" if step2_oom else "TO"
        if step3_done:
            b_val = det[0] + det[1] + det[2]
            b = f"{b_val:.2f}"
        else:
            b = "OOM" if step3_oom else ("TO" if step2_done or a == "TO" else "–")

        bool0 = find(outdir / f"{stem}-bool-0.bpl")
        shadow0 = find(outdir / f"{stem}-shadow-0.bpl")
        y = str(len(src_locations(bool0, bools[-1].sites))) if step2_done else "–"
        if step3_done:
            z = str(len(src_locations(shadow0, shadows[-1].sites)))
        else:
            done = [r for r in shadows if r.finished]
            z = (str(len(src_locations(shadow0, done[-1].sites))) + "*") if done else "–"

        status = "ok"
        if not step2_done:
            status = f"step 2 {a}"
            if lm["wall_timeout"]:
                status += " (wall cap)"
        elif not step3_done:
            status = f"step 3 {b}" + (" (wall cap)" if lm["wall_timeout"] else " (Boogie /timeLimit)"
                                       if step3_to else "")
        stopped = lm["rc"] is not None and lm["rc"] < 0 and not lm["wall_timeout"]
        if stopped and status != "ok":
            status += " (stopped at cutoff)"
        if not lm["log_closed"]:
            status = "running"
        pa, pb, ps = PAPER[pid]
        rows.append({
            "id": pid, "bench": bench, "stem": stem,
            "a": a, "b": b, "x": x, "y": y, "z": z,
            "paper_a": pa, "paper_b": pb, "paper_xyz": ps,
            "abs_a": f"{a_val - float(pa):+.2f}" if a_val is not None and pa not in ("TO",) else "n/a",
            "rel_a": rel(a_val, pa),
            "abs_b": f"{b_val - float(pb):+.2f}" if b_val is not None and pb not in ("TO",) else "n/a",
            "rel_b": rel(b_val, pb),
            "status": status,
            "bool_rounds": len(bools), "shadow_rounds": len(shadows),
            "detail_1": f"{det[0]:.3f}" if det else "", "detail_product1": f"{det[1]:.3f}" if det else "",
            "detail_product2": f"{det[2]:.3f}" if det else "",
            "log_step2_s": f"{lm['step3'] - lm['start'] - lm['bam5_s']:.1f}" if lm["step3"] and lm["start"] is not None else "",
            "y_bplsites_final": len(bools[-1].sites) if step2_done else "",
            "y_N_first": bools[0].n_errors if bools else "",
            "z_bplsites_final": len(shadows[-1].sites) if shadows and shadows[-1].finished else "",
            "z_N_first": shadows[0].n_errors if shadows else "",
            "wall_timeout": lm["wall_timeout"],
        })
    return rows


def to_md(rows: list[dict]) -> str:
    out = ["| ID | a:b ours (s) | a:b paper (s) | rel a | rel b | x:y:z ours | x:y:z paper | status |",
           "|---|---|---|---|---|---|---|---|"]
    for r in rows:
        out.append(f"| {r['id']} | {r['a']}:{r['b']} | {r['paper_a']}:{r['paper_b']} | {r['rel_a']} | "
                   f"{r['rel_b']} | {r['x']}:{r['y']}:{r['z']} | {r['paper_xyz']} | {r['status']} |")
    return "\n".join(out) + "\n"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("root")
    ap.add_argument("logs")
    ap.add_argument("--csv")
    ap.add_argument("--md")
    args = ap.parse_args()
    rows = derive(Path(args.root), Path(args.logs))
    if args.csv:
        with open(args.csv, "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
            w.writeheader()
            w.writerows(rows)
    md = to_md(rows)
    if args.md:
        Path(args.md).write_text(md)
    print(md)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
