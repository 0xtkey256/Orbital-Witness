"""LLM（Planner / Skeptic）の提案を、事前登録できる仮説に安全に取り込む。

ガード
- 既定シグネチャの閾値は変えられない（AI に閾値を決めさせない。提案は記録して監査できるようにする）
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


# プローブ → 独立性グループ。LLM が sensor を "satellite" などと書いても台帳の独立性が崩れないようにする
PROBE_SENSOR = {"optical_change": "s2", "sar_change": "s1", "weather_anomaly": "meteo"}


def merge_signatures(base: list[Signature], proposals: list[SignatureProposal],
                     allow_new: bool = True) -> tuple[list[Signature], list[str]]:
    """戻り値: (合成後のシグネチャ, 却下・調整の記録)

    - 同じ (probe, measure) は 1 つの証拠。新しい id で出し直されても重複として数えない
    - 既定シグネチャの閾値は変えない（厳格化の提案は記録のみ、緩める提案と逆向きの提案は却下）。
      LLM は毎回上限まで厳しくする傾向があり、それを許すと実質的に AI が結論を決めてしまうため
    - allow_new=False（Skeptic）のとき、新しい量は補助観測として記録するだけで判定に入れない
    """
    sigs = list(base)
    log: list[str] = []

    def find(p):
        for k, s in enumerate(sigs):
            if s.id == p.id or (s.probe == p.probe and s.measure == p.measure):
                return k, s
        return None, None

    for p in proposals:
        k, cur = find(p)
        if cur is not None:
            if p.direction != cur.direction:
                log.append(f"{p.id}: {cur.id} と逆向きの提案は却下（代替仮説として記録）")
                continue
            if p.min_effect > cur.min_effect:
                log.append(f"{cur.id}: 厳格化の提案（{cur.min_effect} → {p.min_effect}、提案 {p.id}）は記録のみ。"
                           "閾値は物理的な既定値に固定し、AI には変えさせない")
            elif p.min_effect < cur.min_effect:
                log.append(f"{p.id}: 閾値を緩める提案（{p.min_effect}）は却下")
            else:
                log.append(f"{p.id}: {cur.id} と同じ観測のため重複として統合")
            continue
        if not allow_new:
            log.append(f"{p.id}: 補助観測として記録（{p.probe}.{p.measure}、判定には不算入）")
            continue
        sigs.append(Signature(**{**p.model_dump(exclude={"sensor"}),
                                 "sensor": PROBE_SENSOR.get(p.probe, p.sensor)}))
        log.append(f"{p.id}: 追加（{p.probe}.{p.measure} {p.direction} ≥ {p.min_effect}）")
    return sigs, log


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
    sigs, log = merge_signatures(hyp.signatures, review.signatures, allow_new=False)
    return hyp.model_copy(update={"signatures": sigs, "alternatives": hyp.alternatives + review.alternatives}), log
