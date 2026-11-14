"""witness-core ノード — 計画・懐疑・判定の説明・統括。推論はすべて [Nosana]、配線は [AgentField]。

流れ（verify_claim）
  scout.scan ─▶ plan ─▶ ジオコーディング ─▶ challenge(Skeptic) ─▶ 封印（ハッシュを AgentField memory に記録）
    ─▶ lab.probe_* を並列 ＋ scout.corroborate ─▶ 台帳（数式で判定）─▶ explain(VLM) ─▶ case.json
"""
import asyncio
import json
import uuid

from agentfield import Agent
from pydantic import BaseModel, Field

from witness import config, geo, ledger, prereg
from witness.llm import nosana_ai_config
from witness.mesh import DIRECT, call
from witness.plan import jobs_for, unsupported
from witness.planning import PlanDraft, SkepticReview, apply_review, build_hypothesis
from witness.sandbox import enabled_probes
from witness.schemas import Hypothesis, Preregistration, result_from_wire, result_to_wire
from witness.signatures import known_measures

app = Agent(node_id="witness-core", agentfield_server=config.AGENTFIELD_SERVER,
            description="主張を事前登録された実験に変換し、観測から判定する",
            tags=["orchestrator", "nosana"], ai_config=nosana_ai_config(), dev_mode=True)

if DIRECT:  # 退避モードでは他ノードの関数を直接使う
    from nodes import lab as lab_node
    from nodes import scout as scout_node


class SignatureNote(BaseModel):
    signature_id: str
    plain: str = Field(description="この観測が何を意味するか、専門用語を避けた日本語1〜2文")


class Explanation(BaseModel):
    summary: str = Field(description="判定の要約（日本語2〜3文）。数値の判定を変えずに説明する")
    signatures: list[SignatureNote]
    image_flags: list[str] = Field(description="画像から見える品質上の注意（雲、影、季節、境界のずれ等）")
    media_vs_observation: str = Field(description="報道の論調と衛星観測が一致するか食い違うか（日本語1〜2文）")


# ---------- AgentField discovery ----------
def discover_probes() -> dict[str, str]:
    """{probe 名: 呼び出し先}。control plane に登録されたプローブを実行時に見つける。"""
    if not DIRECT:
        try:
            found = app.discover(tags=["probe"]).json
            targets = {r.id.removeprefix("probe_"): r.invocation_target
                       for cap in found.capabilities for r in cap.reasoners if r.id.startswith("probe_")}
            if targets:
                return targets
        except Exception as e:
            app.note(f"discovery 失敗、既定のプローブ一覧を使用: {e}", tags=["agentfield"])
    return {p: f"witness-lab.probe_{p}" for p in enabled_probes()}


def probe_catalog(available: dict[str, str]) -> str:
    km = known_measures()
    return "\n".join(f"- {p}: measures={sorted(km.get(p, []))}" for p in available)


# ---------- Planner ----------
@app.reasoner(tags=["planner"])
async def plan(claim: str, scan: dict, catalog: str) -> dict:
    digest = "\n".join(f"[{s['published']}] {s['title']} — {s['snippet'][:300]}" for s in scan["sources"][:8])
    if not digest:
        digest = "（報道は取得していません。主張の文面だけから場所・日付・出来事の種類を特定してください。" \
                 "日付が不明なら主張に最も整合する日付を1つ選び、place は地図で引ける具体的な地名にします）"
    draft: PlanDraft = await app.ai(
        system="あなたは衛星観測の実験計画者です。主張を、衛星・気象データで反証可能な仮説に変換します。"
               "報道から場所と日付を特定し、出来事の種類を選びます。既定の観測シグネチャは自動で入るので、"
               "signatures には追加・厳格化したいものだけを書きます。閾値を緩めることはできません。",
        user=f"主張: {claim}\n\nTavily の要約: {scan['answer']}\n\n報道:\n{digest}\n\n使えるプローブ:\n{catalog}",
        schema=PlanDraft,
    )
    return draft.model_dump()


