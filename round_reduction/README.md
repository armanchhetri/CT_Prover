# Round reduction: fewer Boogie rounds in steps 2 and 3

This directory checks how much of CT-Prover's run time on the Table 3 time-out cases goes to the
repeated Boogie rounds of the invariant loop, and whether predicting the invalid invariants upfront
is worth pursuing. Most of it uses only data from earlier runs. One small test (section 4) ran
Boogie once per case on a modified step-3 file.

Cases: P6_5 (BearSSL RSA_i15), P6_16 (RSA_i15_pkcs1), P6_19 (RSA_i31_pkcs1). P5_1 (Mbed TLS RSA)
is not covered: it runs out of memory inside the first round (7278 s), so it never reaches the
loop described here.

## 1. How the loop works

`script/vfct_analysis/findbuginboogie.py`, function `runtillnoerrloopinv`, runs once for step 2
(bool, taint encoding) and once for step 3 (shadow, relational encoding):

1. Run `boogie /doModSetAnalysis /errorLimit 0 /timeLimit 3600` on `<prefix>-<step>-<k>.bpl`.
2. If the report has any `This loop invariant might not ...` error, `SecondAnalysis.py` comments
   out every reported invariant line, writes `<prefix>-<step>-<k+1>.bpl`, and goes back to 1.
3. When no invariant fails, the assertion failures of that last round are the result.

This is the Houdini algorithm: drop every failed candidate, re-check, repeat until nothing fails.
Assertion results of the earlier rounds are not used.

The candidates come from bam (`bam-7/lib/bpl/transformation/shadowing.rb`, around line 770). For
loop-live variables that later reach a branch or an address it adds `$x.dup == 0` (step 2) or
`$x == $x.shadow` (step 3) at the loop head. It does not use the taint result of step 1.
Value arguments get `unlikely_shadow_invariant`, which is written as `true` and is never checked.

Between the steps, `trans_bool_to_shadow` marks every line in `errorline.txt` (step-2 alarms and
the invariants step 2 dropped), and `bam-991 --process_mark` keeps marked lines as asserts and
turns unmarked invariants into `x := x.shadow`. So the step-3 candidates are exactly the
invariants that step 2 dropped, checked again in the relational encoding.

## 2. Data used

* Per-round Boogie reports of the 6 h runs of the unchanged tool, 2026-10-08:
  `reproduce/runlogs/isolated-sites-baseline/outputs/*_stock/` and the logs next to them.
  None of the three cases finished.
* Round BPL files in `bech/BearSSL/*/one_and_two_and_three/` from the isolated-sites run of the
  same day. That run only adds `{:split_here}` to leak asserts and keeps the line count, so the
  invariant lines match. Every invariant line reported by the unchanged-tool runs falls on an
  invariant line of these files. The step-3 BPL of P6_19 was not kept, so P6_19 is left out
  wherever step-3 lines must be mapped.

## 3. Findings from the saved runs

Full output in `results/`. Times are wall seconds of one Boogie call.

**3.1 Step 2 takes 9 rounds in every case.** Unique invariant lines dropped per round:
16, 10, 7, 5, 3, 2, 1, 1, then 0 (45 in total). All failures except 2 lines are
`might not hold on entry`. Dropping one invariant makes a variable look tainted where the next
loop starts, so that loop's invariant fails in the next round. (`results/rounds_summary.txt`)

**3.2 43 of the 45 dropped invariants come from the bignum header word.** Following the
definitions back, the variable is computed from a load of `x[0]` (the announced bit length) in
all three cases, for example `m = (a[0] + 31) >> 4` in `i15_add.c:35`. The other 2 are length
parameters (`br_i15_decode` and `br_ccopy`). bam only makes candidates for scalar variables, so
no invariant says that the header cell in memory is public.
(`results/invariant_origins_p6_*.txt`)

**3.3 Step 3 repeats step 2.** The 45 step-3 candidates are the 45 step-2 drops. Each one step 3
examined failed again: 40 of 40 in P6_5 and 36 of 36 in P6_16, in the same round order.
When the 6 h limit was reached, 5 (P6_5) and 9 (P6_16) were still not decided.
(`results/step3_vs_step2.txt`)

