"""Orbital Witness の共通スキーマ。

原則: LLM は Hypothesis / Signature / ProbeSpec を「提案」するだけ。
結論（Verdict）は ProbeResult と事前登録済みの閾値から決定的に計算する。
"""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from typing import Literal, Optional

from pydantic import BaseModel, Field

EventType = Literal["flood", "deforestation", "fire", "construction", "drought", "landslide", "other"]
Direction = Literal["increase", "decrease"]
Outcome = Literal["confirm", "refute", "null"]
Label = Literal["supported", "contradicted", "inconclusive"]


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class AOI(BaseModel):
    place: str
    lat: float
    lon: float
    half_km: float = 3.0

    def bbox(self) -> list[float]:
        import math
        dlat = self.half_km / 111.0
        dlon = self.half_km / (111.0 * max(math.cos(math.radians(self.lat)), 0.01))
        return [self.lon - dlon, self.lat - dlat, self.lon + dlon, self.lat + dlat]


class TimeFrame(BaseModel):
    event_date: date
    before: tuple[date, date]
    after: tuple[date, date]
    baseline_years_back: int = 1  # 季節対照: 何年前の同時期と比べるか

    @classmethod
    def around(cls, event_date: date, before_days: int = 45, after_days: int = 21,
               today: Optional[date] = None) -> "TimeFrame":
        today = today or date.today()
        after_end = min(event_date + timedelta(days=after_days), today)
        return cls(
            event_date=event_date,
            before=(event_date - timedelta(days=before_days), event_date - timedelta(days=1)),
            after=(event_date, after_end),
        )

    def seasonal(self) -> "TimeFrame":
        """同じ窓を N 年ずらした対照期間（季節変動の除去用）。"""
        def shift(d: date) -> date:
            try:
                return d.replace(year=d.year - self.baseline_years_back)
            except ValueError:  # 2/29
                return d.replace(year=d.year - self.baseline_years_back, day=28)
        return TimeFrame(event_date=shift(self.event_date),
                         before=(shift(self.before[0]), shift(self.before[1])),
                         after=(shift(self.after[0]), shift(self.after[1])),
                         baseline_years_back=self.baseline_years_back)


class Signature(BaseModel):
    """「主張が本当なら、この量がこの向きに、少なくともこれだけ動くはず」という予測。"""
    id: str
    probe: str = Field(description="測るプローブ名（例: optical_change）")
    measure: str = Field(description="プローブが返す量のキー（例: new_water_frac）")
    sensor: str = Field(description="独立性のグルーピングに使う（例: s2, s1, meteo）")
    direction: Direction
    min_effect: float = Field(ge=0, description="主張を支持するのに必要な最小効果（量の単位）")
    rationale: str = ""


class Hypothesis(BaseModel):
    claim: str
    event_type: EventType
    aoi: AOI
    timeframe: TimeFrame
    signatures: list[Signature]
    alternatives: list[str] = Field(default_factory=list, description="代替仮説（Skeptic が追加）")
    prior_p: float = Field(default=0.5, gt=0, lt=1)


class Preregistration(BaseModel):
    hypothesis: Hypothesis
    planner_model: str = ""
    sealed_at: Optional[datetime] = None
    sha256: Optional[str] = None


class Measure(BaseModel):
    value: float
    lo: float
    hi: float
    detail: dict = Field(default_factory=dict, description="生の成分（対象・対照など）")


class ProbeResult(BaseModel):
    probe: str
    measures: dict[str, Measure]
    valid_ratio: float = Field(ge=0, le=1)
    scene_ids: list[str] = Field(default_factory=list)
    code_sha256: str = ""
    sandbox_id: str = ""
    artifacts: dict[str, str] = Field(default_factory=dict)  # 名前 -> ローカルパス
    error: Optional[str] = None
    repairs: int = 0  # コード修復（CodeAF）で直した回数
    finished_at: datetime = Field(default_factory=utcnow)


class LedgerEntry(BaseModel):
    signature_id: str
    sensor: str
    outcome: Outcome
    log_lr: float
    reason: str
    measure: Optional[Measure] = None


class Verdict(BaseModel):
    label: Label
    posterior: float
    prior: float
    entries: list[LedgerEntry]
    prereg_sha256: str


# ---------- ノード間の受け渡し（JSON に NaN を流さない） ----------
def _nan_to_none(x):
    import math
    if isinstance(x, float) and math.isnan(x):
        return None
    if isinstance(x, dict):
        return {k: _nan_to_none(v) for k, v in x.items()}
    if isinstance(x, list):
        return [_nan_to_none(v) for v in x]
    return x


def result_to_wire(r: ProbeResult) -> dict:
    return _nan_to_none(r.model_dump(mode="json"))


def result_from_wire(d: dict) -> ProbeResult:
    nan = float("nan")
    d = dict(d)
    d["measures"] = {k: {**m, **{f: (nan if m.get(f) is None else m[f]) for f in ("value", "lo", "hi")}}
                     for k, m in (d.get("measures") or {}).items()}
    return ProbeResult.model_validate(d)
