import time
from datetime import date, timedelta

import numpy as np
import pytest

from witness import ledger, prereg
from witness.probes import _stats
from witness.schemas import AOI, Hypothesis, Measure, Preregistration, ProbeResult, TimeFrame, utcnow
from witness.signatures import default_signatures, known_measures

EVENT = date(2024, 4, 16)


def make_prereg(event_type="flood") -> Preregistration:
    hyp = Hypothesis(
        claim="2024年4月の豪雨でアル・アイン周辺が冠水した",
        event_type=event_type,
        aoi=AOI(place="Al Ain, UAE", lat=24.2075, lon=55.7447, half_km=4),
        timeframe=TimeFrame.around(EVENT, today=date(2026, 11, 14)),
        signatures=default_signatures(event_type),
    )
    return prereg.seal(Preregistration(hypothesis=hyp, planner_model="test"))


def result(probe, **measures) -> ProbeResult:
    time.sleep(0.001)  # 封印より後の時刻にする
    return ProbeResult(probe=probe, valid_ratio=0.9,
                       measures={k: Measure(value=v[0], lo=v[1], hi=v[2]) for k, v in measures.items()})


# ---------- 事前登録 ----------
def test_seal_and_verify():
    p = make_prereg()
    prereg.verify(p)
    assert len(p.sha256) == 64


def test_tampering_after_seal_is_detected():
    p = make_prereg()
    sigs = [s.model_copy(update={"min_effect": 0.0}) for s in p.hypothesis.signatures]  # 閾値を後から甘くする
    tampered = p.model_copy(update={"hypothesis": p.hypothesis.model_copy(update={"signatures": sigs})})
    with pytest.raises(prereg.PreregistrationError):
        prereg.verify(tampered)


def test_observation_before_seal_is_rejected():
    early = ProbeResult(probe="optical_change", valid_ratio=1, measures={},
                        finished_at=utcnow() - timedelta(minutes=1))
    with pytest.raises(prereg.PreregistrationError):
        prereg.check_order(make_prereg(), [early])


def test_cannot_seal_twice():
    with pytest.raises(prereg.PreregistrationError):
        prereg.seal(make_prereg())


# ---------- 期間 ----------
def test_timeframe_and_seasonal_control():
    tf = TimeFrame.around(EVENT, today=date(2026, 1, 1))
    assert tf.before[1] < tf.event_date <= tf.after[0]
    s = tf.seasonal()
    assert s.event_date == date(2023, 4, 16) and s.after[1].year == 2023


def test_timeframe_does_not_go_past_today():
    assert TimeFrame.around(date(2026, 11, 10), today=date(2026, 11, 14)).after[1] == date(2026, 11, 14)


# ---------- 統計 ----------
def test_block_bootstrap_covers_truth():
    rng = np.random.default_rng(1)
    mask = rng.random((512, 512)) < 0.10
    valid = np.ones_like(mask)
    f, lo, hi = _stats.block_bootstrap_frac(mask, valid)
    assert lo <= 0.10 <= hi and abs(f - 0.10) < 0.01


def test_did_removes_seasonal_change():
    rng = np.random.default_rng(2)
    seasonal = rng.random((512, 512)) < 0.05          # 毎年起きる変化
    event = seasonal | (rng.random((512, 512)) < 0.08)  # それに上乗せされた変化
    valid = np.ones_like(seasonal)
    v, lo, hi, d = _stats.did_frac(event, valid, seasonal, valid)
    assert d["control_available"] and lo < v < hi
    assert 0.06 < v < 0.09  # 上乗せ分（約 0.076）だけが残る


def test_did_without_control():
    m = np.zeros((256, 256), bool); m[:64] = True
    v, lo, hi, d = _stats.did_frac(m, np.ones_like(m), np.zeros_like(m), np.zeros_like(m))
    assert not d["control_available"] and abs(v - 0.25) < 1e-9


def test_anomaly_z():
    z, lo, hi = _stats.anomaly_z(250.0, [5, 12, 0, 30, 8, 15, 3, 20, 10, 6])
    assert z > 10 and lo <= z <= hi
    assert np.isnan(_stats.anomaly_z(1.0, [1, 2])[0])


# ---------- シグネチャ ----------
def test_every_event_type_has_signatures_except_other():
    for et in ["flood", "deforestation", "fire", "construction", "drought", "landslide"]:
        assert default_signatures(et)
    assert default_signatures("other") == []
    assert "new_water_frac" in known_measures()["optical_change"]


# ---------- 台帳 ----------
def test_true_flood_is_supported():
    p = make_prereg()
    v = ledger.aggregate(p, [
        result("optical_change", new_water_frac=(0.12, 0.08, 0.16)),
        result("sar_change", vv_drop_frac=(0.10, 0.07, 0.13)),
        result("weather_anomaly", precip_z=(9.0, 6.0, 12.0)),
    ])
    assert v.label == "supported" and v.posterior > 0.95
    assert v.prereg_sha256 == p.sha256


def test_true_flood_without_sar_is_still_supported():
    v = ledger.aggregate(make_prereg(), [
        result("optical_change", new_water_frac=(0.12, 0.08, 0.16)),
        result("weather_anomaly", precip_z=(9.0, 6.0, 12.0)),
    ])
    assert v.label == "supported"


def test_place_swapped_claim_is_contradicted():
    """場所をすり替えた誤情報: その場所では雨も冠水も観測されない。"""
    v = ledger.aggregate(make_prereg(), [
        result("optical_change", new_water_frac=(0.0005, -0.002, 0.003)),
        result("weather_anomaly", precip_z=(0.2, -0.5, 0.9)),
    ])
    assert v.label == "contradicted" and v.posterior < 0.15


def test_rain_without_visible_water_is_not_overclaimed():
    """雨は降ったが冠水は見えない → 確信度を上げすぎない。"""
    v = ledger.aggregate(make_prereg(), [
        result("optical_change", new_water_frac=(0.0005, -0.002, 0.003)),
        result("weather_anomaly", precip_z=(9.0, 6.0, 12.0)),
    ])
    assert v.label == "inconclusive"


def test_cloudy_or_failed_probes_are_null():
    p = make_prereg()
    cloudy = result("optical_change", new_water_frac=(0.2, 0.1, 0.3)).model_copy(update={"valid_ratio": 0.1})
    failed = ProbeResult(probe="sar_change", valid_ratio=0, measures={}, error="timeout")
    v = ledger.aggregate(p, [cloudy, failed])
    assert v.label == "inconclusive" and all(e.outcome == "null" for e in v.entries)


def test_wide_interval_is_null_not_confirm():
    v = ledger.aggregate(make_prereg(), [result("optical_change", new_water_frac=(0.03, -0.01, 0.07))])
    e = next(e for e in v.entries if e.signature_id == "flood.new_water.s2")
    assert e.outcome == "null"


def test_correlated_evidence_is_damped():
    """同じセンサーの証拠を2つ足しても、独立な2つほどには効かない。"""
    p = make_prereg("deforestation")
    v = ledger.aggregate(p, [result("optical_change", veg_loss_frac=(0.1, 0.06, 0.14), bare_gain_frac=(0.05, 0.03, 0.07))])
    lr = ledger.log_lr("confirm", 0.80, 0.85)
    expected_lo = 2 * lr / np.sqrt(2)
    assert abs(np.log(v.posterior / (1 - v.posterior)) - expected_lo) < 1e-3
