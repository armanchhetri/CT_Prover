#!/bin/bash
# PhASAR bootstrap — conda / no-sudo variant.
# Original (apt/pacman/sudo + /usr/local installs): bootstrap.sh.sudo.bak
#
# Prerequisites:
#   conda activate ctprover13   # LLVM 13, clang, boost, cmake, ninja
# Optional env overrides:
#   CONDA_ENV_NAME   (default: ctprover13)
#   PHASAR_INSTALL_DIR  (default: <repo>/phasar/install)
#   SKIP_CONDA_INSTALL=1  to skip "conda install ..."
#   DO_UNIT_TEST=true|false (default: false)
set -e

source ./utils/safeCommandsSet.sh

readonly PHASAR_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" >/dev/null 2>&1 && pwd )"

NUM_THREADS=$(nproc)
DO_UNIT_TEST=false
CONDA_ENV_NAME="${CONDA_ENV_NAME:-ctprover13}"

POSITIONAL=()
while [[ $# -gt 0 ]]; do
  key="$1"
  case $key in
    -j|--jobs)
      NUM_THREADS="$2"; shift 2 ;;
    -u|--unittest)
      DO_UNIT_TEST=true; shift ;;
    -DBOOST_DIR)
      DESIRED_BOOST_DIR="$2"; shift 2 ;;
    -DBOOST_DIR=*)
      DESIRED_BOOST_DIR="${key#*=}"; shift ;;
    -DBOOST_VERSION|-DBOOST_VERSION=*)
      echo "WARNING: -DBOOST_VERSION ignored in conda bootstrap (use conda packages)." >&2
      shift
      [[ "$key" == -DBOOST_VERSION ]] && shift || true
      ;;
    *)
      POSITIONAL+=("$1"); shift ;;
  esac
done
set -- "${POSITIONAL[@]}"

# --- conda env ------------------------------------------------------------
if [ -z "${CONDA_PREFIX:-}" ] || [[ "$(basename "$CONDA_PREFIX")" != "$CONDA_ENV_NAME" ]]; then
  if [ -f "${HOME}/miniforge3/etc/profile.d/conda.sh" ]; then
    # shellcheck source=/dev/null
    source "${HOME}/miniforge3/etc/profile.d/conda.sh"
  elif [ -f "${HOME}/anaconda3/etc/profile.d/conda.sh" ]; then
    # shellcheck source=/dev/null
    source "${HOME}/anaconda3/etc/profile.d/conda.sh"
  elif [ -f "${HOME}/mambaforge/etc/profile.d/conda.sh" ]; then
    # shellcheck source=/dev/null
    source "${HOME}/mambaforge/etc/profile.d/conda.sh"
  else
    echo "ERROR: conda not found. Install miniforge/mambaforge or set CONDA_PREFIX." >&2
    exit 1
  fi
  conda activate "$CONDA_ENV_NAME"
fi

if [ -z "${CONDA_PREFIX:-}" ]; then
  echo "ERROR: CONDA_PREFIX unset after activate $CONDA_ENV_NAME" >&2
  exit 1
fi

echo "Using conda env: $CONDA_PREFIX"

# Install build deps into the active env (no sudo). Safe to re-run.
if [ "${SKIP_CONDA_INSTALL:-0}" != "1" ]; then
  echo "Ensuring conda packages for PhASAR (LLVM 13 stack)..."
  # Pin CMake 3.x: CMake 4 dropped compatibility with Phasar's
  # cmake_minimum_required(VERSION 3.0) and fails configure.
  conda install -y -c conda-forge \
    "clangdev=13.*" "llvmdev=13.*" "llvm-tools=13.*" \
    boost-cpp "cmake>=3.20,<4" ninja zlib sqlite libxml2 libedit \
    pyyaml pygments pip \
    || {
      echo "ERROR: conda install failed (need write access to the env + network)." >&2
      echo "  Fix the env, or re-run with SKIP_CONDA_INSTALL=1 if packages are already present." >&2
      exit 1
    }
  # Optional / often useful; ignore failure if channel hiccups
  conda install -y -c conda-forge z3-solver nlohmann_json 2>/dev/null || true
  pip install --upgrade Pygments pyyaml wllvm 2>/dev/null || \
    pip install Pygments pyyaml wllvm
fi

# Use conda LLVM instead of building into /usr/local/llvm-13
LLVM_INSTALL_DIR="${LLVM_INSTALL_DIR:-$CONDA_PREFIX}"
if ! command -v llvm-config >/dev/null || [[ "$(llvm-config --version)" != 13.* ]]; then
  echo "ERROR: need llvm-config from LLVM 13 in PATH (got: $(llvm-config --version 2>/dev/null || echo missing))" >&2
  exit 1
fi
echo "LLVM $(llvm-config --version) at $(llvm-config --prefix)"

# Install PhASAR under the repo (writable without sudo), not /usr/local/phasar
PHASAR_INSTALL_DIR="${PHASAR_INSTALL_DIR:-${PHASAR_DIR}/install}"

if [ -n "${DESIRED_BOOST_DIR:-}" ]; then
  BOOST_PARAMS="-DBOOST_ROOT=${DESIRED_BOOST_DIR}"
