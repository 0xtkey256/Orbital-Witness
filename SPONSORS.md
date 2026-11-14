# スポンサー技術の統合マップ

5 社とも役割が決まった位置に入っています（Tavily だけは任意で、無くても観測だけで判定できます）。審査員がコードで確かめられるよう、ファイルと関数を挙げます。

| パートナー | どこで | 何をしているか | 外すと |
|---|---|---|---|
| **AgentField** | `nodes/*.py`、`witness/mesh.py` | 3 ノード（scout / lab / core）を control plane に登録し、`app.call` でつないで 1 回の検証を DAG として追跡する。プローブは `probe` タグ付き reasoner で、core は `app.discover(tags=["probe"])` で実行時に見つける。進捗は `app.note`、事前登録のハッシュと較正値は `app.memory` | ノード間の配線、プローブの動的発見、封印の第三者記録が消える |
| **Tavily** | `witness/scout.py`、`nodes/scout.py` | 主張から場所・日付を探る検索 → 出来事の期間（`start_date`/`end_date`）に絞った「支持」「否定・検証」の 2 方向検索 → 公的機関（ReliefWeb、Copernicus EMS、GDACS など）を `include_domains_mode="prefer"` で優先 → 上位を `extract` で本文抽出 | 報道との対比が消える（判定は観測だけで出るので検証自体は続く。クレジット切れ等は自動で省略） |
| **Daytona** | `witness/sandbox.py` | プローブ 1 本ごとに隔離サンドボックスを並列起動。STAC 検索と気象 API はオーケストレーター側で引いて `params.json` に同梱し（各プローブの `prefetch()`）、サンドボックスは S3 の COG 画素だけを読む。上位ティアでは `domain_allow_list` で通信先を絞る。SAR の認証は Daytona Secrets で平文を渡さない | 衛星データの取得・解析と、生成・修復コードの安全な実行ができない |
| **CodeAF** | `witness/repair.py`、`nodes/lab.py` | AgentField の `app.harness(provider="codeaf")` 経由で、(1) 失敗したプローブを修復する。閾値の数値定数を変えた修復は ast 比較で拒否し、統計・共通モジュールの変更は破棄し、差分を保存する。(2) 既存プローブで測れない観測を新しいプローブとして書かせ、通信先の宣言と契約を検査して登録する | プローブが壊れたら検証が止まる。新しい種類の出来事に対応できない |
| **Nosana** | `witness/llm.py`、`nosana/qwen-vl-vllm.json` | Qwen2.5-VL-7B を vLLM で自前ホストし、全ノードの `app.ai` の行き先にする（計画、懐疑役のレビュー、報道の立場分類、画像を見ての説明）。`CODEAF_VIA_NOSANA=1` で CodeAF も同じ GPU で動く | エージェントが考えられない（`WITNESS_LLM=openrouter` は GPU 停止時のデモ用退避先） |

## 確かめ方

```bash
python scripts/preflight.py   # 4 社＋AgentField を本物の API で 1 つずつ確認
python -m pytest -q           # 55 件（ネットワーク不要）
```

## 設計上の約束

- **LLM は結論を出さない。** 判定は `witness/ledger.py` の数式で決まり、Judge（VLM）は説明を書くだけ
- **データを見る前に封印する。** 封印後の改変と、封印前の観測は `witness/prereg.py` が拒否する
- **CodeAF はバグを直せるが、ゴールポストは動かせない。**
