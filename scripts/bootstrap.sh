#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
mkdir -p .tmp .cache .config envs references logs
source scripts/env.sh
if [[ ! -x envs/miniconda/bin/conda ]]; then
  curl -fL https://repo.anaconda.com/miniconda/Miniconda3-latest-Linux-x86_64.sh -o .tmp/miniconda.sh
  # Preserve the embedded payload byte offsets while disabling the two installer
  # actions that would create ~/.conda. Do not reassign HOME.
  python3 - <<'PY'
from pathlib import Path
b=Path('.tmp/miniconda.sh').read_bytes()
old=b'test -d ~/.conda || mkdir -p ~/.conda >/dev/null 2>/dev/null || test -d ~/.conda || mkdir ~/.conda'
if b.count(old)!=1:raise SystemExit('Installer changed: audit home-directory writes before proceeding')
b=b.replace(old,b':'+b' '*(len(old)-1),1)
old=b'CONDA_REGISTER_ENVS="true"'
if b.count(old)!=1:raise SystemExit('Installer registration changed: audit before proceeding')
b=b.replace(old,b'CONDA_REGISTER_ENVS=false ',1)
Path('.tmp/miniconda-local.sh').write_bytes(b)
PY
  bash .tmp/miniconda-local.sh -b -p "$PWD/envs/miniconda"
fi
if [[ ! -x envs/seismo/bin/python ]]; then
  CONDA_NO_PLUGINS=true envs/miniconda/bin/conda create -y -p "$PWD/envs/seismo" --override-channels -c conda-forge --solver classic python=3.11 pip
fi
python -m pip install -r requirements.txt
if [[ ! -f references/hutko2006.pdf ]]; then
  curl -fL 'https://basin.earth.ncu.edu.tw/download/courses/basin_analysis/reading/Hutko_etal_2006_Nature_Seismic%20detection%20of%20floded%20subducted%20lithsphere%20at%20the%20core-mantle%20boundary_nature04757.pdf' -o references/hutko2006.pdf
fi
command -v pdflatex > /dev/null || { echo 'Install a minimal TeX Live including pdflatex, amsmath, booktabs, longtable, graphicx and hyperref.'; exit 1; }
echo 'Environment ready. Run bash rebuild.sh --online.'
