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


| File                                      | Change                                                                                                                                                                                                                                                                                                                                                                                       |
| ----------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `script/vfct_analysis/findbuginboogie.py` | `add_split_here()` rewrites every `assert ($nondet ==> e);` in `<stem>-bool-0.bpl` and `<stem>-shadow-0.bpl` to `assert {:split_here} ($nondet ==> e);` before the first Boogie call of step 2 and step 3. The line count does not change, so the mark-by-line transfer from step 2 to step 3 is untouched. Enabled by `CT_SPLIT_HERE=1` (default off). `CT_VCS_CORES=n` adds `/vcsCores:n`. |
| `script/vfct_analysis/vfct_find_bug.py`   | `taint_override()`: with `CT_TAINT_DIR=<dir>`, the step 1 outputs `<stem>-t.ll` and `<stem>-taintres.txt` are replaced by the copies in `<dir>` after Phasar has run.                                                                                                                                                                                                                        |
| `reproduce/run_table3.py`                 | `--split-here`, `--vcs-cores n`, `--taint-dir DIR:PATH`. The manifest and each log header record the settings.                                                                                                                                                                                                                                                                               |


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


| Run   | Command                                                                                                                                                                                                                                                                           | Cap                                |
| ----- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ---------------------------------- |
| split | `python3 reproduce/run_table3.py --only Mbed-tls/RSA BearSSL/RSA_i15 BearSSL/RSA_i15_pkcs1 BearSSL/RSA_i31_pkcs1 --wall 21600 --heap 0x4000000000 --vcs-cores 16 --split-here --taint-dir Mbed-tls/RSA:bech/Mbed-tls/RSA/authors_taint --logdir reproduce/runlogs/isolated-sites` | 6 h per case, the paper's time-out |
| stock | same programs copied to `bech/BearSSL/*_stock`, run with the unmodified driver (`--extra ...` without `--split-here`), `--logdir reproduce/runlogs/isolated-sites-baseline`                                                                                                       | 6 h                                |


The stock run was needed because the earlier reference run (`TABLE3_RESULTS.md`)
stopped the time-out rows by hand at 1821 s, so it has no step 3 numbers for
them. Both runs used Boogie 2.9.6, Z3 4.8.12, `/doModSetAnalysis /errorLimit 0 /timeLimit 3600`, on the same machine at the same time (190 cores, 503 GiB).

## 3. Results



### 3.1 Outcome per case


| ID    | split run                                                                                      | stock run                                                  |
| ----- | ---------------------------------------------------------------------------------------------- | ---------------------------------------------------------- |
| P5_1  | step 2: Boogie `OutOfMemoryException` after 7278 s at the 256 GiB heap cap, before any Z3 call | not run (the same Boogie blow-up, see `TABLE3_RESULTS.md`) |
| P6_5  | step 2 done in 1525 s; step 3 killed at the 6 h cap in round 4                                 | step 2 done in 1309 s; step 3 killed at the cap in round 8 |
| P6_16 | step 2 done in 18698 s; step 3 killed at the cap in round 0                                    | step 2 done in 3236 s; step 3 killed at the cap in round 5 |
| P6_19 | step 2 killed at the cap in round 5                                                            | step 2 done in 4183 s; step 3 killed at the cap in round 4 |


Verdicts: for every round that both runs completed, the set of distinct
failing lines is identical, with one exception. In P6_5 step 3 round 2 the stock
run reports the leak assertion at `decrypt-shadow-2.bpl:4004` and the split run
does not. Both report it in round 3. See 3.4 for why.

### 3.2 Boogie time per round (seconds)

Each entry is one Boogie call. The driver repeats a call after commenting out
the loop invariants that failed, until none fails (rounds). Step 2 is the bool
product, step 3 the shadow product.

P6_5 (`BearSSL/RSA_i15`):


|              | round 0 | 1    | 2    | 3    | 4             | 5    | 6    | 7    | 8             |
| ------------ | ------- | ---- | ---- | ---- | ------------- | ---- | ---- | ---- | ------------- |
| step 2 split | 163     | 170  | 170  | 167  | 169           | 172  | 164  | 164  | 176           |
| step 2 stock | 109     | 169  | 134  | 136  | 140           | 130  | 173  | 151  | 167           |
| step 3 split | 3747    | 5261 | 3661 | 3798 | killed at cap |      |      |      |               |
| step 3 stock | 3980    | 453  | 1005 | 396  | 4444          | 1238 | 3989 | 4109 | killed at cap |