# ---------- Skeptic（データを見る前の敵対的レビュー） ----------
@app.reasoner(tags=["skeptic"])
async def challenge(hypothesis: dict, catalog: str) -> dict:
    review: SkepticReview = await app.ai(
        system="あなたは懐疑的な査読者です。データを見る前の実験計画を読み、主張が偽でも同じ観測が出てしまう"
               "代替説明（季節変動、潮位、収穫、雲の影、恒久的な水域、別日の出来事など）を挙げ、"
               "それを排除するためのシグネチャの追加や閾値の厳格化を提案します。緩める提案はしません。",
        user=f"実験計画:\n{json.dumps(hypothesis, ensure_ascii=False, indent=1)}\n\n使えるプローブ:\n{catalog}",
        schema=SkepticReview,
    )
    return review.model_dump()


# ---------- Judge（数値は変えず、画像と台帳から説明を書く） ----------
@app.reasoner(tags=["judge", "vision"])
async def explain(hypothesis: dict, verdict: dict, sources: list, images: list) -> dict:
    ledger_txt = "\n".join(f"- {e['signature_id']}: {e['outcome']} — {e['reason']}" for e in verdict["entries"])
    media = "\n".join(f"- [{s.get('stance', '?')}] {s['title']}" for s in sources[:10])
    exp: Explanation = await app.ai(
        f"主張: {hypothesis['claim']}\n判定（数式で確定済み・変更不可）: {verdict['label']} "
        f"事後確率 {verdict['posterior']:.2f}\n\n証拠台帳:\n{ledger_txt}\n\n報道の立場:\n{media}\n\n"
        "添付画像は順に: " + "、".join(name for name, _ in images),
        *[path for _, path in images],
        system="あなたは衛星画像判読の専門家です。判定は変えずに、根拠と限界を一般の読者に説明します。",
        schema=Explanation,
    )
    return exp.model_dump()


def pick_images(results) -> list[tuple[str, str]]:
    """VLM に見せる画像（vLLM 側の上限 4 枚）。"""
    names = {"before.png": "光学・前", "after.png": "光学・後"}
    out = []
    for r in results:
        for name, path in r.artifacts.items():
            if name in names:
                out.append((names[name], path))
            elif name.startswith("change_"):
                out.append((f"{r.probe} の変化マップ（{name[7:-4]}）", path))
    return out[:4]


# ---------- 統括 ----------
async def _probe(target: str, probe: str, **kw) -> dict:
    return await call(app, target, lab_node.PROBE_FUNCS[probe] if DIRECT else None, **kw)


