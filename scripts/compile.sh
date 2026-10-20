#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
source scripts/env.sh
for document in report/report.tex report/supplement-historical.tex report/supplement-modern_same.tex report/supplement-expanded.tex; do
  pdflatex -interaction=nonstopmode -halt-on-error -output-directory=report "$document" > .tmp/latex-pass1.log
  pdflatex -interaction=nonstopmode -halt-on-error -output-directory=report "$document" > .tmp/latex-pass2.log
done
