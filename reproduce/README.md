# Reproducing FSE 2024 Table 3 (CT-Prover column)

This fork (<https://github.com/armanchhetri/CT_Prover>) is
`S3L-official/CT_Prover` @ `0629dda` plus the fixes needed to run the
authors' Table 3 pipeline on a current Linux machine. The main one is a
bam-5 line-alignment bug that silently weakens step 3. See "Changes vs.
upstream" below.

Reference results, and the configuration that produced them, are in
[`../TABLE3_RESULTS.md`](../TABLE3_RESULTS.md).

## 1. Tested platform

Ubuntu 22.04.5 x86-64, gcc 11, Xeon Platinum 8360H, 503 GiB RAM
(`environment/hardware.txt`). Tool versions: `environment/toolchain-run2.txt`.
You need ≥ 300 GiB free RAM only if you run P5_1 to the end. Everything else
needs < 10 GiB per job.

## 2. Two conda environments

Phasar needs LLVM 13. SMACK needs LLVM 12 / clang-12. They cannot share one env.

```bash
conda create -n ctprover   --file reproduce/environment/ctprover-explicit.txt    # LLVM 12, ruby 3.2, python 3.10, dotnet 10, cmake, ninja, boost
conda create -n ctprover13 --file reproduce/environment/ctprover13-explicit.txt  # LLVM 13 (Phasar/SVF build)
```

Two tools are not conda packages:

```bash
conda activate ctprover
# Boogie 2.9.6 as a .NET tool inside the env
dotnet tool install Boogie --version 2.9.6 --tool-path "$CONDA_PREFIX/bin"
# Z3 4.8.12 release binary (also used for the SVF build below)
wget https://github.com/Z3Prover/z3/releases/download/z3-4.8.12/z3-4.8.12-x64-glibc-2.31.zip
unzip z3-4.8.12-x64-glibc-2.31.zip && cp z3-4.8.12-x64-glibc-2.31/bin/z3 "$CONDA_PREFIX/bin/"
```

## 3. Build

```bash
export CT_ROOT=$PWD            # repository root

# 3a. SVF (static library used by Phasar), LLVM 13
conda activate ctprover13
cmake -S Extern_PTA/SVF -B Extern_PTA/SVF/Release-build -G Ninja -DCMAKE_BUILD_TYPE=Release \
      -DCMAKE_C_COMPILER=gcc -DCMAKE_CXX_COMPILER=g++ \
      -DLLVM_DIR="$CONDA_PREFIX/lib/cmake/llvm" -DZ3_DIR=/path/to/z3-4.8.12-x64-glibc-2.31
ninja -C Extern_PTA/SVF/Release-build

# 3b. Phasar (no sudo; installs under phasar/install; uses clang-12 from ctprover to link Boost)
cd phasar && SKIP_CONDA_INSTALL=1 ./bootstrap.sh && cd ..
LD_LIBRARY_PATH=$CONDA_PREFIX/lib phasar/build/tools/phasar-llvm/phasar-llvm -v   # PhASAR v0222

# 3c. SMACK, LLVM 12 (use the Ninja generator)
conda activate ctprover
cmake -S smack -B smack/build -G Ninja -DCMAKE_BUILD_TYPE=Release \
      -DCMAKE_C_COMPILER=/usr/bin/gcc -DCMAKE_CXX_COMPILER=/usr/bin/g++ \
      -DLLVM_DIR="$(llvm-config --cmakedir)" -DBOOST_ROOT="$CONDA_PREFIX"
ninja -C smack/build
```

`Extern_PTA/SVF-example/bin/svf-ex` is shipped prebuilt by the authors.
`smack/share/smack/versions.py` is committed (copy of `smack/bin/versions`).

## 4. Run

Always from env `ctprover`. The runner sets `PATH`, `LD_LIBRARY_PATH` (adds
`ctprover13/lib`), `DOTNET_ROOT`, `DOTNET_ROLL_FORWARD=LatestMajor`, the
Boogie heap cap and `CT_SKIP_BUILDBECH=1`. It also creates `reproduce/bin/*-12`
links for SMACK's suffixed LLVM tool names. If your envs are not under
`~/miniforge3/envs/`, set `CTPROVER_ENV` and edit `CT13_LIB` in `run_table3.py`.

```bash
conda activate ctprover

# smoke test, about 40 s: P6_1 / P6_2
python3 reproduce/run_table3.py --only BearSSL/AES_small --wall 600 --logdir /tmp/smoke
python3 reproduce/derive_table3.py bech /tmp/smoke | grep -E 'ID|P6_(1|2) '

# all 15 Table 3 programs in parallel (the 11 finite rows finish within about 10 min;
# the 4 paper-TO rows run until --wall)
python3 reproduce/run_table3.py --wall 7200 --heap 0x4000000000 --logdir reproduce/runlogs/table3
python3 reproduce/derive_table3.py bech reproduce/runlogs/table3 --csv table3.csv --md table3.md

# sanity check for the bam-5 fix: every row must print "ok"
python3 reproduce/check_mark_alignment.py --all bech
```

The runner moves an existing `bech/<bench>/one_and_two_and_three/` to
`one_and_two_and_three.prev.<timestamp>` before running. Logs carry `[t=elapsed]`
prefixes and a `manifest.json`. On `--wall` expiry the whole process group
(driver, Boogie, Z3) is killed and the row is reported as TO.

Controlled check used in the write-up (Boogie heap 100 vs 256 GiB on P5_1):

```bash
python3 reproduce/run_table3.py --only Mbed-tls/RSA --heap 0x4000000000 \
    --extra Mbed-tls/RSA_heap100:0x1900000000 --wall 3000 --logdir reproduce/runlogs/heap
```

## 5. Metrics (what `derive_table3.py` computes)

- `a` = `1 + product1` and `b = a + product2`, from the authors' driver CSV
  `one_and_two_and_three_detail.csv`. For a row stopped after step 2, `a` comes
  from the timestamped log (it equals the CSV value within 0.2 s on finished rows).
- `x` = `all taint position!` in `<stem>-taintres.txt`.
- `y` / `z` = distinct C `file:line` of `This assertion might not hold` errors in
  the **final** Boogie round of step 2 / step 3. The driver iterates until no
  loop invariant fails, and round 0 is not its result.
- TO = Boogie `/timeLimit 3600` or the wall cap. OOM = Boogie `OutOfMemoryException`.
  The authors' driver records neither; it writes a time anyway.

`src_counter_candidates.py` prints the alternative counters (bpl lines, Boogie
`N errors`, first vs final round) used to choose `y`/`z`.

## 6. Changes vs. upstream `0629dda`

| File(s) | Change | Why |
|---|---|---|
| `bam/bam-5/lib/bpl/transformation/shadowing.rb` | re-enable `add_to_assert` body (`requires (x == x.shadow)`) | **Correctness.** bam-7 emits a `requires` line there and bam-5 did not. `findbuginboogie.trans_bool_to_shadow` applies bool-file line numbers to the bam-5 file, so every extra line shifted the step-3 marks. `bam-991 --process_mark` then turned the unmarked leak checks into `x := x.shadow`. Before the fix, only 48/205 marks hit an assertion on P6_5 (97/206 P6_16, 98/205 P6_19, 0/8 P6_17/18), and P6_5/P6_16 falsely finished step 3. The authors' own shipped `bech/BearSSL/RSA_i15_pkcs1/one_and_two_and_three/sign-tmp.bpl` contains these `requires` lines. |
| `bam/bam-*/lib/bam.rb` | `File.exists?` → `File.exist?` | Ruby 3.2 removed the alias |
| `script/vfct_analysis/{vfct_find_bug,findbuginboogie,findbuginboogie_shadow}.py` | `/home/luwei/...` → `$CT_ROOT`; `CT_SKIP_BUILDBECH=1` skips `compile.sh`; Boogie `/timeLimit 21600` → `3600` | relocatable; keep the shipped `.ll`; time budget |
| `script/geterror_pos_of_boogie_report.py` | 1-arg mode | not on the driver's path (`script/vfct_analysis/` version is used) |
| `phasar/bootstrap.sh`, `phasar/CMakeLists.txt`, `phasar/lib/.../IfdsIde/CMakeLists.txt`, `CallStringCTX.h` | conda/no-sudo build, SVF/Z3 paths relative to the repo, one compile fix | build on this machine |
| `smack/sea-dsa/include/seadsa/CompleteCallGraph.hh` | `#include <set>` | gcc 11 |
| `bech/BearSSL/AES_small/{decrypt,encrypt}.ll` | restored complete bitcode with `*_wrapper` / `*_wrapper_t` | upstream copy lacks the wrappers; Phasar aborts |
| `bech/Mbed-tls/RSA_heap100/` | copy of `Mbed-tls/RSA` inputs | second arm of the heap controlled check |
| `reproduce/` | runner, derivation, alignment checker, env pins | this reproduction |

Bitcode checksums: `environment/benchmark-ll.md5` (`md5sum -c` from the repo root).
In this repository the two AES_small `.ll` files have machine-specific debug-info
directories replaced by `/work/...`. Their MD5 therefore differs from the
reference run's (`ff61941c…`, `1f572185…`). Re-running with the scrubbed files gives
byte-identical `*-taintres.txt`, `*.bpl`, `*-bool-0.bpl`, `*-tmp.bpl`,
`*-shadow-0.bpl` and Boogie reports.

## 7. Known limitations

- The paper's Table 3 time-out is 6 h. The reference run stopped the 4 paper-TO rows
  (P5_1, P6_5, P6_16, P6_19) at 1821 s, so they are reported as "not finished".
- On P5_1 this Phasar build reports 0 taint positions on byte-identical input,
  where the authors' shipped output lists 48. `x` differs from the paper on 11/15 rows.
- The `y:z` counter misses on P5_11 (3 vs 16: Mbed DES macros put many sources on one line).
