"""実データでプローブを確認する（前日に必ず通す）。

    python scripts/smoke_probes.py local                 # 手元で実行（通信先の確認用）
    python scripts/smoke_probes.py daytona               # Daytona で並列実行（本番と同じ）
    python scripts/smoke_probes.py daytona optical_change weather_anomaly

題材: 2024-04-16 のドバイ豪雨。ドバイ国際空港周辺は冠水が広く報じられた。
期待: weather_anomaly の z が非常に大きい / optical_change の new_water_frac が正。
"""
import asyncio
import sys
import time
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from witness import config  # noqa: E402
from witness.plan import jobs_for  # noqa: E402
from witness.sandbox import DaytonaExecutor, LocalExecutor, run_jobs  # noqa: E402
from witness.schemas import AOI, Hypothesis, TimeFrame  # noqa: E402
from witness.signatures import default_signatures  # noqa: E402

if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else "local"
    only = set(sys.argv[2:])
    hyp = Hypothesis(claim="smoke", event_type="flood",
                     aoi=AOI(place="Dubai International Airport", lat=25.2532, lon=55.3657, half_km=4),
                     timeframe=TimeFrame.around(date(2024, 4, 16)),
                     signatures=default_signatures("flood"))
    run_dir = config.RUNS_DIR / f"smoke-{int(time.time())}"
    jobs = [j for j in jobs_for(hyp, run_dir) if not only or j.probe in only]
    executor = DaytonaExecutor() if mode == "daytona" else LocalExecutor()

    t = time.time()
    results = asyncio.run(run_jobs(jobs, executor))
    print(f"{len(jobs)} プローブ / {time.time() - t:.0f} 秒 / 実行環境 {executor.name}\n")
    for r in results:
        print(f"[{r.probe}] sandbox={r.sandbox_id or '-'} valid={r.valid_ratio:.0%} code={r.code_sha256[:10]}")
        if r.error:
            print("   ERROR:", r.error[:600])
        for k, m in r.measures.items():
            print(f"   {k}: {m.value:+.4f}  [{m.lo:+.4f}, {m.hi:+.4f}]  {m.detail}")
        for name, path in r.artifacts.items():
            print(f"   - {name}: {path}")