@app.reasoner(tags=["orchestrator"])
async def verify_claim(claim: str) -> dict:
    run_id = uuid.uuid4().hex[:10]
    run_dir = config.RUNS_DIR / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    available = discover_probes()
    catalog = probe_catalog(available)

    # 1. 探索 → 計画
    try:
        scan_res = await call(app, "witness-scout.scan", scout_node.scan if DIRECT else None, claim=claim)
    except Exception as e:  # scout ノードが落ちていても検証は止めない
        scan_res = {"answer": "", "sources": [], "skipped": f"{type(e).__name__}: {e}"[:200]}
    draft = PlanDraft(**await call(app, "witness-core.plan", plan, claim=claim, scan=scan_res, catalog=catalog))
    loc = geo.geocode(draft.place)
    if loc is None:
        raise ValueError(f"地名を座標にできませんでした: {draft.place}")
    hyp, plan_log = build_hypothesis(claim, draft, loc[0], loc[1])
    app.note(f"計画: {draft.place}（{loc[0]:.4f}, {loc[1]:.4f}）{draft.event_type} {draft.event_date}", tags=["planner"])

    # 2. データを見る前の敵対的レビュー → 封印
    review = SkepticReview(**await call(app, "witness-core.challenge", challenge,
                                        hypothesis=hyp.model_dump(mode="json"), catalog=catalog))
    hyp, review_log = apply_review(hyp, review)
    sealed = prereg.seal(Preregistration(hypothesis=hyp, planner_model=config.NOSANA_MODEL))
    (run_dir / "prereg.json").write_text(sealed.model_dump_json(indent=1))
    try:  # 封印のハッシュを観測前に control plane に記録しておく（時刻つきの第三者記録）
        await app.memory.set(f"prereg:{run_id}", {"sha256": sealed.sha256, "sealed_at": sealed.sealed_at.isoformat(),
                                                  "claim": claim})
    except Exception:
        pass
    app.note(f"事前登録を封印: sha256 {prereg.short(sealed)}…（シグネチャ {len(hyp.signatures)} 件、"
             f"代替仮説 {len(hyp.alternatives)} 件）", tags=["prereg"])

    # 3. 観測（プローブ並列）と報道の裏取りを同時に
    jobs = jobs_for(hyp, run_dir)
    probe_calls = [_probe(available[j.probe], j.probe, params=j.params, run_id=run_id) for j in jobs if j.probe in available]
    synth = []
    if config.WITNESS_SYNTH:
        common = jobs[0].params if jobs else {}
        for sid in unsupported(hyp):
            sig = next(s for s in hyp.signatures if s.id == sid)
            synth.append(call(app, "witness-lab.synthesize_and_run", lab_node.synthesize_and_run if DIRECT else None,
                              signature=sig.model_dump(), run_id=run_id, params=common,
                              hyp_summary={"place": hyp.aoi.place, "lat": hyp.aoi.lat, "lon": hyp.aoi.lon,
                                           "event_date": hyp.timeframe.event_date.isoformat()}))
    corroboration_call = call(app, "witness-scout.corroborate", scout_node.corroborate if DIRECT else None,
                              claim=claim, place=hyp.aoi.place, event_date=hyp.timeframe.event_date.isoformat())
    outputs = await asyncio.gather(*probe_calls, *synth, corroboration_call, return_exceptions=True)
    corroboration = outputs[-1] if isinstance(outputs[-1], dict) else {"sources": [], "error": str(outputs[-1])}
    results = [result_from_wire(o) for o in outputs[:-1] if isinstance(o, dict)]

    # 4. 判定（数式）。較正値があれば AgentField memory から読む
    try:
        calib = await app.memory.global_scope.get("witness:calibration", None)
    except Exception:
        calib = None
    reliability = {**ledger.RELIABILITY, **{k: tuple(v) for k, v in (calib or {}).items()}}
    verdict = ledger.aggregate(sealed, results, reliability)
    app.note(f"判定: {verdict.label}（事後確率 {verdict.posterior:.2f}）", tags=["ledger"])

    # 5. 説明（VLM）
    try:
        explanation = await call(app, "witness-core.explain", explain, hypothesis=hyp.model_dump(mode="json"),
                                 verdict=verdict.model_dump(mode="json"), sources=corroboration.get("sources", []),
                                 images=pick_images(results))
    except Exception as e:
        explanation = {"summary": "", "signatures": [], "image_flags": [f"説明の生成に失敗: {e}"],
                       "media_vs_observation": ""}

    case = {"run_id": run_id, "claim": claim, "prereg": json.loads(sealed.model_dump_json()),
            "plan_log": plan_log + review_log, "results": [result_to_wire(r) for r in results],
            "verdict": json.loads(verdict.model_dump_json()), "explanation": explanation,
            "scan": scan_res, "corroboration": corroboration,
            "geocode": {"lat": loc[0], "lon": loc[1], "display_name": loc[2]}}
    (run_dir / "case.json").write_text(json.dumps(case, ensure_ascii=False, indent=1, default=str))
    try:
        from witness.report import render
        (run_dir / "report.html").write_text(render(json.loads((run_dir / "case.json").read_text())), encoding="utf-8")
    except Exception as e:
        app.note(f"レポート生成に失敗: {e}", tags=["report"])
    try:
        await app.memory.set(f"case:{run_id}", {"claim": claim, "label": verdict.label,
                                                "posterior": verdict.posterior, "prereg": sealed.sha256})
    except Exception:
        pass
    return {"run_id": run_id, "label": verdict.label, "posterior": verdict.posterior,
            "prereg_sha256": sealed.sha256, "summary": explanation.get("summary", ""),
            "case": str(run_dir / "case.json"), "report": str(run_dir / "report.html")}


if __name__ == "__main__":
    app.run(port=8103)
