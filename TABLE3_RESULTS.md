# Table 3 (CT-Prover column): reference reproduction

Paper: Cai, Song, Chen. *Towards Efficient Verification of Constant-Time
Cryptographic Implementations*, FSE 2024, Table 3. How to reproduce:
[`reproduce/README.md`](reproduce/README.md).

Configuration of this reference run (2026-09-13, 18:59:44–19:30:06 −04:00):

- this repository (upstream `0629dda` + fixes listed in `reproduce/README.md`),
  including the **bam-5 alignment fix**
- `python3 reproduce/run_table3.py --wall 7200 --heap 0x4000000000`, all
  benchmark directories in parallel, on an Intel Xeon Platinum 8360H with
  503 GiB RAM running Ubuntu 22.04.5
- Boogie 2.9.6 `/doModSetAnalysis /errorLimit 0 /timeLimit 3600`, Z3 4.8.12
- manual cutoff at 1821 s after launch, once all 11 rows that finish in the paper
  had finished. The remaining 4 rows (the paper's TO rows) were stopped and are
  reported as TO. The paper's TO is 6 h.
- metrics: `python3 reproduce/derive_table3.py bech <logdir>`
  (`a = 1+product1`, `b = a+product2` from the driver CSV; `x` = Phasar taint
  positions; `y`/`z` = distinct C `file:line` of failing assertions in the final
  Boogie round of step 2/3)

| ID | a:b ours (s) | a:b paper (s) | rel a | rel b | x:y:z ours | x:y:z paper | status |
|---|---|---|---|---|---|---|---|
| P4_3 | 25.68:56.74 | 24.05:50.84 | +6.8% | +11.6% | 49:49:49 | 49:48:48 | ok |
| P4_4 | 21.64:48.92 | 21.03:44.76 | +2.9% | +9.3% | 49:49:49 | 49:48:48 | ok |
| P5_1 | TO:TO | TO:TO | n/a | n/a | 0:–:– | 48:–:– | step 2 TO (stopped at cutoff) |
| P5_11 | 14.55:32.92 | 14.10:30.68 | +3.2% | +7.3% | 16:3:3 | 26:16:16 | ok |
| P6_1 | 8.30:18.13 | 9.36:19.27 | −11.4% | −5.9% | 1:1:1 | 12:1:1 | ok |
| P6_2 | 7.47:15.69 | 8.48:17.24 | −11.9% | −9.0% | 1:1:1 | 12:1:1 | ok |
| P6_5 | 1073.00:TO | 983.86:TO | +9.1% | n/a | 89:71:– | 107:71:50 | step 3 TO (stopped at cutoff) |
| P6_13 | 7.84:17.18 | 8.85:17.87 | −11.4% | −3.9% | 4:4:4 | 6:4:4 | ok |
| P6_14 | 12.91:27.56 | 13.06:26.57 | −1.2% | +3.7% | 32:33:33 | 32:32:32 | ok |
| P6_15 | 12.31:26.35 | 13.06:26.35 | −5.7% | +0.0% | 32:33:33 | 32:32:32 | ok |
| P6_16 | TO:TO | 2561.81:TO | n/a | n/a | 116:–:– | 107:71:53 | step 2 TO (stopped at cutoff) |
| P6_17 | 9.37:20.48 | 9.75:20.31 | −3.9% | +0.8% | 9:8:8 | 11:8:8 | ok |
| P6_18 | 8.99:20.09 | 9.77:20.12 | −8.0% | −0.2% | 9:8:8 | 13:8:8 | ok |
| P6_19 | TO:TO | 3515.77:TO | n/a | n/a | 121:–:– | 142:70:39 | step 2 TO (stopped at cutoff) |
| P6_27 | 133.31:550.87 | 131.34:503.23 | +1.5% | +9.5% | 53:45:45 | 177:45:45 | ok |


P6_5 `a` is log-derived (the driver writes its CSV only when a directory finishes);
on the 11 finished rows the log value equals the CSV value within 0.2 s.
P6_5 had been in its first step-3 Boogie call for 738 s when stopped.

## Effect of the bam-5 fix (same counter, earlier run without the fix)

| ID | run 1 a:b | run 1 x:y:z | run 2 a:b | run 2 x:y:z | paper |
|---|---|---|---|---|---|
| P6_5 | 1094.07:**1471.89** | 89:71:29 | 1073.00:TO | 89:71:– | 983.86:TO / 107:71:50 |
| P6_16 | 2858.25:**4258.19** | 116:72:31 | TO:TO | 116:–:– | 2561.81:TO / 107:71:53 |
| P6_17 | 8.58:17.74 | 9:8:**7** | 9.37:20.48 | 9:8:8 | 9.75:20.31 / 11:8:8 |
| P6_18 | 8.36:17.55 | 9:8:**7** | 8.99:20.09 | 9:8:8 | 9.77:20.12 / 13:8:8 |


Without the fix, P6_5 and P6_16 falsely finish step 3 (the paper reports TO), and P6_17/P6_18
lose one source in step 3. Rows the bug does not touch have identical `y:z` in both runs.
