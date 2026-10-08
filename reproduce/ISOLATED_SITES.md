# Isolated sites: one leak assert per VC piece (`{:split_here}`)

Branch `isolated-sites`. Run on 2026-10-08. Question: do the four Table 3
time-outs (P5_1, P6_5, P6_16, P6_19) finish when Boogie proves one leak
assertion at a time instead of all of them in one verification condition?

Short answer: no. Every round that contains at least one hard assertion costs
at least the per-query limit, the hard assertions are the same ones the single
VC proves in minutes, and P5_1 fails inside Boogie before any assertion is sent
to Z3. Details below.

## 1. What was changed

No bam or SMACK change. Three scripts:

| File | Change |
|---|---|
| `script/vfct_analysis/findbuginboogie.py` | `add_split_here()` rewrites every `assert ($nondet ==> e);` in `<stem>-bool-0.bpl` and `<stem>-shadow-0.bpl` to `assert {:split_here} ($nondet ==> e);` before the first Boogie call of step 2 and step 3. The line count does not change, so the mark-by-line transfer from step 2 to step 3 is untouched. Enabled by `CT_SPLIT_HERE=1` (default off). `CT_VCS_CORES=n` adds `/vcsCores:n`. |
| `script/vfct_analysis/vfct_find_bug.py` | `taint_override()`: with `CT_TAINT_DIR=<dir>`, the step 1 outputs `<stem>-t.ll` and `<stem>-taintres.txt` are replaced by the copies in `<dir>` after Phasar has run. |
| `reproduce/run_table3.py` | `--split-here`, `--vcs-cores n`, `--taint-dir DIR:PATH`. The manifest and each log header record the settings. |

`bech/Mbed-tls/RSA/authors_taint/` holds the authors' shipped step 1 result for
P5_1 (48 taint positions), extracted from upstream commit `0629dda`. This
machine's Phasar build finds 0 positions on the same bitcode, so P5_1 was run on
the authors' file.

Boogie 2.9.6 semantics of `{:split_here}`, checked on a toy program and on the
dumped pieces (`/vcsDumpSplits`): one VC piece per marked assertion, the marked
assertion is checked, every earlier assertion becomes an assumption, the code
after the piece's assertion is dropped, error lines keep the original line
numbers, and the attribute survives inlining. A marker inside an inlined
procedure gives one piece per inlined call, so P6_19's 313 markers become 1300
pieces.

## 2. Runs

| Run | Command | Cap |
|---|---|---|
| split | `python3 reproduce/run_table3.py --only Mbed-tls/RSA BearSSL/RSA_i15 BearSSL/RSA_i15_pkcs1 BearSSL/RSA_i31_pkcs1 --wall 21600 --heap 0x4000000000 --vcs-cores 16 --split-here --taint-dir Mbed-tls/RSA:bech/Mbed-tls/RSA/authors_taint --logdir reproduce/runlogs/isolated-sites` | 6 h per case, the paper's time-out |
| stock | same programs copied to `bech/BearSSL/*_stock`, run with the unmodified driver (`--extra ... ` without `--split-here`), `--logdir reproduce/runlogs/isolated-sites-baseline` | 6 h |

The stock run was needed because the earlier reference run (`TABLE3_RESULTS.md`)
stopped the time-out rows by hand at 1821 s, so it has no step 3 numbers for
them. Both runs used Boogie 2.9.6, Z3 4.8.12, `/doModSetAnalysis /errorLimit 0
/timeLimit 3600`, on the same machine at the same time (190 cores, 503 GiB).

## 3. Results

### 3.1 Outcome per case

| ID | split run | stock run |
|---|---|---|
| P5_1 | step 2: Boogie `OutOfMemoryException` after 7278 s at the 256 GiB heap cap, before any Z3 call | not run (the same Boogie blow-up, see `TABLE3_RESULTS.md`) |
| P6_5 | step 2 done in 1525 s; step 3 killed at the 6 h cap in round 4 | step 2 done in 1309 s; step 3 killed at the cap in round 8 |
| P6_16 | step 2 done in 18698 s; step 3 killed at the cap in round 0 | step 2 done in 3236 s; step 3 killed at the cap in round 5 |
| P6_19 | step 2 killed at the cap in round 5 | step 2 done in 4183 s; step 3 killed at the cap in round 4 |

Verdicts: for every round that both runs completed, the set of distinct
failing lines is identical, with one exception. In P6_5 step 3 round 2 the stock
run reports the leak assertion at `decrypt-shadow-2.bpl:4004` and the split run
does not. Both report it in round 3. See 3.4 for why.

### 3.2 Boogie time per round (seconds)

Each entry is one Boogie call. The driver repeats a call after commenting out
the loop invariants that failed, until none fails (rounds). Step 2 is the bool
product, step 3 the shadow product.

P6_5 (`BearSSL/RSA_i15`):

| | round 0 | 1 | 2 | 3 | 4 | 5 | 6 | 7 | 8 |
|---|---|---|---|---|---|---|---|---|---|
| step 2 split | 163 | 170 | 170 | 167 | 169 | 172 | 164 | 164 | 176 |
| step 2 stock | 109 | 169 | 134 | 136 | 140 | 130 | 173 | 151 | 167 |
| step 3 split | 3747 | 5261 | 3661 | 3798 | killed at cap | | | | |
| step 3 stock | 3980 | 453 | 1005 | 396 | 4444 | 1238 | 3989 | 4109 | killed at cap |

P6_16 (`BearSSL/RSA_i15_pkcs1`):

