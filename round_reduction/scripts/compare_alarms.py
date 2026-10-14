#!/usr/bin/env python3
"""Compare alarm source locations of the one-round step 3 (results/<case>/pruned.txt.gz)
with the final step-2 round and the last finished step-3 round of the unchanged-tool run."""
import gzip
import os
import re

from common import STOCK, bench_dir, ASSERT_ERR

HERE = os.path.join(os.path.dirname(__file__), "..", "results")


def read(path):
    return (gzip.open(path, "rt") if path.endswith(".gz") else open(path)).read()


def locs(report, bpl):
    L = read(bpl).split("\n")
    out = set()
    for n in set(int(x) for x in ASSERT_ERR.findall(read(report))):
        for k in range(n - 1, max(n - 40, 0), -1):
            m = re.search(r'sourceloc "([^"]+)", (\d+)', L[k])
            if m:
                out.add((m.group(1).split("/")[-1], int(m.group(2))))
                break
    return out


for case, od, base, bd, last in [("p6_5", "BearSSL_RSA_i15_stock", "decrypt", "BearSSL/RSA_i15", "shadow7"),
                                 ("p6_16", "BearSSL_RSA_i15_pkcs1_stock", "sign", "BearSSL/RSA_i15_pkcs1", "shadow4")]:
    r = os.path.join(HERE, case)
    pruned = locs(f"{r}/pruned.txt.gz", f"{r}/pruned.bpl.gz")
    step2 = locs(f"{STOCK}/{od}/{base}-bool8.txt", f"{bench_dir(bd)}/{base}-bool-8.bpl")
    step3 = locs(f"{STOCK}/{od}/{base}-{last}.txt", f"{r}/pruned.bpl.gz")
    print(f"{case}: one-round step 3 {len(pruned)} locations, final step 2 {len(step2)}, equal {pruned == step2};"
          f" last finished unchanged step-3 round ({last}) {len(step3)}, subset {step3 <= pruned},"
          f" extra in one-round run {sorted(pruned - step3)}")