P6_16 (`BearSSL/RSA_i15_pkcs1`):


|              | round 0       | 1    | 2    | 3    | 4    | 5             | 6   | 7    | 8    |
| ------------ | ------------- | ---- | ---- | ---- | ---- | ------------- | --- | ---- | ---- |
| step 2 split | 4332          | 3669 | 187  | 7747 | 189  | 193           | 186 | 1083 | 1100 |
| step 2 stock | 225           | 295  | 322  | 402  | 390  | 471           | 366 | 340  | 426  |
| step 3 split | killed at cap |      |      |      |      |               |     |      |      |
| step 3 stock | 1076          | 4246 | 1065 | 5416 | 2475 | killed at cap |     |      |      |


P6_19 (`BearSSL/RSA_i31_pkcs1`):


|              | round 0 | 1    | 2    | 3    | 4             | 5             | 6   | 7   | 8   |
| ------------ | ------- | ---- | ---- | ---- | ------------- | ------------- | --- | --- | --- |
| step 2 split | 3767    | 3774 | 226  | 3798 | 6603          | killed at cap |     |     |     |
| step 2 stock | 325     | 465  | 568  | 443  | 394           | 507           | 417 | 685 | 354 |
| step 3 stock | 3816    | 4112 | 4370 | 4362 | killed at cap |               |     |     |     |


So the stock tool also fails all three BearSSL cases within 6 h on this machine,
in step 3, as the paper reports. Its step 3 rounds alternate between a few
hundred seconds and about 4000 s; the split run's step 3 rounds are all above
3600 s.

### 3.3 Where the time goes: P6_19 step 2 round 0, traced

A side run of the same `sign-bool-0.bpl` with `/trace /vcsDumpSplits` gives
per-piece numbers (`reproduce/isolated-sites-pieces/p6_19-step2-round0-limit3600.csv`, one row per
piece: program-order number, finish order, Z3 seconds, verdict, inlined
procedure instance, checked variable, bool file line, C site).

- 1300 pieces. 1297 finish with median 0.12 s, 90th percentile 1.0 s, maximum
23 s, 838 s of Z3 time in total. 1011 are valid and 286 invalid; the invalid
set equals the stock run's error set.
- Boogie hands pieces to the 16 Z3 workers in program order and the finish
order tracks it: piece 100 finished 98th, piece 900 finished 893rd, mean
displacement 7 places. Early sites are indeed verified early.
- 3 pieces hit the 3600 s limit: numbers 191, 324 and 820, that is 15%, 25% and
63% through the program. They check `$i6.dup == 0` in `br_i31_sub` call 25
(`i31_sub.c:37`), `$i6.dup == 0` in `br_i31_add` call 11 (`i31_add.c:36`) and
`$p22.dup == 0` in `br_i31_muladd_small` call 5 (`i31_muladd.c:83`, bool line
3546). (The first version of this paragraph named the next piece in each
case, add calls 7 and 5 and sub call 27, because of the off-by-one in the
dump numbering explained in 3.6; corrected 2026-10-14.) The stock single VC
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

### 3.6 Which assertion hits the limit, per round (revised 2026-10-12)

This section replaces the first version of 3.6 (2026-10-09), whose assertion
names were off by one piece: Boogie numbers the dumped pieces from 0 and the
trace from 1, so dump file k holds trace piece k+1. The corrected mapping is
confirmed two ways: on a toy program, and by the fact that the "Invalid at the
limit" piece of P6_5 step 3 round 0 (trace piece 475) has its assertion, shadow
line 9215, in the error report of the original run, while the line named
before (9240, the next piece) does not appear there.

Method. Every round of the split run that took about 3600 s or more was rerun
on the same file with `/trace /vcsCores:8 /timeLimit 1800` and the pieces
dumped, so that each piece's finish time and verdict are visible and a piece
that reaches the limit can be read off. The P6_5 files survived; the P6_16 and
P6_19 round files were rebuilt from the surviving bam outputs and the saved
Boogie reports (the rebuild is byte-identical to the originals where those
survive). Per-piece tables: `reproduce/isolated-sites-pieces/`.

