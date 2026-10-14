#!/usr/bin/env python3
"""Assertion failures in step-2 round 0 against the final step-2 round, and where the new ones are."""
import collections
import os
import re

from common import CASES, STOCK, bench_dir, round_reports, failed_inv_lines, ASSERT_ERR

for name, od, base, bd in CASES:
    out = os.path.join(STOCK, od)
    L = open(os.path.join(bench_dir(bd), f"{base}-bool-0.bpl")).read().split("\n")
    starts = [(i, re.match(r'procedure\s+(?:\{[^}]*\}\s*)*([\w.$#]+)\(', l).group(1))
              for i, l in enumerate(L, 1) if l.startswith("procedure ")]

    def proc(ln):
        return max((i, n) for i, n in starts if i <= ln)[1]

    reps = round_reports(out, base, "bool")
    alarms = lambda f: set(int(x) for x in ASSERT_ERR.findall(open(f).read()))
    a0, af = alarms(reps[0]), alarms(reps[-1])
    lost_inv = set(proc(x) for f in reps for x in failed_inv_lines(f))
    new = af - a0
    c = collections.Counter(proc(x) for x in new)
    print(f"{name}: unique alarm lines round 0 {len(a0)}, final {len(af)}, new {len(new)},"
          f" new ones in procedures that lost an invariant {sum(v for p, v in c.items() if p in lost_inv)}")
    print("   ", c.most_common(8))
