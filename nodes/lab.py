"""witness-lab ノード — プローブを [Daytona] で実行し、壊れたら [CodeAF] が直す。

プローブ 1 本 = reasoner 1 つ（タグ probe, sensor:*, measure:*）。Planner は AgentField の
discovery でここに登録されたプローブを実行時に見つける。プローブの追加 = ここへの登録だけ。
"""
import os

from agentfield import Agent

from witness import config
from witness.llm import nosana_ai_config
from witness.repair import codeaf_repair, codeaf_synthesize
from witness.sandbox import PROBES, DaytonaExecutor, LocalExecutor, ProbeJob, enabled_probes, run_jobs
from witness.schemas import result_to_wire
from witness.signatures import known_measures

app = Agent(node_id="witness-lab", agentfield_server=config.AGENTFIELD_SERVER,
            description="衛星・気象プローブを隔離サンドボックスで実行し、失敗時はコードを修復する",
            tags=["daytona", "codeaf", "probes"], ai_config=nosana_ai_config(), dev_mode=True)

SENSOR = {"optical_change": "s2", "sar_change": "s1", "weather_anomaly": "meteo"}
DESCRIPTION = {
    "optical_change": "Sentinel-2 光学: 水面・植生・裸地・焼失・造成の変化割合（前年同時期との差の差）",
    "sar_change": "Sentinel-1 SAR: 後方散乱の低下（冠水）と増加（構造物）。雲を透過",
    "weather_anomaly": "ERA5 再解析: 出来事前後の積算降水の、過去15年同時期に対する z 値",
}
_executor = None
PROBE_FUNCS = {}  # 退避モード（WITNESS_DIRECT=1）で core から直接呼ぶため


def executor():
    global _executor
    if _executor is None:  # WITNESS_EXECUTOR=local は Daytona 障害時の退避（sandbox_id が local になる）
        _executor = LocalExecutor() if os.environ.get("WITNESS_EXECUTOR") == "local" else DaytonaExecutor()
    return _executor


async def _repair(job, log):
    return await codeaf_repair(app, job, log)


async def _run(job: ProbeJob) -> dict:
    app.note(f"{job.probe}: サンドボックスを起動（{executor().name}、通信先 {', '.join(PROBES[job.probe]['domains'])}）",
             tags=["daytona"])
    [res] = await run_jobs([job], executor(), repair=_repair)
    status = "完了" if not res.error else f"失敗: {res.error[:160]}"
    app.note(f"{job.probe}: {status}（sandbox {res.sandbox_id or '-'}、修復 {res.repairs} 回、code {res.code_sha256[:10]}）",
             tags=["daytona"])
    return result_to_wire(res)


def _register(probe: str):
    async def run_probe(params: dict, run_id: str) -> dict:
        return await _run(ProbeJob(probe, params, config.RUNS_DIR / run_id))
    tags = ["probe", f"sensor:{SENSOR.get(probe, 'other')}"] + [f"measure:{m}" for m in sorted(known_measures().get(probe, []))]
    app.reasoner(name=f"probe_{probe}", tags=tags, description=DESCRIPTION.get(probe, probe))(run_probe)
    PROBE_FUNCS[probe] = run_probe


for _p in enabled_probes():
    _register(_p)


@app.reasoner(tags=["probe-factory", "codeaf"])
async def synthesize_and_run(signature: dict, hyp_summary: dict, params: dict, run_id: str) -> dict:
    """既存プローブで測れないシグネチャ用に、CodeAF が新しいプローブを書き、契約を満たせば実行する。

    閾値はすでに事前登録で封印されているので、コードを後から書いても判定基準は動かない。
    """
    run_dir = config.RUNS_DIR / run_id
    src = await codeaf_synthesize(app, signature["probe"], signature["measure"], signature["direction"],
                                  signature.get("rationale", ""), hyp_summary, config.PROBES_DIR,
                                  out_dir=run_dir / "probes_synth")
    job = ProbeJob(signature["probe"], {**params, "measures": [signature["measure"]]}, run_dir, source_dir=src)
    return await _run(job)


if __name__ == "__main__":
    app.run(port=8102)
