#!/usr/bin/env bash
# 使い方: scripts/verify.sh "2024年4月の豪雨でドバイ国際空港周辺が広範囲に冠水した"
set -euo pipefail
CLAIM="${1:?主張を引数で渡してください}"
SERVER="${AGENTFIELD_SERVER:-http://localhost:8080}"
curl -sS -X POST "$SERVER/api/v1/execute/witness-core.verify_claim" -H "Content-Type: application/json" \
  -d "$(python3 -c 'import json,sys;print(json.dumps({"input":{"claim":sys.argv[1]}}, ensure_ascii=False))' "$CLAIM")" \
  | python3 -m json.tool --no-ensure-ascii