else
  BOOST_PARAMS="-DBOOST_ROOT=${CONDA_PREFIX}"
fi

echo "dependencies resolved via conda (no apt/pacman/sudo)"

echo "Building PhASAR..."
${DO_UNIT_TEST} && echo "with unit tests."

# ---------------------------------------------------------------------------
# external/* is required by CMakeLists (json, googletest, schema-validator, WALi).
# This phasar tree is often vendored without a nested .git, so `git submodule`
# does nothing. Populate external/ ourselves.
# ---------------------------------------------------------------------------
ensure_external_deps() {
  local ext="${PHASAR_DIR}/external"
  mkdir -p "$ext"

  need_json() { [ -f "$ext/json/single_include/nlohmann/json.hpp" ]; }
  need_gtest() { [ -d "$ext/googletest/googletest" ]; }
  need_jsv() { [ -d "$ext/json-schema-validator/src" ]; }
  need_wali() { [ -d "$ext/WALi-OpenNWA" ]; }

  if need_json && need_gtest && need_jsv && need_wali; then
    echo "external deps already present under $ext"
    return 0
  fi

  # Optional: copy from a complete PhASAR tree (e.g. prior checkout)
  if [ -n "${PHASAR_EXTERNAL_SRC:-}" ] && [ -d "${PHASAR_EXTERNAL_SRC}" ]; then
    echo "Copying external deps from PHASAR_EXTERNAL_SRC=${PHASAR_EXTERNAL_SRC}"
    rsync -a "${PHASAR_EXTERNAL_SRC}/" "$ext/"
  fi

  if need_json && need_gtest && need_jsv && need_wali; then
    return 0
  fi

  # Try git submodule when this directory is its own git repo
  if [ -d "${PHASAR_DIR}/.git" ] || [ -f "${PHASAR_DIR}/.git" ]; then
    echo "Trying git submodule update --init --recursive ..."
    ( cd "${PHASAR_DIR}" && git submodule update --init --recursive ) || true
  fi

  if need_json && need_gtest && need_jsv && need_wali; then
    return 0
  fi

  echo "Cloning missing external deps over HTTPS ..."
  if ! need_json; then
    rm -rf "$ext/json"
    git clone --depth 1 --branch v3.10.5 https://github.com/nlohmann/json.git "$ext/json"
  fi
  if ! need_gtest; then
    rm -rf "$ext/googletest"
    git clone --depth 1 --branch release-1.12.1 https://github.com/google/googletest.git "$ext/googletest"
  fi
  if ! need_jsv; then
    rm -rf "$ext/json-schema-validator"
    git clone --depth 1 https://github.com/pboettch/json-schema-validator.git "$ext/json-schema-validator"
  fi
  if ! need_wali; then
    rm -rf "$ext/WALi-OpenNWA"
    git clone --depth 1 https://github.com/pdschubert/WALi-OpenNWA.git "$ext/WALi-OpenNWA"
  fi

  if ! need_json || ! need_gtest || ! need_jsv || ! need_wali; then
    echo "ERROR: failed to populate ${ext}/{json,googletest,json-schema-validator,WALi-OpenNWA}" >&2
    echo "  Set PHASAR_EXTERNAL_SRC to a complete phasar/external directory, or clone manually." >&2
    exit 1
  fi
  echo "external deps ready"
}
ensure_external_deps

export CC="${CC:-$CONDA_PREFIX/bin/clang}"
export CXX="${CXX:-$CONDA_PREFIX/bin/clang++}"
# Prefer clang-12 from ctprover if present — clang-13 + Boost hits
# "discarded section .text.startup" link failures on this stack.
if [ -x "${HOME}/miniforge3/envs/ctprover/bin/clang++" ]; then
  CC="${HOME}/miniforge3/envs/ctprover/bin/clang"
  CXX="${HOME}/miniforge3/envs/ctprover/bin/clang++"
fi
# Conda activation often sets CC/CXX to the env's GCC; force clang.
if [[ "$(basename "$CC")" == *conda-linux-gnu-cc* ]] || [[ "$("$CC" --version 2>/dev/null | head -1)" == *GCC* ]]; then
  CC="${HOME}/miniforge3/envs/ctprover/bin/clang"
  [ -x "$CC" ] || CC="$CONDA_PREFIX/bin/clang"
fi
if [[ "$(basename "$CXX")" == *conda-linux-gnu-c++* ]] || [[ "$("$CXX" --version 2>/dev/null | head -1)" == *g++* ]]; then
  CXX="${HOME}/miniforge3/envs/ctprover/bin/clang++"
  [ -x "$CXX" ] || CXX="$CONDA_PREFIX/bin/clang++"
fi
export CC CXX
export PATH="$CONDA_PREFIX/bin:$PATH"
export LD_LIBRARY_PATH="$CONDA_PREFIX/lib${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"