| | round 0 | 1 | 2 | 3 | 4 | 5 | 6 | 7 | 8 |
|---|---|---|---|---|---|---|---|---|---|
| step 2 split | 4332 | 3669 | 187 | 7747 | 189 | 193 | 186 | 1083 | 1100 |
| step 2 stock | 225 | 295 | 322 | 402 | 390 | 471 | 366 | 340 | 426 |
| step 3 split | killed at cap | | | | | | | | |
| step 3 stock | 1076 | 4246 | 1065 | 5416 | 2475 | killed at cap | | | |

P6_19 (`BearSSL/RSA_i31_pkcs1`):

| | round 0 | 1 | 2 | 3 | 4 | 5 | 6 | 7 | 8 |
|---|---|---|---|---|---|---|---|---|---|
| step 2 split | 3767 | 3774 | 226 | 3798 | 6603 | killed at cap | | | |
| step 2 stock | 325 | 465 | 568 | 443 | 394 | 507 | 417 | 685 | 354 |
| step 3 stock | 3816 | 4112 | 4370 | 4362 | killed at cap | | | | |

So the stock tool also fails all three BearSSL cases within 6 h on this machine,
in step 3, as the paper reports. Its step 3 rounds alternate between a few
hundred seconds and about 4000 s; the split run's step 3 rounds are all above
3600 s.

### 3.3 Where the time goes: P6_19 step 2 round 0, traced

A side run of the same `sign-bool-0.bpl` with `/trace /vcsDumpSplits` gives
per-piece numbers (`reproduce/isolated-sites-p6_19-pieces.csv`, one row per
piece: program-order number, finish order, Z3 seconds, verdict, inlined
procedure instance, checked variable, bool file line, C site).

- 1300 pieces. 1297 finish with median 0.12 s, 90th percentile 1.0 s, maximum
  23 s, 838 s of Z3 time in total. 1011 are valid and 286 invalid; the invalid
  set equals the stock run's error set.
- Boogie hands pieces to the 16 Z3 workers in program order and the finish
  order tracks it: piece 100 finished 98th, piece 900 finished 893rd, mean
  displacement 7 places. Early sites are indeed verified early.
- 3 pieces hit the 3600 s limit: numbers 191, 324 and 820, that is 15%, 25% and
  63% through the program. They check `$i10.dup == 0` in `br_i31_add` inlined
  calls 7 and 5 (`i31_add.c:36`, bool line 1765) and `$p3.dup == 0` in
  `br_i31_sub` call 27 (`i31_sub.c:36`, bool line 4548). The stock single VC
  proves these three inside its 325 s round 0. In round 1, after the invariant
  removal, both runs report them as failing.
- Round time is therefore the per-query limit whenever one piece is hard, plus
  the queue: a round with more hard pieces than workers takes several limits
  (P6_16 round 3: 7747 s; P6_19 round 4: 6603 s). In those rounds single Z3
  processes also ran past 3600 s of CPU, so Z3's soft limit is not a bound.

### 3.4 Reporting hazard with split pieces in Boogie 2.9.6

A piece that times out leaves no trace in the report when other pieces have
errors: no error line for its assertion and no `time outs` count in the footer.
The traced run shows `TimeOut` for pieces 191 and 820, and the report of the
main run has neither their lines nor any time-out wording. The assertion looks
verified by omission. The missing line 4004 in P6_5 step 3 round 2 (3.1) is the
same effect in a real round. With the stock single VC a time-out is reported in
the footer.

### 3.5 P5_1

With the authors' 48 sites the bool product has 501 leak asserts. Boogie never
reached Z3: it generated the VC for 7278 s, hit the 256 GiB heap cap and threw
`OutOfMemoryException`. The driver then read the empty report as "no errors",
skipped step 3 and exited with status 0, so without the log the case looks like
a clean pass. Splitting cannot change this, because the cost is Boogie's VC
construction.

## 4. Conclusion

- Option 2 does not remove the time-outs. Step 2 becomes much slower on P6_16
  and P6_19 (18698 s against 3236 s; not finished against 4183 s). On P6_5 step
  3 the first round is roughly equal (3747 s against 3980 s) and the later rounds
  are slower (5261 s against 453 s).
- The verdicts do not change, except that a timed-out piece disappears from the
  report.
- The expensive obligations are a handful of taint checks in the inlined bignum
  helpers, mid-program, which the combined VC proves cheaply and the isolated
  query does not. Why the isolated query is harder is open. One hypothesis is
  that in the single VC Boogie's error loop keeps the same Z3 session across the
  reported errors, so the final proof reuses what was learnt.
- P5_1 needs a smaller VC (or a smaller product) before any splitting matters.

Things this measurement suggests trying next: a per-site file with the suffix
cut and the prefix sliced (option 1 of the earlier survey) for exactly the
hard sites; `/vcsMaxKeepGoingSplits` with a short piece limit to see whether the
hard obligations are hard on every path or only on some; `/rlimit` instead of
`/timeLimit` so that a piece cannot run past its budget.

## 5. Files

- `reproduce/runlogs/isolated-sites/` (not tracked): logs, `manifest.json`,
  `outputs/<bench>/` with every Boogie report and `vrtime-use.txt`,
  `p6_19-step2-round0-trace.out`.
- `reproduce/runlogs/isolated-sites-baseline/`: the stock run, with
  `outputs/<bench>/` reports.
- Note: the raw output directories of the 2026-09-13 reference run for these
  four cases (`one_and_two_and_three.prev.20261008T112932`) were deleted while
  cleaning up after these runs. The reference numbers rest on
  `TABLE3_RESULTS.md` and the logs in `reproduce/runlogs/table3-fixed/`.
- `reproduce/isolated-sites-p6_19-pieces.csv`: the per-piece table of 3.3.
