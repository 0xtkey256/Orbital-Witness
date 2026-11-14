#!/usr/bin/env bash
# 使い方: scripts/verify.sh "2024年4月16日の記録的豪雨で、ドバイ国際空港周辺が広範囲に冠水した"
# AgentField の control plane に非同期で投げ、完了まで状態を確認する（同期 API は 90 秒で切れるため）。
set -euo pipefail
CLAIM="${1:?主張を引数で渡してください}"
SERVER="${AGENTFIELD_SERVER:-http://localhost:8080}"
BODY="$(python3 -c 'import json,sys;print(json.dumps({"input":{"claim":sys.argv[1]}}, ensure_ascii=False))' "$CLAIM")"
EID="$(curl -sS -X POST "$SERVER/api/v1/execute/async/witness-core.verify_claim" \
  -H "Content-Type: application/json" -d "$BODY" | python3 -c 'import json,sys;print(json.load(sys.stdin)["execution_id"])')"
echo "execution_id: $EID（ダッシュボード: $SERVER）" >&2
for _ in $(seq 1 180); do
  OUT="$(curl -sS "$SERVER/api/v1/executions/$EID")"
  ST="$(printf '%s' "$OUT" | python3 -c 'import json,sys;print(json.load(sys.stdin).get("status",""))')"
  case "$ST" in
    succeeded|completed|failed|cancelled|timeout|error)
      printf '%s' "$OUT" | python3 -c '
import json, sys
d = json.load(sys.stdin)
r = d.get("result") or {}
print(json.dumps({"status": d.get("status"), "run_id": r.get("run_id"), "label": r.get("label"),
                  "posterior": r.get("posterior"), "report": r.get("report"), "error": d.get("error")},
                 ensure_ascii=False, indent=1))'
      exit 0;;
  esac
  printf '.' >&2
  sleep 5
done
echo "15 分待っても終わりませんでした: $EID" >&2
exit 1
