"""証拠台帳: 観測結果を事前登録の閾値と比べ、対数オッズで結論を出す。

判定規則（シグネチャごと、向きを揃えた信頼区間 [lo, hi] に対して）
  lo >= min_effect          → confirm（予測どおりの変化が確かにある）
  hi <  min_effect          → refute （予測した大きさの変化は無いと言える）
  それ以外 / データ不足       → null   （判定に使わない）

集計
  事後対数オッズ = 事前対数オッズ + Σ_センサー (Σ log LR) / √n_センサー
  同じセンサー由来の証拠は独立でないため、グループ内は √n で割って減衰させる。
"""
from __future__ import annotations

import math

from . import prereg as pr
from .schemas import LedgerEntry, Preregistration, ProbeResult, Signature, Verdict

MIN_VALID_RATIO = 0.3

# (感度, 特異度) の事前値。キーはシグネチャ ID → センサーの順に引く。
# 評価ハーネスで較正して上書きする（Part 5）。
RELIABILITY: dict[str, tuple[float, float]] = {
    "s1": (0.85, 0.85),
    "s2": (0.80, 0.85),
    "meteo": (0.85, 0.55),
    # 豪雨は冠水のほぼ必要条件だが十分条件ではない: 降っていなければ強く反証、降っていても弱い支持
    "flood.precip.meteo": (0.90, 0.50),
}
DEFAULT_RELIABILITY = (0.70, 0.70)

SUPPORT_P, CONTRADICT_P = 0.85, 0.15


def log_lr(outcome: str, sens: float, spec: float) -> float:
    if outcome == "confirm":
        return math.log(sens / (1 - spec))
    if outcome == "refute":
        return math.log((1 - sens) / spec)
    return 0.0


def judge_signature(sig: Signature, result: ProbeResult | None,
                    reliability: dict[str, tuple[float, float]] = RELIABILITY) -> LedgerEntry:
    sens, spec = reliability.get(sig.id) or reliability.get(sig.sensor) or DEFAULT_RELIABILITY

    def entry(outcome, reason, m=None):
        return LedgerEntry(signature_id=sig.id, sensor=sig.sensor, outcome=outcome,
                           log_lr=log_lr(outcome, sens, spec), reason=reason, measure=m)

    if result is None or result.error:
        return entry("null", f"プローブ失敗: {result.error if result else '未実行'}")
    if result.valid_ratio < MIN_VALID_RATIO:
        return entry("null", f"有効画素が {result.valid_ratio:.0%} しかない")
    m = result.measures.get(sig.measure)
    if m is None or any(math.isnan(x) for x in (m.value, m.lo, m.hi)):
        return entry("null", f"{sig.measure} が得られなかった")

    s = 1.0 if sig.direction == "increase" else -1.0
    lo, hi = sorted((s * m.lo, s * m.hi))
    if lo >= sig.min_effect:
        return entry("confirm", f"{sig.measure}={m.value:+.3f}（区間の下限 {lo:.3f} ≥ 閾値 {sig.min_effect}）", m)
    if hi < sig.min_effect:
        return entry("refute", f"{sig.measure}={m.value:+.3f}（区間の上限 {hi:.3f} < 閾値 {sig.min_effect}）", m)
    return entry("null", f"{sig.measure}={m.value:+.3f}（区間 [{lo:.3f}, {hi:.3f}] が閾値 {sig.min_effect} を跨ぐ）", m)


def aggregate(prereg: Preregistration, results: list[ProbeResult],
              reliability: dict[str, tuple[float, float]] = RELIABILITY) -> Verdict:
    pr.check_order(prereg, results)  # 改変・順序違反があればここで止まる
    hyp = prereg.hypothesis
    by_probe = {r.probe: r for r in results}
    entries = [judge_signature(sig, by_probe.get(sig.probe), reliability) for sig in hyp.signatures]

    groups: dict[str, list[float]] = {}
    for e in entries:
        if e.outcome != "null":
            groups.setdefault(e.sensor, []).append(e.log_lr)
    prior_lo = math.log(hyp.prior_p / (1 - hyp.prior_p))
    post_lo = prior_lo + sum(sum(v) / math.sqrt(len(v)) for v in groups.values())
    post = 1 / (1 + math.exp(-post_lo))

    if not groups:
        label = "inconclusive"
    elif post >= SUPPORT_P:
        label = "supported"
    elif post <= CONTRADICT_P:
        label = "contradicted"
    else:
        label = "inconclusive"
    return Verdict(label=label, posterior=round(post, 4), prior=hyp.prior_p,
                   entries=entries, prereg_sha256=prereg.sha256)