# Conda activation injects -ffunction-sections / -Wl,--gc-sections which breaks
# clang linking of Boost optional (discarded .text.startup). Keep a minimal flag set.
export CFLAGS="--gcc-toolchain=/usr"
export CXXFLAGS="--gcc-toolchain=/usr"
export LDFLAGS="-L${CONDA_PREFIX}/lib -Wl,-rpath,${CONDA_PREFIX}/lib -Wl,-rpath-link,${CONDA_PREFIX}/lib -fuse-ld=bfd"
# Drop other conda toolchain injects if present
unset DEBUG_CFLAGS DEBUG_CXXFLAGS DEBUG_LDFLAGS
unset CPPFLAGS

# Guard against CMake 4 if the env still has it
CMAKE_VER=$(cmake --version | head -1 | awk '{print $3}')
CMAKE_MAJOR=${CMAKE_VER%%.*}
CMAKE_POLICY_FLAG=()
if [ "${CMAKE_MAJOR}" -ge 4 ]; then
  echo "WARNING: cmake ${CMAKE_VER} is >= 4; adding -DCMAKE_POLICY_VERSION_MINIMUM=3.5"
  echo "  Prefer: conda install -y -c conda-forge 'cmake>=3.20,<4'"
  CMAKE_POLICY_FLAG=(-DCMAKE_POLICY_VERSION_MINIMUM=3.5)
fi

mkdir -p "${PHASAR_DIR}/build"
safe_cd "${PHASAR_DIR}/build"
# Fresh configure if a previous CMake 4 attempt left a bad cache
if [ -f CMakeCache.txt ]; then
  rm -rf CMakeCache.txt CMakeFiles
fi
echo "Configuring with CC=$CC CXX=$CXX (gcc-toolchain=/usr for libstdc++)"
cmake -G Ninja \
  -DCMAKE_BUILD_TYPE=Release \
  -DCMAKE_INSTALL_PREFIX="${PHASAR_INSTALL_DIR}" \
  -DCMAKE_PREFIX_PATH="${CONDA_PREFIX}" \
  -DCMAKE_C_COMPILER="${CC}" \
  -DCMAKE_CXX_COMPILER="${CXX}" \
  -DCMAKE_C_FLAGS="${CFLAGS}" \
  -DCMAKE_CXX_FLAGS="${CXXFLAGS}" \
  -DCMAKE_EXE_LINKER_FLAGS="${LDFLAGS}" \
  -DCMAKE_SHARED_LINKER_FLAGS="${LDFLAGS}" \
  -DLLVM_DIR="$(llvm-config --cmakedir)" \
  ${BOOST_PARAMS} \
  "${CMAKE_POLICY_FLAG[@]}" \
  -DPHASAR_BUILD_UNITTESTS=${DO_UNIT_TEST} \
  "${PHASAR_DIR}"
# Default ninja "all" also builds IR test .ll via clang without our flags; build tools only.
cmake --build . -j "${NUM_THREADS}" --target phasar-llvm

if ${DO_UNIT_TEST}; then
  echo "Running PhASAR unit tests..."
  pushd unittests
  for x in $(find . -type f -executable -print); do
    pushd "${x%/*}" && ./"${x##*/}" && popd || { echo "Test ${x} failed, aborting."; exit 1; }
  done
  popd
fi

echo "phasar successfully built"
echo "install phasar to ${PHASAR_INSTALL_DIR} (no sudo)..."
mkdir -p "${PHASAR_INSTALL_DIR}/bin"
if [ -x tools/phasar-llvm/phasar-llvm ]; then
  cp -f tools/phasar-llvm/phasar-llvm "${PHASAR_INSTALL_DIR}/bin/phasar-llvm"
  # Best-effort full install; ignore failures from unbuilt IR-test targets
  cmake -DCMAKE_INSTALL_PREFIX="${PHASAR_INSTALL_DIR}" -P cmake_install.cmake 2>/dev/null || true
else
  cmake -DCMAKE_INSTALL_PREFIX="${PHASAR_INSTALL_DIR}" -P cmake_install.cmake
fi
safe_cd ..

# Local env file instead of writing ~/.bashrc and opening a new shell
ENV_FILE="${PHASAR_DIR}/env.conda.sh"
cat > "${ENV_FILE}" <<EOF
# Generated by phasar/bootstrap.sh (conda / no-sudo)
# Usage: source ${ENV_FILE}
export CONDA_ENV_NAME=${CONDA_ENV_NAME}
# shellcheck disable=SC1091
source "\$(conda info --base)/etc/profile.d/conda.sh"
conda activate "\${CONDA_ENV_NAME}"
export PATH="${PHASAR_INSTALL_DIR}/bin:\${PATH}"
export LD_LIBRARY_PATH="\${CONDA_PREFIX}/lib:\${LD_LIBRARY_PATH:-}"
export PHASAR_INCLUDE_DIR="${PHASAR_INSTALL_DIR}/include"
export PHASAR_LIBRARY_DIR="${PHASAR_INSTALL_DIR}/lib"
export PHASAR_INSTALL_DIR="${PHASAR_INSTALL_DIR}"
EOF

echo "phasar successfully installed to ${PHASAR_INSTALL_DIR}"
echo "Environment snippet written to ${ENV_FILE}"
echo "  source ${ENV_FILE}"
