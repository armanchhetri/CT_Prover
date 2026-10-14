#!/usr/bin/env python3
"""For each invariant dropped in step 2, follow the variable's definitions back to
memory loads and parameters (P6_5 by default; pass P6_16 or P6_19 to change)."""
import collections
import os
import re
import sys

from common import CASES, STOCK, bench_dir, round_reports, failed_inv_lines

want = sys.argv[1] if len(sys.argv) > 1 else "P6_5"
name, od, base, bd = next(c for c in CASES if c[0] == want)
L = open(os.path.join(bench_dir(bd), f"{base}-bool-0.bpl")).read().split("\n")

procs, cur = {}, None
for i, l in enumerate(L, 1):
    m = re.match(r'procedure\s+(?:\{[^}]*\}\s*)*([\w.$#]+)\(', l)
    if m:
        cur = m.group(1)
        procs[cur] = {"start": i, "defs": collections.defaultdict(list)}
    if cur:
        m = re.match(r'\s*(\$[\w]+) := (.*);', l)
        if m and not m.group(1).endswith(".dup"):
            procs[cur]["defs"][m.group(1)].append(m.group(2))


def proc_of(ln):
    return max((v["start"], p) for p, v in procs.items() if v["start"] <= ln)[1]


def trace(p, var, depth=0, seen=None):
    seen = seen if seen is not None else set()
    if var in seen or depth > 25:
        return []
    seen.add(var)
    defs = procs[p]["defs"].get(var, [])
    if not defs:
        return [f"{var}=param"]
    res = []
    for rhs in defs:
        if "$load" in rhs:
            ptr = re.search(r'\$load\.\w+\(\$M\.\d+,\s*(\$p\d+)\)', rhs)
            pdef = procs[p]["defs"].get(ptr.group(1), [""])[0] if ptr else ""
            hdr = " [index 0]" if re.search(r'\$mul\.ref\(0,', pdef) else ""
            res.append(f"{var}:={rhs[:40]}{hdr}")
        for v in re.findall(r'\$[ip]\d+\b', rhs):
            if v != var:
                res += trace(p, v, depth + 1, seen)
    return res


summary = collections.Counter()
for r, f in enumerate(round_reports(os.path.join(STOCK, od), base, "bool")):
    for ln in sorted(failed_inv_lines(f)):
        p = proc_of(ln)
        var = re.search(r'\((\$\w+)\.dup', L[ln - 1]).group(1)
        t = sorted(set(trace(p, var)))
        kind = "header word x[0]" if any("[index 0]" in x for x in t) else "parameter or other"
        summary[kind] += 1
        print(f"r{r} {p}:{var}  <- {' | '.join(t)[:160]}")
print("summary:", dict(summary))
