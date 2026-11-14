# 🛰️ Orbital Witness

**衛星を証人に立てる。** 拡散する主張を、AI が「事前登録された実験」に変え、衛星と気象データで反証可能な形で検証するエージェント。

**Put satellites on the witness stand.** An agent that turns viral claims into pre-registered experiments and tests them against satellite and weather data — the verdict comes from a formula, not from an LLM.

Agent Forge AI Hackathon Tokyo · 2026-11-14 · **Live demo: https://0xtkey256.github.io/Orbital-Witness/**

| Claim | Verdict | Evidence |
|---|---|---|
| 2024年4月16日の記録的豪雨で、ドバイ国際空港周辺が広範囲に冠水した | ✅ **supported** (posterior 0.91) | Sentinel-2 new water +1.1% (95% CI 0.6–1.6%, diff-in-diff vs 2023) · ERA5 rain z = +20.8 (92 mm vs 1.6 mm normal) |
| 2024年4月16日の記録的豪雨で、エジプトのカイロ国際空港周辺が広範囲に冠水した *(place-swapped misinformation)* | ❌ **contradicted** (posterior 0.045) | no new water (CI upper −0.6%) · rain z = −0.34 |

## How it works

1. **Scout** (Tavily) finds where/when the claim is about — optional; the verdict never depends on news.
2. **Planner** (Nosana-hosted Qwen2.5-VL) turns it into a hypothesis with physical *signatures* (e.g. flood → new water in Sentinel-2, rainfall anomaly in ERA5, VV drop in Sentinel-1).
3. **Skeptic** lists alternative explanations (tide, cloud shadow, irrigation, wrong date…).
4. **Seal** — the hypothesis is hashed (SHA-256) and stored in AgentField memory **before any data is fetched**. The AI cannot move thresholds afterwards.
5. **Probes** run in parallel Daytona sandboxes, discovered at runtime through AgentField; **CodeAF** repairs a probe if it crashes.
6. **Ledger** decides by formula: posterior log-odds = prior + Σ log LR.
7. **Judge** (Nosana VLM) looks at before/after/change images and explains — it cannot change the verdict.

See **[ARCHITECTURE.md](ARCHITECTURE.md)** for diagrams and **[SPONSORS.md](SPONSORS.md)** for exactly where each partner technology lives in the code.

## Partner technologies

| | Role |
|---|---|
| **AgentField** | 3 nodes (scout / lab / core) on the control plane, probe discovery by tag, seal hash in memory, live trace & notes |
| **Daytona** | one isolated sandbox per sensor probe, in parallel; orchestrator prefetches metadata, sandbox reads only S3 pixels |
| **CodeAF** | auto-repairs probe code that fails inside Daytona; threshold constants are protected |
| **Nosana** | Qwen2.5-VL-7B on vLLM (RTX 3090) for planning, skepticism and image interpretation |
| **Tavily** | supporting *and* debunking news search, authoritative sources preferred (optional) |

## Run it

```bash
uv venv -p 3.12 .venv && source .venv/bin/activate
uv pip install -r requirements.txt
cp .env.example .env            # or: bash scripts/set_keys.sh (hidden input)
python -m pytest -q             # offline tests
python scripts/preflight.py     # checks every partner API for real
bash scripts/start_nodes.sh     # AgentField control plane must be running (af server)
scripts/verify.sh "2024年4月16日の記録的豪雨で、ドバイ国際空港周辺が広範囲に冠水した"
open runs/<run_id>/report.html
```

Fallbacks: `WITNESS_TAVILY=0` (no news), `WITNESS_LLM=openrouter` (if the Nosana GPU is down), `WITNESS_DIRECT=1` (no control plane).

## Use cases

Newsroom fact-checking · parametric insurance loss confirmation · humanitarian damage assessment · deforestation due diligence — anywhere a claim about the physical world needs evidence that a third party can re-run.

Data: Copernicus Sentinel-2 L2A via Element 84 Earth Search (AWS Open Data), ERA5 via Open-Meteo, optional Sentinel-1 via Copernicus Data Space.