Two caveats found on the way:

- `/vcsDumpSplits` changes Boogie's behaviour in later rounds. With dumping,
  P6_16 step 2 round 1 finished in 271 s with no piece near the limit and 345
  errors; without dumping the same file has one piece at the limit and 523
  errors, as in the original run. So for rounds where the dumped run showed no
  stall, the stalled piece was taken from a no-dump rerun and its assertion
  read from the dump of the same round, which has the same piece count and
  order.
- Two kinds of limit hits. A piece reported as "TimeOut" is silently absent
  from the error report. A piece reported as "Invalid" at exactly the limit is
  listed in the error report as "might not hold". Both are marked below.

**Stock run.** No round of the stock run recorded a time-out: every report
ends with "N errors" and no "time outs" count. A stock round of about 4000 s
is one query whose error loop takes that long as a whole, and Boogie gives no
per-assertion time inside it. The per-assertion attribution therefore exists
only for the split pieces.

**Split run, rounds of about 3600 s or more.** "piece k/N" is the position in
program order; the assertion is given as the variable checked, the inlined
call instance, the C site, and the line in the round's Boogie file where known.

| case, round | original time | pieces at the limit | assertion |
|---|---|---|---|
| P5_1 step 2 r0 | 7278 s, OOM | none reached | Boogie ran out of memory building the VC; no piece was ever sent to Z3 |
| P6_5 step 3 r0 | 3747 s | 475/765, Invalid at limit | `$i24 == $i24.shadow`, loop variable `u` of the loop at `i15_muladd.c:147`, `br_i15_muladd_small` call 4, shadow line 9215 |
| P6_5 step 3 r1 | 5261 s | 298/765 TimeOut (4979 s under the 1800 s limit); 312/765 TimeOut | `$i10` equality at `i15_montmul.c:39`, `br_i15_montymul` call 3, line 7454; `$i8` equality (loop variable) at `i15_sub.c:36`, `br_i15_sub` call 18, line 6646 |
| P6_5 step 3 r2 | 3661 s | 146/765 TimeOut | `$i14` equality at `i15_mulacc.c:45`, `br_i15_mulacc` call 1, line 3776 (plus two pieces of 1057 s and 575 s in `montymul` call 5 and `muladd_small` call 11 that did finish) |
| P6_5 step 3 r3 | 3798 s | 358/765 TimeOut | `$i16` equality at `i15_montmul.c:39`, `br_i15_montymul` call 4, line 7475 |
| P6_5 step 3 r4 | killed at cap | not traced | no attribution; the round's file survives in the split run outputs, so a trace run would give it |
| P6_16 step 2 r0 | 4332 s | 203/1290, Invalid at limit (4248 s under the 1800 s limit) | `$i18.dup == 0`: the taint of `k = mblen - 1`, checked as the argument of `br_i15_decode(x, buf, k)` at `i15_decred.c:71`, `br_i15_decode_reduce` call 2 |
| P6_16 step 2 r1 | 3669 s | 201/1290 TimeOut (no-dump rerun; outputs not kept, see the note below) | the pointer taint check before the `memset` in `br_i15_zero` call 2, `inner.h:1540` (the zeroing of `x` in `decode_reduce`); in the dumped form the assertion is already `0 == 0`, so the time is spent on the prefix, not on the goal |
| P6_16 step 2 r3 | 7747 s | 765/1290 TimeOut (1901 s) | `$i23.dup == 0`, loop variable at `i15_muladd.c:147` on the loop back edge, `br_i15_muladd_small` call 6 |
| P6_16 step 3 r0 | killed at cap | 286/770, Invalid at limit (rebuilt file, 2163 s with 8 workers) | `$i17 == $i17.shadow` at `i15_reduce.c:50`, `br_i15_reduce` call 0 |
| P6_19 step 2 r0 | 3767 s | 191/1300 TimeOut; 324/1300 Invalid at limit; 820/1300 TimeOut | `$i6.dup == 0` at `i31_sub.c:37`, `br_i31_sub` call 25; `$i6.dup == 0` at `i31_add.c:36`, `br_i31_add` call 11; `$p22.dup == 0` at `i31_muladd.c:83`, `br_i31_muladd_small` call 5, line 3546 |
| P6_19 step 2 r1 | 3774 s | 782/1300 (no-dump rerun; outputs not kept) | `$i19.dup == 0`, loop variable on the back edge of the loop at `i31_muladd.c:128`, `br_i31_muladd_small` call 6 |
| P6_19 step 2 r3 | 3798 s | 408/1300 and 1071/1300 (no-dump rerun; outputs not kept) | loop-variable taint on the back edge at `i31_add.c:36`, `br_i31_add` call 10; `$p3.dup == 0` at `i31_sub.c:36`, `br_i31_sub` call 11 |
| P6_19 step 2 r4 | 6603 s | 704/1300 TimeOut (2327 s under the 1800 s limit; no-dump rerun, outputs not kept) | `$i10.dup == 0` at `i31_montmul.c:76`, `br_i31_montymul` call 5 |
| P6_19 step 2 r5 | killed at cap | not traced | no attribution; same as P6_5 r4 |
| P6_19 step 3 r0 | never reached in the split run; file rebuilt from the stock marks | 12 pieces at the limit (4135 s with 8 workers) | equality checks at `i31_reduce.c:62` (call 0, `$p35`), `i31_muladd.c:91/97/128` (call 10: `$p46`, `$p68`, `$p73`, `$i20`), `i31_sub.c:37` (calls 27, 22, 14: `$i7`), `i31_add.c:36` (calls 12 and 4: `$i7`), `i31_muladd.c:43/91` (call 8: `$i5`, `$p41`) |

