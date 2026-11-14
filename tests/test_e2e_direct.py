"""オーケストレーター全体の通しテスト（WITNESS_DIRECT=1、外部サービスは偽物）。

本物のまま動くもの: 計画のガード、封印、ジョブ生成、プローブの並列実行（ローカル）、
CodeAF 修復ループ（harness だけ偽物）、台帳、説明の配線、case.json の保存。
"""
import asyncio
import functools
import importlib
import json
import os
from types import SimpleNamespace

import pytest

from witness import config, prereg
from witness.schemas import Preregistration

FAKE_PROBE = '''from _common import emit, load_params, measure, run
def main():
    p = load_params()
    import os
    os.makedirs("out", exist_ok=True)
    open("out/change_{m}.png", "wb").write(b"png")
    emit("{probe}", {{"{m}": measure({v}, {lo}, {hi})}}, 0.9, ["scene-{probe}"], ["change_{m}.png"]){bug}
run(main)
'''

SCENARIOS = {
    # 本物の冠水: 3 センサーとも予測どおり
    "true": {"optical_change": ("new_water_frac", 0.12, 0.08, 0.16),
             "sar_change": ("vv_drop_frac", 0.10, 0.07, 0.13),
             "weather_anomaly": ("precip_z", 9.0, 6.0, 12.0)},
    # 場所すり替え: 雨も冠水も無い
    "swapped": {"optical_change": ("new_water_frac", 0.001, -0.004, 0.006),
                "sar_change": ("vv_drop_frac", 0.0, -0.003, 0.004),
                "weather_anomaly": ("precip_z", 0.2, -0.5, 0.9)},
}


@pytest.fixture
def direct(monkeypatch, tmp_path):
    monkeypatch.setenv("WITNESS_DIRECT", "1")
    monkeypatch.setattr(config, "RUNS_DIR", tmp_path / "runs")
    monkeypatch.setattr(config, "CDSE_CLIENT_ID", "test")  # SAR プローブを有効にする
    import witness.mesh
    importlib.reload(witness.mesh)
    import nodes.core, nodes.lab, nodes.scout
    lab = importlib.reload(nodes.lab)
    scout_node = importlib.reload(nodes.scout)
    core = importlib.reload(nodes.core)
    yield core, lab, scout_node
    monkeypatch.delenv("WITNESS_DIRECT")
    importlib.reload(witness.mesh)


def fake_sources(tmp_path, scenario):
    dirs = {}
    for probe, (m, v, lo, hi) in SCENARIOS[scenario].items():
        d = tmp_path / f"src-{scenario}-{probe}"
        d.mkdir()
        for f in ("_common.py", "_stats.py"):
            (d / f).write_bytes((config.PROBES_DIR / f).read_bytes())
        bug = " BUG" if probe == "sar_change" else ""  # SAR だけわざと壊して CodeAF 修復を通す
        (d / f"{probe}.py").write_text(FAKE_PROBE.format(probe=probe, m=m, v=v, lo=lo, hi=hi, bug=bug))
        dirs[probe] = d
    return dirs


async def fake_ai(*args, system=None, user=None, schema=None, **kw):
    from nodes.core import Explanation
    from nodes.scout import StanceList
    from witness.planning import PlanDraft, SignatureProposal, SkepticReview
    if schema is PlanDraft:
        return PlanDraft(place="Dubai International Airport", event_type="flood", event_date="2024-04-16",
                         reasoning="報道から特定")
    if schema is SkepticReview:
        return SkepticReview(alternatives=["恒久的な水域を新たな水面と誤認"], signatures=[
            SignatureProposal(id="flood.new_water.s2", probe="optical_change", measure="new_water_frac",
                              sensor="s2", direction="increase", min_effect=0.03, rationale="厳しめに"),
            SignatureProposal(id="flood.vv_drop.s1", probe="sar_change", measure="vv_drop_frac",
                              sensor="s1", direction="increase", min_effect=0.0, rationale="緩める試み")])
    if schema is StanceList:
        return StanceList(items=[])
    if schema is Explanation:
        assert len(args) >= 2  # プロンプト + 画像パス
        return Explanation(summary="説明", signatures=[], image_flags=[], media_vs_observation="一致")
    raise AssertionError(schema)


def wire(core, lab, scout_node, monkeypatch, tmp_path, scenario):
    srcs = fake_sources(tmp_path, scenario)
    from witness.sandbox import LocalExecutor, ProbeJob
    monkeypatch.setattr(lab, "_executor", LocalExecutor())
    monkeypatch.setattr(lab, "ProbeJob", lambda probe, params, run_dir: ProbeJob(probe, params, run_dir, srcs[probe]))
    for node in (core, scout_node):
        monkeypatch.setattr(node.app, "ai", fake_ai)

    async def fake_harness(prompt, provider, cwd, **kw):
        from pathlib import Path
        f = Path(cwd) / "sar_change.py"
        f.write_text(f.read_text().replace(" BUG", ""))
        return SimpleNamespace(text="fixed", error_message=None)

    monkeypatch.setattr(lab.app, "harness", fake_harness)
    monkeypatch.setattr(core.geo, "geocode", lambda place: (25.2532, 55.3657, place))
    monkeypatch.setattr(scout_node.scout, "scan", lambda claim: {"answer": "Dubai flooded", "sources": [
        {"title": "Dubai floods", "url": "https://n/a", "published": "2024-04-17", "snippet": "airport"}]})
    monkeypatch.setattr(scout_node.scout, "corroborate", lambda claim, place, d: {"window": ["", ""], "sources": [
        {"title": "OCHA", "url": "https://reliefweb.int/x", "published": "", "snippet": "", "authoritative": True}]})


@pytest.mark.parametrize("scenario,label", [("true", "supported"), ("swapped", "contradicted")])
def test_verify_claim_end_to_end(direct, monkeypatch, tmp_path, scenario, label):
    core, lab, scout_node = direct
    wire(core, lab, scout_node, monkeypatch, tmp_path, scenario)

    out = asyncio.run(core.verify_claim(claim="2024年4月の豪雨でドバイ空港周辺が冠水した"))
    assert out["label"] == label, out

    case = json.loads(open(out["case"]).read())
    sealed = Preregistration.model_validate(case["prereg"])
    prereg.verify(sealed)  # 保存された事前登録が改変されていない
    sigs = {s["id"]: s for s in case["prereg"]["hypothesis"]["signatures"]}
    assert sigs["flood.new_water.s2"]["min_effect"] == 0.03   # Skeptic の厳格化は採用
    assert sigs["flood.vv_drop.s1"]["min_effect"] == 0.02     # 緩める提案は却下
    assert any("却下" in x for x in case["plan_log"])
    assert case["prereg"]["hypothesis"]["alternatives"] == ["恒久的な水域を新たな水面と誤認"]

    res = {r["probe"]: r for r in case["results"]}
    assert set(res) == {"optical_change", "sar_change", "weather_anomaly"}
    assert res["sar_change"]["repairs"] == 1 and not res["sar_change"]["error"]   # CodeAF 修復が効いた
    assert all(len(r["code_sha256"]) == 64 for r in res.values())
    assert case["verdict"]["prereg_sha256"] == sealed.sha256
    assert case["corroboration"]["sources"][0]["authoritative"]
    report = open(out["report"], encoding="utf-8").read()
    assert sealed.sha256 in report and "証拠台帳" in report
