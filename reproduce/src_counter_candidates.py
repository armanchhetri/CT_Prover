#!/usr/bin/env python3
"""Compare candidate operationalisations of Table 3 `#Src y` / `z`.

For each row whose step finished, print, for the first and the final Boogie
round of step 2 (bool) and step 3 (shadow):
  bpl   distinct Boogie line numbers of `This assertion might not hold`
  N     Boogie footer `N errors` (includes loop-invariant errors)
  src   distinct C (file, line) of those assertions (derive_table3.py's y/z)

Usage: src_counter_candidates.py <outputs root> > derived/src_counter_candidates.csv
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import derive_table3 as d  # noqa: E402


def main() -> int:
    root = Path(sys.argv[1])
    cols = ["id", "paper_y", "paper_z"]
    for kind in ("bool", "shadow"):
        for r in ("first", "final"):
            cols += [f"{kind}_{r}_bpl", f"{kind}_{r}_N", f"{kind}_{r}_src"]
    cols += ["bool_rounds", "shadow_rounds"]
    print(",".join(cols))
    for pid, bench, stem in d.CASES:
        outdir = root / bench / "one_and_two_and_three"
        if not outdir.is_dir():
            outdir = root / bench.replace("/", "_")
        _, py, pz = d.PAPER[pid][2].split(":")
        row = [pid, py, pz]
        counts = {}
        for kind in ("bool", "shadow"):
            reps = d.rounds(outdir, stem, kind)
            bpl0 = d.find(outdir / f"{stem}-{kind}-0.bpl")
            for label, rep in (("first", reps[0] if reps else None),
                               ("final", reps[-1] if reps and reps[-1].finished and not reps[-1].inv else None)):
                if rep is None or not rep.finished:
                    row += ["", "", ""]
                else:
                    row += [len(rep.sites), rep.n_errors, len(d.src_locations(bpl0, rep.sites))]
            counts[kind] = len(reps)
        row += [counts["bool"], counts["shadow"]]
        print(",".join(str(v) for v in row))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
