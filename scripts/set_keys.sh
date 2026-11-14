#!/usr/bin/env bash
# .env にキーを書き込む。入力は画面に表示しない。Enter だけ押すと既存値を保持。
set -euo pipefail
cd "$(dirname "$0")/.."
[ -f .env ] || cp .env.example .env

set_kv() {  # $1=key $2=value
  python3 - "$1" "$2" <<'PY'
import sys, re, pathlib
k, v = sys.argv[1], sys.argv[2]
p = pathlib.Path(".env"); s = p.read_text()
line = f"{k}={v}"
s, n = re.subn(rf"^{re.escape(k)}=.*$", lambda m: line, s, flags=re.M)
if not n: s = s.rstrip("\n") + "\n" + line + "\n"
p.write_text(s)
PY
}

ask() {  # $1=key $2=label $3=secret(1/0)
  local v
  if [ "$3" = 1 ]; then read -r -s -p "$2: " v; echo; else read -r -p "$2: " v; fi
  if [ -n "$v" ]; then set_kv "$1" "$v"; echo "  ✓ $1 を保存"; else echo "  - $1 はそのまま"; fi
}

echo "キーを貼って Enter（表示されません）。未取得なら Enter でスキップ。"
ask TAVILY_API_KEY     "Tavily API key (tvly-...)"        1
ask DAYTONA_API_KEY    "Daytona API key (dtn_...)"        1
ask OPENROUTER_API_KEY "OpenRouter API key (sk-or-...)"   1
read -r -p "Nosana のデプロイ URL（/v1 なしで可）: " u
if [ -n "$u" ]; then u="${u%/}"; [[ "$u" == */v1 ]] || u="$u/v1"; set_kv NOSANA_BASE_URL "$u"; echo "  ✓ NOSANA_BASE_URL を保存"; fi
chmod 600 .env
echo "完了。Claude に「入れた」と伝えてください。"