What is backed by a kept file, and what is not (checked 2026-10-14 against
the tables in `reproduce/isolated-sites-pieces/`, without rerunning anything):

- Backed by a per-piece table: P6_5 step 3 r0 to r3, P6_16 step 2 r0 and r3,
  P6_16 step 3 r0, P6_19 step 2 r0 and P6_19 step 3 r0. For each of these the
  piece number, helper, call instance, variable, C site and verdict above
  were read back from the table.
- Not backed by a kept file: P6_16 step 2 r1 and P6_19 step 2 r1, r3 and r4.
  Their attribution came from no-dump reruns whose Boogie output was not
  saved, so these four rows cannot be checked from the repository. Rerunning
  those rounds with `/trace` (about one hour each) would settle them.
- No attribution at all: the rounds killed at the 6 h cap (P6_5 step 3 r4,
  P6_19 step 2 r5), and every stock round. The stock rounds of about 4000 s
  (P6_5 step 3 r0, r4, r6, r7; P6_16 step 3 r1, r3; P6_19 step 3 r0 to r3)
  are single queries that end with `0 verified, N errors` and no time-out
  count, so Boogie gives no per-assertion time for them. The only way to get
  it is the split form, which is what the rows above are.
- "At the limit" means the piece stalled, not that it stopped at the limit:
  Z3's limit is soft, and the stalled pieces ran 4248 s, 4979 s and 2387 s
  under an 1800 s setting (P6_16 step 2 r0, P6_5 step 3 r1, P6_19 step 3 r0).
- The tables of P6_5 step 3 r1 and r2 carry one piece (number 2) as
  `NOT_DONE`: its trace line was not matched when the table was built. In
  rounds 0 and 3 the same piece is a trivial `Valid` (the `i8` equality in
  `br_i15_decode` call 1), so it is not a hidden stall.

What the list says. Every limit piece is a check on a loop index, a pointer
into a limb array, or a length derived from the modulus header, inside an
inlined bignum helper (`add`, `sub`, `mulacc`, `montymul`, `muladd_small`,
`reduce`, `decode_reduce`, `zero`). The instance changes from round to round:
removing the invariants that failed in one round moves the stall to a
different call of the same helpers, not to the same assertion. P6_19's step 3
has 12 such pieces in its first round alone. A fix therefore has to treat the
class of obligations, not one site, which is what the three next steps in
4.2 are aimed at.

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



## 4.1 Perspective one: what each piece asks the solver

Every piece is a question to Z3: "is there an execution of the code before
this site in which the check fails?" Z3 answers either "yes, here is one" (a
counterexample; the driver prints "might not hold") or "no" (a proof). The cost
depends on which answer is true and on how much of the program the answer
rests on. Three kinds of pieces occur.

