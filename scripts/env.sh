#!/usr/bin/env bash
# Source from the project root. Never place caches or credentials in $HOME.
export XDG_CACHE_HOME="$PWD/.cache"
export XDG_CONFIG_HOME="$PWD/.config"
export MPLCONFIGDIR="$PWD/.cache/matplotlib"
export TMPDIR="$PWD/.tmp"
export PYTHONPYCACHEPREFIX="$PWD/.cache/pycache"
export CONDA_PKGS_DIRS="$PWD/.cache/conda"
export CONDA_ENVS_PATH="$PWD/envs"
export CONDA_REGISTER_ENVS=false
export PIP_CACHE_DIR="$PWD/.cache/pip"
export GH_CONFIG_DIR="$PWD/.config/gh"
export TEXMFVAR="$PWD/.cache/texmf-var"
export TEXMFCONFIG="$PWD/.config/texmf"
export TEXMFCACHE="$PWD/.cache/texmf-cache"
export OPENBLAS_NUM_THREADS=1
export OMP_NUM_THREADS=1
export PATH="$PWD/envs/seismo/bin:$PATH"
mkdir -p "$MPLCONFIGDIR" "$TMPDIR"
