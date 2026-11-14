# 当日の手順（15:40 → 17:30 提出）

## 15:40 クレジットと起動（10 分）
1. Nosana のクレジットを受け取り、すぐ `nosana/qwen-vl-vllm.json` をデプロイ（RTX 4090）。URL + `/v1` を `.env` の NOSANA_BASE_URL へ
2. Tavily: app.tavily.com/redeem/AGENTFORGE → API キーを `.env` へ
3. Daytona: メールのリンクで申請 → API キーを `.env` へ → 裏で `python scripts/build_snapshot.py`

## 15:50 環境（15 分）
```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env            # キーを埋める。CDSE は空のままでよい（SAR は自動で外れる）
curl -fsSL https://agentfield.ai/install.sh | bash && af server   # 別ターミナル
scripts/start_nodes.sh          # 別ターミナル
python scripts/preflight.py     # 全部 ✅ になるまで直す
```
スナップショットが完成したら `.env` に WITNESS_SNAPSHOT=orbital-witness-geo を入れてノードを再起動。

## 16:10 本番の主張で通す（30 分）
```bash
scripts/verify.sh "2024年4月16日の記録的豪雨で、ドバイ国際空港周辺が広範囲に冠水した"
open runs/<run_id>/report.html
```
詰まったら:
- control plane 経由でタイムアウト → `WITNESS_DIRECT=1 python -c "import asyncio; from nodes.core import verify_claim; print(asyncio.run(verify_claim(claim='...')))"`
- Nosana の JSON が崩れる → 温度はすでに 0.2。プロンプトを短くするか、NOSANA_MODEL を Qwen2.5-7B-Instruct（テキスト専用）に替え、explain の画像を外す

## 16:40 反証される主張（20 分）
場所すり替え型の誤情報を 1〜2 本試し、「反証」になるものをデモに採用する。
ならなければ「判定不能」も正直さの見せ場として使える（雨は降ったが冠水は見えない、など）。

## 17:05 提出準備（25 分）
- 成功した run の report.html と AgentField ダッシュボードのトレースを画面録画（デモ失敗時の保険）
- 提出文には SPONSORS.md の表をそのまま使う
- 17:20 までに提出

## デモ 3 分
1. 主張を投げる（15 秒）
2. 事前登録のハッシュが観測の前に封印される瞬間（30 秒）— 「AI に結論を出させない、実験を設計させる」
3. ダッシュボード: Daytona のサンドボックスが並列で走るトレース、Skeptic が閾値を厳しくし、緩める提案は却下（45 秒）
4. レポート: 衛星画像、証拠台帳、報道と観測の対比（45 秒）
5. 反証される誤情報（30 秒）
6. 用途: 報道のファクトチェック、パラメトリック保険、人道支援（15 秒）
