#!/usr/bin/env python3
"""Compare the invariants dropped in step 3 (shadow) with those dropped in step 2 (bool).

Candidates are matched by (procedure, loop head, variable); the expression form
differs between the two files ($x.dup == 0 against $x == $x.shadow).
P6_19 is skipped: its step-3 BPL was not kept.
"""
import collections
import os

from common import CASES, STOCK, bench_dir, round_reports, failed_inv_lines, candidates

for name, od, base, bd in CASES:
    d = bench_dir(bd)
    sb = os.path.join(d, f"{base}-shadow-0.bpl")
    if not os.path.exists(sb):
        print("=====", name, ": no step-3 BPL kept, skipped")
        continue
    out = os.path.join(STOCK, od)
    bc = candidates(os.path.join(d, f"{base}-bool-0.bpl"))
    sc = candidates(sb)
    key = lambda v: v[:3]
    bdrop, sdrop = {}, {}
    for r, f in enumerate(round_reports(out, base, "bool")):
        for ln in failed_inv_lines(f):
            bdrop[key(bc[ln])] = r
    for r, f in enumerate(round_reports(out, base, "shadow")):
        for ln in failed_inv_lines(f):
            sdrop[key(sc[ln])] = r
    skeys = set(key(v) for v in sc.values() if v[3] != "unlikely_shadow_invariant")
    print("=====", name)
    print(" active step-3 candidates:", len(skeys),
          " of which dropped in step 2:", len(skeys & set(bdrop)))
    print(" step-3 drops so far:", len(sdrop),
          " also dropped in step 2:", sum(1 for k in sdrop if k in bdrop))
    print(" step-3 candidates not yet decided at the cap:", len(skeys - set(sdrop)))
    print(" step-2 drops per round:", sorted(collections.Counter(bdrop.values()).items()))
    print(" step-3 drops per round:", sorted(collections.Counter(sdrop.values()).items()))