**Kind 1, leak sites: the answer is yes.** Example: `assert $nondet ==> $i13.dup == 0` in `montymul`, where `$i13` is a loop index taken from the secret
exponent. A taint bit of 1 can reach it, so Z3 looks for one execution, finds
it and stops. Finding one execution is cheap even when the prefix is long,
because Z3 may pick values freely for everything that is not on the way. About
290 pieces per case; they are the errors in the report.

**Kind 2, easy proofs: the answer is no, for a local reason.** Example: `assert $nondet ==> $p46.dup == 0` in `sig_pad`, where `$p46` is the public buffer
pointer plus a constant, so its taint bit is `0 | 0`. Or a check on a loop
variable for which bam has put `assert {:shadow_invariant} $i24.dup == 0` at
the loop head, which Boogie assumes at the top of every iteration. The
negation contradicts a fact one or two steps away and Z3 never has to look at
the rest of the prefix. About 1000 pieces per case, a tenth of a second each.

**Kind 3, hard proofs: the answer is no, for a global reason.** Take the guard
`u <= mlen` at `i15_muladd.c:147`. The product asks whether `mlen` and its
shadow copy are equal in the two runs. `mlen` comes from `m[0]`, and `m[0]` is
a load from memory. In SMACK's encoding memory is one map, and the value of
`m[0]` here is "the map after every store since the program started, read at
address m". To prove that the two runs agree, Z3 has to show that none of the
hundreds of earlier stores, in either run, made that cell differ. Stores made
by `memcpy` and `memset` are described by quantified axioms, which Z3 can only
use by guessing instantiations. Loops in between are not unrolled: Boogie cuts
them, havocs what they modify and assumes the loop invariants, so the proof
also has to pick the right invariant at the right loop head and connect it to
this cell. The negation of the check is consistent with everything local, so
Z3 is forced into case splits over the whole chain. That is why one such piece
runs for an hour while its neighbours take a tenth of a second. The position in
the program is incidental: this is simply the first place where a bound derived
from the modulus header is used. The stalled site of P6_16, the loop start
`k = mblen - 1` at `i15_decred.c:78`, is the same situation.

Two more facts shape what is worth optimising:

- In round 0 the hard proof succeeds only because of a loop invariant that
Boogie assumes. The same round reports that invariant as failing elsewhere.
The driver comments it out and reruns, and in round 1 the hard check is a
kind 1 piece: a counterexample exists and is found in seconds.
- The driver keeps only the invariant failures of the intermediate rounds and
the assertion verdicts of the final round. Every assertion proof done in a
non-final round is thrown away. The hard proofs that cost P6_16 three rounds
of one to two hours each were all discarded.

The levers this perspective gives:

- **Do not prove assertions in intermediate rounds.** Run the rounds with the
leak asserts disabled until the set of loop invariants is stable, then check
the sites once. Invariant failures do not depend on the leak asserts, because
`$nondet` makes a leak assert contribute nothing as an assumption. This
removes the discarded work from both the split and the stock pipeline, and in
the observed cases the hard obligations have turned into cheap leaks by the
time the final round runs. A driver change only.
- **Give the solver the global fact as a local one.** The hard proof needs
"the modulus header is public". Stating it once, as a precondition on the
memory cell for the bignum helpers or as an invariant at the loop that reads
it, turns a kind 3 piece into a kind 2 piece. bam already emits
`requires x == x.shadow` for untainted scalar arguments; what is missing is
the same statement for the memory cell behind a pointer argument.
- **Weaken the memory axioms for the proof.** The quantified `memcpy` and
`memset` models are the expensive part of the chain. A bounded or summarised
version for the specific copies that write the modulus removes most of the
instantiation work.

Not pursued: slicing the prefix of the hard pieces (already tried in the
earlier site-slicing work) and keeping the hard obligations together in one
query (a query that contains a too-hard piece takes the time of that piece
whatever else is in it).

## 4.2 Perspective two: three parts of the product that make the hard question hard

Perspective one looks at the question. This one looks at the formula the
question is asked over. Three parts of it are responsible for most of the
work.

**Inlined procedures.** `{:inline 1}` pastes every callee into its caller, and
that compounds down the call graph: P6_5's product has 84 procedures and 1,155
call statements, P5_1's has 116 and 1,697, and after inlining P5_1 is so large
that Boogie runs out of memory before it asks Z3 anything. A procedure in the
prefix of a piece can be treated in three ways, and each is a different proof.

