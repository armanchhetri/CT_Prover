#!/bin/bash
# Build the one-round step-3 input for a case.
#   make_pruned.sh <bench-dir> <prefix> <out-dir>
#   e.g. make_pruned.sh bech/BearSSL/RSA_i15 decrypt /tmp/p6_5
# Takes <prefix>-shadow-0.bpl, removes {:split_here} marks (left there by the
# isolated-sites run), then comments out every active invariant candidate.
# In this pipeline the step-3 candidates are exactly the invariants that
# step 2 rejected. Commenting them keeps the line numbers. Do not leave
# them unmarked instead: bam --process_mark turns unmarked invariants into
# x := x.shadow, which assumes them.
set -e
src="$1/one_and_two_and_three/$2-shadow-0.bpl"
mkdir -p "$3"
sed -E 's/assert \{:split_here\} /assert /' "$src" > "$3/stock0.bpl"
sed -E 's#^(\s*assert \{:(shadow_invariant|likely_shadow_invariant)\}.*)#  // \1#' \
    "$3/stock0.bpl" > "$3/pruned.bpl"
echo "lines: $(wc -l < "$src") -> $(wc -l < "$3/pruned.bpl")," \
     "commented: $(diff "$3/stock0.bpl" "$3/pruned.bpl" | grep -c '^>')"
