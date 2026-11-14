#!/usr/bin/env bash
# 先に別ターミナルで `af server` を起動しておく（ダッシュボード http://localhost:8080）
set -euo pipefail
cd "$(dirname "$0")/.."
python -m nodes.scout & P1=$!
python -m nodes.lab   & P2=$!
python -m nodes.core  & P3=$!
trap 'kill $P1 $P2 $P3 2>/dev/null' EXIT
echo "witness-scout(8101) / witness-lab(8102) / witness-core(8103) を起動しました。Ctrl-C で停止。"
wait
