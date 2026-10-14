#!/bin/bash
# Run one Boogie round on <dir>/pruned.bpl with the flags and environment of
# reproduce/run_table3.py (Boogie 2.9.6 from the ctprover conda env, 256 GiB heap).
#   run_one_round.sh <dir>
C=${CONDA:-$HOME/miniforge3/envs/ctprover}
export PATH=$C/bin:/usr/local/bin:/usr/bin:/bin LD_LIBRARY_PATH=$C/lib DOTNET_ROOT=$C/lib/dotnet \
       DOTNET_ROLL_FORWARD=LatestMajor DOTNET_MULTILEVEL_LOOKUP=0 DOTNET_GCHeapHardLimit=0x4000000000
cd "$1"
st=$(date +%s.%N)
timeout 21600 boogie /doModSetAnalysis /errorLimit 0 /timeLimit 3600 pruned.bpl > pruned.txt 2> pruned.err
rc=$?
echo "rc=$rc elapsed=$(echo "$(date +%s.%N) - $st" | bc)" > done.txt
