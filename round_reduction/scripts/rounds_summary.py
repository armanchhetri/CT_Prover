#!/usr/bin/env python3
"""Per round: time, invariant failures, unique failed lines and their kind, assertion failures."""
import collections
import os
import re

from common import CASES, STOCK, bench_dir, round_reports, round_times, candidates, INV_ERR

for name, od, base, bd in CASES:
    out = os.path.join(STOCK, od)
    times = round_times(out)
    print("=====", name)
    t = 0
    for step in ("bool", "shadow"):
        bpl = os.path.join(bench_dir(bd), f"{base}-{step}-0.bpl")
        cand = candidates(bpl) if os.path.exists(bpl) else None
        if cand:
            print(f" {step}: candidates in {os.path.basename(bpl)}:",
                  dict(collections.Counter(v[3] for v in cand.values())))
        dropped = set()
        for r, f in enumerate(round_reports(out, base, step)):
            txt = open(f).read()
            errs = INV_ERR.findall(txt)
            uniq = set(int(a) for a, _ in errs)
            dropped |= uniq
            how = dict(collections.Counter(b for _, b in errs))
            kinds = dict(collections.Counter(cand[x][3] for x in uniq)) if cand else {}
            nas = len(re.findall(r'This assertion might not', txt))
            fin = "finished" in txt
            sec = f"{times[t]:7.0f} s" if t < len(times) and fin else "killed at cap"
            t += 1
            print(f"  {step} r{r}: {sec}  inv errors {len(errs):3d}  unique lines {len(uniq):3d}"
                  f"  {how}  {kinds}  assertion errors {nas}")
        print(f"  {step}: distinct invariant lines dropped = {len(dropped)}")
