#!/usr/bin/env python3
"""Run the FSE'24 Table 3 CT-Prover column (15 non-CT programs) in parallel.

Each benchmark directory runs the authors' driver
`script/vfct_analysis/vfct_find_bug.py` (default `runall()` =
`one_and_two_and_three()`, i.e. CT-Prover) in its own process group.

What this wrapper adds (it does not change the analysis):
  * one process per benchmark directory, all started together;
  * a wall-clock cap per directory; on expiry the whole process group
    (python driver, boogie, z3) is killed and the row is reported as TO;
  * every stdout/stderr line of the driver is written to the log with the
    elapsed wall time since the directory started: `[t=   12.345] <line>`;
  * a run manifest (`manifest.json`) with start/end time, exit code,
    timeout flag, environment and git state.

Results are derived afterwards by `derive_table3.py` from the output tree.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import signal
import subprocess
import sys
import threading
import time
from datetime import datetime
from pathlib import Path

def _find_ct_root() -> Path:
    """$CT_ROOT, else the nearest parent of this script that contains bech/ and script/."""
    if os.environ.get("CT_ROOT"):
        return Path(os.environ["CT_ROOT"])
    for p in Path(__file__).resolve().parents:
        if (p / "bech").is_dir() and (p / "script" / "vfct_analysis").is_dir():
            return p
    raise SystemExit("cannot locate the CT_Prover repository; set CT_ROOT")


CT_ROOT = _find_ct_root()
BECH = CT_ROOT / "bech"
CONDA = Path(os.environ.get("CTPROVER_ENV", str(Path.home() / "miniforge3/envs/ctprover")))
CT13_LIB = Path.home() / "miniforge3/envs/ctprover13/lib"

# paper id -> (bench dir, entry stem). Directories with several stems are one job.
CASES = [
    ("P4_3", "Tongsuo/AES", "decrypt"),
    ("P4_4", "Tongsuo/AES", "encrypt"),
    ("P5_1", "Mbed-tls/RSA", "decrypt"),
    ("P5_11", "Mbed-tls/DES", "crypt_cbc"),
    ("P6_1", "BearSSL/AES_small", "decrypt"),
    ("P6_2", "BearSSL/AES_small", "encrypt"),
    ("P6_5", "BearSSL/RSA_i15", "decrypt"),
    ("P6_13", "BearSSL/AES_big_cbc", "key_schedule"),
    ("P6_14", "BearSSL/AES_big_cbc", "decrypt"),
    ("P6_15", "BearSSL/AES_big_cbc", "encrypt"),
    ("P6_16", "BearSSL/RSA_i15_pkcs1", "sign"),
    ("P6_17", "BearSSL/DES_table", "cbc_decrypt"),
    ("P6_18", "BearSSL/DES_table", "cbc_encrypt"),
    ("P6_19", "BearSSL/RSA_i31_pkcs1", "sign"),
    ("P6_27", "BearSSL/RSA_i32", "decrypt"),
]

# SMACK calls LLVM tools with a "-12" suffix; conda ships some unsuffixed.
LLVM12_TOOLS = ["clang", "clang++", "llvm-link", "opt", "llvm-as", "llvm-dis", "llc", "llvm-nm"]


def make_llvm12_shims(bindir: Path) -> None:
    bindir.mkdir(parents=True, exist_ok=True)
    for tool in LLVM12_TOOLS:
        target = CONDA / "bin" / f"{tool}-12"
        if not target.exists():
            target = CONDA / "bin" / tool
        link = bindir / f"{tool}-12"
        if target.exists() and not link.exists():
            link.symlink_to(target)


def build_env(heap_limit_hex: str | None) -> dict:
    env = os.environ.copy()
    shim = CT_ROOT / "reproduce" / "bin"
    make_llvm12_shims(shim)
    env["CT_ROOT"] = str(CT_ROOT)
    env["CT_SKIP_BUILDBECH"] = "1"
    env["CONDA_PREFIX"] = str(CONDA)
    env["PATH"] = ":".join([
        str(CT_ROOT / "script/vfct_analysis"),   # must precede script/
        str(CT_ROOT / "script"),
        str(CT_ROOT / "smack/bin"),
        str(CT_ROOT / "smack/build"),
        str(CT_ROOT / "phasar/build/tools/phasar-llvm"),
        str(shim),
        str(CONDA / "bin"),
        "/usr/local/bin:/usr/bin:/bin",
    ])
    env["LD_LIBRARY_PATH"] = f"{CT13_LIB}:{CONDA}/lib"
    env["DOTNET_ROOT"] = str(CONDA / "lib/dotnet")
    env["DOTNET_ROLL_FORWARD"] = "LatestMajor"   # Boogie 2.9.6 targets net5.0
    env["DOTNET_MULTILEVEL_LOOKUP"] = "0"
    env.pop("DOTNET_GCHeapHardLimit", None)
    if heap_limit_hex:
        env["DOTNET_GCHeapHardLimit"] = heap_limit_hex
    return env


def run_job(job: dict, env: dict, logdir: Path, wall: int, results: dict) -> None:
    work = BECH / job["dir"]
    outdir = work / "one_and_two_and_three"
    if outdir.exists():
        bak = work / f"one_and_two_and_three.prev.{datetime.now().strftime('%Y%m%dT%H%M%S')}"
        shutil.move(str(outdir), str(bak))
        job["moved_previous_output_to"] = str(bak)
    log = logdir / (job["dir"].replace("/", "_") + ".log")
    cmd = ["python3", "-u", str(CT_ROOT / "script/vfct_analysis/vfct_find_bug.py")]
    start_iso = datetime.now().astimezone().isoformat(timespec="seconds")
    t0 = time.monotonic()
    timed_out = False
    with log.open("w") as lf:
        lf.write(f"# start {start_iso} cwd={work} cmd={' '.join(cmd)} wall_cap={wall}s "
                 f"DOTNET_GCHeapHardLimit={env.get('DOTNET_GCHeapHardLimit', 'unset')} "
                 f"CT_SPLIT_HERE={env.get('CT_SPLIT_HERE', 'unset')} "
                 f"CT_VCS_CORES={env.get('CT_VCS_CORES', 'unset')} "
                 f"CT_TAINT_DIR={env.get('CT_TAINT_DIR', 'unset')}\n")
        lf.flush()
        proc = subprocess.Popen(cmd, cwd=work, env=env, stdout=subprocess.PIPE,
                                stderr=subprocess.STDOUT, text=True, bufsize=1,
                                start_new_session=True)

        def killer():
            nonlocal timed_out
            try:
                proc.wait(timeout=wall)
            except subprocess.TimeoutExpired:
                timed_out = True
                os.killpg(proc.pid, signal.SIGTERM)
                try:
                    proc.wait(timeout=30)
                except subprocess.TimeoutExpired:
                    os.killpg(proc.pid, signal.SIGKILL)

        th = threading.Thread(target=killer, daemon=True)
        th.start()
        for line in proc.stdout:
            lf.write(f"[t={time.monotonic() - t0:10.3f}] {line}")
            lf.flush()
        proc.wait()
        th.join()
        # make sure no boogie/z3 survives in the group
        try:
            os.killpg(proc.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        elapsed = time.monotonic() - t0
        if timed_out:
            lf.write(f"[t={elapsed:10.3f}] # WALL TIMEOUT after {wall}s: process group killed\n")
        lf.write(f"# end {datetime.now().astimezone().isoformat(timespec='seconds')} "
                 f"rc={proc.returncode} elapsed={elapsed:.3f} timed_out={timed_out}\n")
    job.update(start=start_iso, end=datetime.now().astimezone().isoformat(timespec="seconds"),
               rc=proc.returncode, elapsed_s=round(elapsed, 3), wall_timeout=timed_out,
               log=str(log))
    results[job["dir"]] = job
    print(f"[done] {job['dir']} rc={proc.returncode} elapsed={elapsed:.1f}s timed_out={timed_out}",
          flush=True)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--logdir", default=str(CT_ROOT / "reproduce/runlogs/table3-fixed"))
    ap.add_argument("--wall", type=int, default=7200, help="wall-clock cap per directory (s)")
    ap.add_argument("--heap", default="0x4000000000",
                    help="DOTNET_GCHeapHardLimit for Boogie (default 256 GiB); 'none' to unset")
    ap.add_argument("--only", nargs="*", help="bench dirs to run (default: all Table 3 dirs)")
    ap.add_argument("--extra", nargs="*", default=[],
                    help="extra jobs DIR:HEAPHEX (e.g. a copied bench dir for a controlled check)")
    ap.add_argument("--taint-dir", nargs="*", default=[],
                    help="DIR:PATH, run steps 2/3 of bench DIR on the step-1 files "
                         "(<stem>-t.ll, <stem>-taintres.txt) found in PATH")
    ap.add_argument("--vcs-cores", type=int, default=0,
                    help="Boogie /vcsCores:n (VC pieces checked in parallel)")
    ap.add_argument("--split-here", action="store_true",
                    help="add {:split_here} to every leak assert (one VC piece per assert)")
    ap.add_argument("--no-split-here", action="store_true",
                    help="(default) stock single VC; kept for older command lines")
    args = ap.parse_args()
    taint_dirs = {}
    for spec in args.taint_dir:
        d, p = spec.split(":", 1)
        taint_dirs[d] = str(Path(p).resolve())

    logdir = Path(args.logdir)
    logdir.mkdir(parents=True, exist_ok=True)
    dirs = []
    for _, d, _ in CASES:
        if d not in dirs and (not args.only or d in args.only):
            dirs.append(d)
    heap = None if args.heap == "none" else args.heap
    jobs = [{"dir": d, "heap": heap} for d in dirs]
    for spec in args.extra:
        d, h = spec.split(":")
        jobs.append({"dir": d, "heap": None if h == "none" else h})

    for tool in ("boogie", "llvm2bpl", "phasar-llvm", "llvm-link-12", "ruby"):
        if shutil.which(tool, path=build_env(heap)["PATH"]) is None:
            print(f"ERROR: {tool} not on PATH", file=sys.stderr)
            return 2

    git = subprocess.run(["git", "-C", str(CT_ROOT), "rev-parse", "HEAD"],
                         capture_output=True, text=True).stdout.strip()
    bam5 = subprocess.run(["git", "-C", str(CT_ROOT), "diff", "--stat", "--",
                           "bam/bam-5/lib/bpl/transformation/shadowing.rb"],
                          capture_output=True, text=True).stdout.strip()
    boogie_flags = "/doModSetAnalysis /errorLimit 0 /timeLimit 3600"
    if args.vcs_cores:
        boogie_flags += f" /vcsCores:{args.vcs_cores}"
    manifest = {"started": datetime.now().astimezone().isoformat(timespec="seconds"),
                "ct_root": str(CT_ROOT), "git_head": git, "bam5_patch": bam5,
                "wall_cap_s": args.wall, "boogie_flags": boogie_flags,
                "split_here": bool(args.split_here), "taint_dirs": taint_dirs,
                "jobs": {}}
    results: dict = {}
    threads = []
    for job in jobs:
        env = build_env(job["heap"])
        env["CT_SPLIT_HERE"] = "1" if args.split_here else "0"
        if args.vcs_cores:
            env["CT_VCS_CORES"] = str(args.vcs_cores)
        if job["dir"] in taint_dirs:
            env["CT_TAINT_DIR"] = taint_dirs[job["dir"]]
            job["taint_dir"] = taint_dirs[job["dir"]]
        print(f"[run] {job['dir']} heap={job['heap']} wall={args.wall}s", flush=True)
        th = threading.Thread(target=run_job, args=(job, env, logdir, args.wall, results))
        th.start()
        threads.append(th)
    for th in threads:
        th.join()
    manifest["jobs"] = results
    manifest["finished"] = datetime.now().astimezone().isoformat(timespec="seconds")
    (logdir / "manifest.json").write_text(json.dumps(manifest, indent=2))
    print(f"[manifest] {logdir / 'manifest.json'}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
