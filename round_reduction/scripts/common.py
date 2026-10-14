"""Shared paths and parsers for the round reduction analysis.

Inputs are the saved reports of the 6 h unchanged-tool runs of 2026-10-08
(reproduce/runlogs/isolated-sites-baseline/outputs/*_stock) and the round
BPL files left in bech/*/one_and_two_and_three by the isolated-sites run of
the same day. That run only adds {:split_here} to leak asserts, so line
numbers of invariants are the same as in the unchanged-tool files.
"""
import glob
import os
import re

CT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
STOCK = os.path.join(CT_ROOT, "reproduce/runlogs/isolated-sites-baseline/outputs")

# name, stock output dir, file prefix, bench dir
CASES = [
    ("P6_5", "BearSSL_RSA_i15_stock", "decrypt", "BearSSL/RSA_i15"),
    ("P6_16", "BearSSL_RSA_i15_pkcs1_stock", "sign", "BearSSL/RSA_i15_pkcs1"),
    ("P6_19", "BearSSL_RSA_i31_pkcs1_stock", "sign", "BearSSL/RSA_i31_pkcs1"),
]

INV_ERR = re.compile(r'bpl\((\d+),\d+\): Error: This loop invariant might not (hold on entry|be maintained)')
ASSERT_ERR = re.compile(r'bpl\((\d+),\d+\): Error: This assertion might not')
CAND = re.compile(r'\{:(shadow_invariant|likely_shadow_invariant|unlikely_shadow_invariant)')


def bench_dir(bd):
    return os.path.join(CT_ROOT, "bech", bd, "one_and_two_and_three")


def round_reports(outdir, base, step):
    """Reports of one step in round order: <base>-<step>-0.txt, <base>-<step>1.txt, ..."""
    def key(f):
        return 0 if f.endswith("-0.txt") else int(re.findall(r'(\d+)\.txt$', f)[0])
    return sorted(glob.glob(os.path.join(outdir, f"{base}-{step}*.txt")), key=key)


def round_times(outdir):
    return [float(x) for x in open(os.path.join(outdir, "vrtime-use.txt")).read().split()]


def failed_inv_lines(report):
    return set(int(a) for a, _ in INV_ERR.findall(open(report).read()))


def candidates(bpl):
    """line -> (procedure, loop head label, variable, kind) for every invariant candidate."""
    out = {}
    proc = label = None
    for i, l in enumerate(open(bpl).read().split("\n"), 1):
        m = re.match(r'\s*(procedure|implementation)\s+(?:\{[^}]*\}\s*)*([\w.$#]+)', l)
        if m:
            proc, label = m.group(2), None
        m = re.match(r'^\s*\$?([\w.$#]+):\s*$', l)
        if m:
            label = m.group(1)
        m = CAND.search(l)
        if m and "assert" in l:
            var = re.search(r'(\$[\w]+)', l[m.end():]).group(1)
            out[i] = (proc, label, var, m.group(1))
    return out