**3.4 Most alarms appear only after the invariants are dropped.** Unique alarm lines in step 2
grow from 47 in round 0 to 160 in the final round. 111 of the 113 new lines are in procedures
that lost an invariant. All 160 are sent to step 3. (`results/alarm_growth.txt`)

**3.5 Time per case.**

| | P6_5 | P6_16 | P6_19 |
|---|---|---|---|
| Step 2, 9 rounds | 1310 s | 3238 s | 4162 s |
| Step 2, final round only | 167 s | 426 s | 354 s |
| Step 3, finished rounds | 8 rounds, 19616 s | 5 rounds, 14279 s | 4 rounds, 16660 s |
| Step 3 round time range | 396 to 4444 s | 1065 to 5416 s | 3816 to 4370 s |
| State at 6 h | round 8 running for 650 s | round 5 running for 4058 s | round 4 running for 753 s |

The run reached the limit because rounds run one after another. Each round on its own took at most
5416 s.

## 4. Test: step 3 in one round

Method (`scripts/make_pruned.sh`, `scripts/run_one_round.sh`): take the step-3 input
`<prefix>-shadow-0.bpl`, remove the `{:split_here}` marks, comment out the 45 candidate
invariants (line numbers unchanged), and run Boogie once with the same flags and the same 256 GiB
heap limit as the unchanged tool. Run on 2026-10-13, both cases at the same time, with other
jobs on the machine. This file is the one the unchanged loop would reach after its last round if
the undecided candidates also fail.

| | P6_5 | P6_16 |
|---|---|---|
| Time, one round | 1180 s | 3969 s |
| Boogie result | 0 verified, 701 errors | 0 verified, 702 errors |
| Time-outs | none | none |
| Alarm source locations | 71 | 72 |
| Same locations as final step-2 round | yes | yes |
| Last finished unchanged step-3 round | 70 locations (round 7) | 63 locations (round 4) |
| Extra locations in the one-round run | `i15_modpow2.c:141` | `i15_modpow2.c:141`, 7 in `i15_montmul.c`, `inner.h:1539` |

End to end with the unchanged step 2 this is about 2510 s (0.7 h) for P6_5 and about 7230 s
(2.0 h) for P6_16. The unchanged tool did not finish either case in 6 h.

The extra locations come from the 5 and 9 undecided candidates, which the unchanged rounds still
assumed. Every candidate examined so far failed, so these are expected to fail as well, and the
final result of the unchanged tool would then be the same. This could not be confirmed, because
the unchanged tool has not finished these cases. (`results/compare_alarms.txt`)

## 5. Is the direction worth pursuing

Yes.

* The rounds are where the time goes: 17,000 to 21,000 s of the 21,600 s budget in each case.
  Removing them is a change in the driver only, and dropping invariants never hides a leak.
* With one step-3 round, P6_5 and P6_16 finish in about 0.7 h and 2.0 h.
* The cause is specific. One missing fact (the header word `x[0]` is public) explains 43 of 45
  dropped invariants. The same pattern (a length field in memory) exists in other libraries.
* Earlier work on this branch (`reproduce/ISOLATED_SITES.md` section 3.6) found that the stalled
  pieces were proved by the round-0 query within minutes and failed only from round 1 on. Dropped
  invariants make later queries harder as well as more numerous.

Incomplete aspects:

* In these cases the one-round step 3 reports the same alarm locations as step 2. Step 3 removes no
  alarm here, so the run time gain does not by itself improve precision. Better invariants (6.2)
  are needed for that.
* Round times vary widely (396 to 4444 s for P6_5), so the measured one-round times can differ
  between runs.
* P6_19 was not tested (step-3 BPL not kept). P5_1 is not affected.
* Step 2 still takes 9 rounds (1310 to 4162 s).

## 6. Next steps, in order