- *Remove it* when the piece does not depend on it: no remaining check sits
inside it, nothing it writes (return values, the memory maps, the error flag,
their `.dup` and `.shadow` copies) is read on the way to the check, and it
decides no branch or index on that way. This is a dependence slice. Boogie's
pieces already remove everything after the check, and the hard pieces stall
with that done, so what is left to remove is prefix code the proof does not
use. Slicing has been tried; not pursued further.
- *Summarize it* when the caller uses only a few facts about it. The body is
checked once against a contract; every call then havocs what the body may
write and assumes the contract. The contract must list everything the body
writes (a missing map or flag makes the caller treat it as unchanged), must
say that the outputs the caller still reads agree across the two runs when
the inputs agree, and must say how the taint of a tainted output depends on
the inputs, otherwise a later branch on that output is nondeterministic and
the sink fails even if the code is constant-time. It need not carry the limb
products, the loop index or the numeric result; those are the bulk of the
body. The hard proofs found here need only one such fact, "the modulus header
is public", at the entry of the bignum helpers. That one-line contract is the
first thing to test. Full summaries, with frames over SMACK's maps, are the
quantified `ensures` cost the earlier design note warned about; they come
after, and they are also the only route that shrinks P5_1's VC.
- *Keep it* when a check sits inside it, or when the fact the caller needs
holds only at this call. The kept bodies are where the next two parts live.

**Multiplications in a kept body.** On the whole step 3 query of P6_5,
abstracting the multiplications of two variables removed about 74% of Z3's
decisions, `montymul` alone 68%. Inlining multiplies that cost by the number of
kept copies. The abstraction that is safe for constant time: replace `x * y` by
an uninterpreted function `f(x, y)`. `f` still gives equal results for equal
inputs, which is all an equality or taint check ever needs; it loses only
arithmetic facts such as carry bounds, which belong to functional correctness,
not to constant time. The products have few such sites (23 in P6_5, 10 in P5_1;
multiplications by a constant stay as they are, so pointer arithmetic is
untouched), and the rewrite is a text change. Two cautions: the percentages
were measured on a query that returned `unknown`, not on the pieces that stall,
so the first test is on the dumped stalled pieces; and a counterexample found
under the abstraction may be spurious and has to be replayed on the original
product. Not pursued: moving to bit-vectors (bit-vector mode crashes bam-7, and
a bit-blasted 32-bit multiplier is not cheaper for Z3), and "compute the
product once for both runs", which the uninterpreted function already gives.

**One memory map for every bignum and both runs.** In BearSSL's products the
headers and limbs of every bignum live in one map, `$M.0`; Mbed TLS's P5_1 has
`$M.0` and `$M.1`. Step 2 and step 3 duplicate the map (`.dup`, `.shadow`). A
store is a case split over addresses, a summary whose frame is the whole map
havocs every limb, and `memcpy`/`memset` on the map are quantified axioms
(about 9% of decisions on P6_5).

- Separate maps per bignum object would let a summary havoc only what it
writes. It needs a pointer analysis that tells bignums apart, which the
current one does not, and it pays off only once summaries exist. Not now.
- When the length of a copy is public, the copy is a finite list of updates
instead of a quantified axiom. A secret length cannot be fixed; it is itself
a leak. This is the third lever of perspective one, modest in size, kept.
- Dropping the shadow map after a resynchronization is not sound: the two runs
differ in the secret limbs by construction, so the maps never agree as a
whole. bam-991's per-variable resets are the sound form of this idea and are
already in place.



## 4.3 What to try next, in order

1. **Uninterpreted multiplication of two variables**, tested on the dumped
  stalled pieces with a 30 minute limit.
2. **The one-fact contract**: `m[0]` equal across the runs and untainted at the
  entry of the bignum helpers, tested the same way by adding the assumption at
   the top of a stalled piece.
3. **Invariant-first rounds** in the driver, which removes the discarded proofs
  whatever the solver outcome.
4. **Bounded copies for public lengths**, if the remaining hard pieces still
  spend their time in quantifier instantiation.

Summaries proper come after item 2 shows whether a local fact is enough. P5_1
stays blocked on Boogie memory until the inlined body count drops, which only
the summary route addresses.

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
- `reproduce/isolated-sites-pieces/`: the per-piece tables of 3.3 and 3.6.

