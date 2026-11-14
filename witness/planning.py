"""LLM（Planner / Skeptic）の提案を、事前登録できる仮説に安全に取り込む。

ガード
- 既定シグネチャの閾値は「厳しくする」方向にしか変えられない（緩めて通す、を防ぐ）
- 既定シグネチャは削除できない
- 新しいシグネチャは追加できる。今あるプローブで測れなければ「新規プローブ候補」になる
- 日付は未来・遠すぎる過去を拒否する
"""
from __future__ import annotations

from datetime import date, timedelta
from typing import Literal, Optional

from pydantic import BaseModel, Field

from .schemas import AOI, EventType, Hypothesis, Signature, TimeFrame
from .signatures import default_signatures

MAX_YEARS_BACK = 12  # Sentinel-2 の運用開始（2015）以降に限る


class SignatureProposal(BaseModel):
    id: str = Field(description="既定シグネチャを厳しくするならその id、新規なら新しい id")
    probe: str
    measure: str
    sensor: str
    direction: Literal["increase", "decrease"]
    min_effect: float = Field(ge=0)
    rationale: str = ""


class PlanDraft(BaseModel):
    place: str = Field(description="ジオコーディング可能な具体的地名（例: 'Dubai International Airport, UAE'）")
    event_type: EventType
    event_date: str = Field(description="出来事の日付 YYYY-MM-DD（報道から特定）")
    half_km: float = Field(default=4.0, ge=1.0, le=15.0, description="観測範囲の半径相当 km")
    signatures: list[SignatureProposal] = Field(default_factory=list, description="追加・厳格化の提案のみ")
    reasoning: str = ""


class SkepticReview(BaseModel):
    alternatives: list[str] = Field(description="主張以外で同じ観測を生みうる説明（季節、潮位、収穫、雲の影など）")
    signatures: list[SignatureProposal] = Field(default_factory=list,
                                                description="代替仮説を潰すための追加・厳格化の提案")
    concerns: list[str] = Field(default_factory=list)


class PlanError(ValueError):
    pass


def parse_event_date(s: str, today: Optional[date] = None) -> date:
    today = today or date.today()
    try:
        d = date.fromisoformat(s.strip()[:10])
    except ValueError as e:
        raise PlanError(f"日付を解釈できません: {s!r}") from e
    if d > today:
        raise PlanError(f"未来の日付です: {d}")
    if d < today - timedelta(days=365 * MAX_YEARS_BACK):
        raise PlanError(f"古すぎる日付です（衛星データの範囲外）: {d}")
    return d


def merge_signatures(base: list[Signature], proposals: list[SignatureProposal]) -> tuple[list[Signature], list[str]]:
    """戻り値: (合成後のシグネチャ, 却下・調整の記録)"""
    by_id = {s.id: s for s in base}
    order = [s.id for s in base]
    log: list[str] = []
    for p in proposals:
        if p.id in by_id:
            cur = by_id[p.id]
            if p.min_effect > cur.min_effect:
                by_id[p.id] = cur.model_copy(update={"min_effect": p.min_effect,
                                                     "rationale": f"{cur.rationale}／厳格化: {p.rationale}".strip("／")})
                log.append(f"{p.id}: 閾値を {cur.min_effect} → {p.min_effect} に厳格化")
            elif p.min_effect < cur.min_effect:
                log.append(f"{p.id}: 閾値を緩める提案（{p.min_effect}）は却下")
            continue
        by_id[p.id] = Signature(**p.model_dump())
        order.append(p.id)
        log.append(f"{p.id}: 追加（{p.probe}.{p.measure} {p.direction} ≥ {p.min_effect}）")
    return [by_id[i] for i in order], log


def build_hypothesis(claim: str, draft: PlanDraft, lat: float, lon: float,
                     today: Optional[date] = None) -> tuple[Hypothesis, list[str]]:
    ev = parse_event_date(draft.event_date, today)
    sigs, log = merge_signatures(default_signatures(draft.event_type), draft.signatures)
    if not sigs:
        raise PlanError(f"{draft.event_type} を測るシグネチャがありません")
    hyp = Hypothesis(claim=claim, event_type=draft.event_type,
                     aoi=AOI(place=draft.place, lat=lat, lon=lon, half_km=draft.half_km),
                     timeframe=TimeFrame.around(ev, today=today), signatures=sigs)
    return hyp, log


def apply_review(hyp: Hypothesis, review: SkepticReview) -> tuple[Hypothesis, list[str]]:
    sigs, log = merge_signatures(hyp.signatures, review.signatures)
    return hyp.model_copy(update={"signatures": sigs, "alternatives": hyp.alternatives + review.alternatives}), log