**6.1 Reuse the step-2 verdicts in step 3.** In `trans_bool_to_shadow`, comment out the
invariants that step 2 dropped instead of marking them. Do not simply leave them unmarked, because
`process_mark` turns unmarked invariants into `x := x.shadow`, which assumes them. Keep the
existing loop as a check. Expected effect: section 4.

**6.2 Better invariants: the header word is public.** Add memory-cell candidates at loop heads
for each bignum base pointer `p`: `$load.i16($M.0.dup, p) == 0` in step 2 and
`$load.i16($M.0, p) == $load.i16($M.0.shadow, p)` in step 3 (`i32` for i31 code). This covers
43 of 45 drops, so step 2 should need 1 or 2 rounds, and most of the 113 extra alarms should not
appear, which also makes each step-3 round smaller. The fact can be assumed in the harness
(BearSSL treats sizes as public, similar to ct-verif's `public_in`) or proved by Houdini, which
needs range candidates such as `u >= 1` for the loop index so that `x[u]` cannot be `x[0]`.
Needs a run to measure.

**6.3 Predict step-2 failures statically.** Failures are taint reaching a loop on entry, so a
forward taint pass over the BPL, or the step-1 taint result, could drop most of them before
Boogie runs. Saves at most 1143, 2812 or 3808 s.

**6.4 Boogie's own Houdini (`/contractInfer` with existential candidates).** Builds the query
once and does not list all 289 to 701 assertion errors in every round. Since the driver does not
use assertion results of the earlier rounds, leak asserts can be turned into assumes during
those rounds without changing the fixed point. Not measured.

**6.5 Refute step-3 candidates with tests.** Run two executions with the same public inputs and
different secrets. If a loop variable differs at the loop head, `x == x.shadow` is false and can
be dropped with no loss of precision. GPUVerify uses fast analyses of this kind to reject
candidates before Houdini.

## 7. Related methods

* Houdini (Flanagan and Leino, FME 2001): the algorithm used here.
* Candidate-based invariant generation in GPUVerify, with fast analyses that reject candidates
  before Houdini (Betts et al., TSE 2017): https://arxiv.org/abs/1612.01198
* ICE learning for incomplete verifiers on top of Boogie (Neider et al., TACAS 2018):
  https://arxiv.org/abs/1712.05581 and Sorcar for conjunctive invariants:
  https://madhu.cs.illinois.edu/Sorcar.pdf
* H-Houdini, hierarchical invariant learning, used for constant-time hardware (Dinesh et al.,
  ASPLOS 2025): https://cwfletcher.github.io/content/research/2025.asplos.hhoudini.paper.pdf
* Ranking LLM-generated invariants to reduce verifier calls (iRank, Chakraborty et al., 2023):
  https://arxiv.org/abs/2310.09342

With about 45 candidates of a simple form, 6.1 and 6.2 address the cost more directly than the
learning methods.

## 8. Files

```
scripts/common.py             paths and report parsers
scripts/rounds_summary.py     per-round times and failures      -> results/rounds_summary.txt
scripts/step3_vs_step2.py     step-3 drops against step-2 drops -> results/step3_vs_step2.txt
scripts/invariant_origins.py  where dropped variables come from -> results/invariant_origins_p6_*.txt
scripts/alarm_growth.py       alarm lines round 0 against final -> results/alarm_growth.txt
scripts/make_pruned.sh        build the one-round step-3 input
scripts/run_one_round.sh      run Boogie once, as the unchanged tool does
scripts/compare_alarms.py     alarm locations of the test       -> results/compare_alarms.txt
results/p6_5, results/p6_16   pruned.bpl.gz, pruned.txt.gz (Boogie report), done.txt (time)
```

The analysis scripts read the saved runs listed in section 2. If those files are moved or the
`bech` output directories are overwritten by a new run, the scripts have to be pointed at copies.

To repeat the test for P6_5:

```
round_reduction/scripts/make_pruned.sh bech/BearSSL/RSA_i15 decrypt /tmp/p6_5
round_reduction/scripts/run_one_round.sh /tmp/p6_5
```
