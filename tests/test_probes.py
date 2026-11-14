import asyncio
import importlib
import sys
from datetime import date
from pathlib import Path

import numpy as np
import pytest

from witness import config
from witness.plan import jobs_for, unsupported
from witness.sandbox import PROBES, LocalExecutor, ProbeJob, run_jobs
from witness.schemas import AOI, Hypothesis, Signature, TimeFrame
from witness.signatures import default_signatures, known_measures

sys.path.insert(0, str(config.PROBES_DIR))  # プローブはサンドボックス内と同じく平置きで import
optical = importlib.import_module("optical_change")
weather = importlib.import_module("weather_anomaly")
sar = importlib.import_module("sar_change")

N = 128


# ---------- 光学 ----------
def scene(green, nir, red=0.05, valid=True):
    b = {"green": np.full((N, N), green, "float32"), "nir": np.full((N, N), nir, "float32"),
         "red": np.full((N, N), red, "float32"), "blue": np.full((N, N), 0.04, "float32")}
    return {"idx": optical.scene_indices(b), "valid": np.full((N, N), valid), "bands": b}


def test_reflectance_offset_by_processing_baseline():
    dn = np.array([[0, 1000, 3000]], "uint16")
    old = optical.to_reflectance(dn, {}, "03.01")
    new = optical.to_reflectance(dn, {}, "05.10")
    assert np.isnan(old[0, 0]) and abs(old[0, 2] - 0.3) < 1e-6
    assert abs(new[0, 1] - 0.0) < 1e-6 and abs(new[0, 2] - 0.2) < 1e-6
    meta = {"raster:bands": [{"scale": 0.0001, "offset": -0.1}]}
    assert abs(optical.to_reflectance(dn, meta, None)[0, 2] - 0.2) < 1e-6


def test_max_extent_catches_short_lived_flood():
    """後期間の 3 枚のうち 1 枚だけ冠水 → 中央値では消えるが最大浸水範囲では残る。"""
    land = scene(green=0.06, nir=0.30)
    wet = scene(green=0.10, nir=0.03)
    before = optical.composite([land, land])
    after = optical.composite([land, wet, land])
    masks, valid = optical.change_masks(before, after)
    assert masks["new_water_frac"].all() and valid.all()
    assert not masks["water_loss_frac"].any()


def test_permanent_water_is_not_new_water():
    lake = scene(green=0.10, nir=0.03)
    masks, _ = optical.change_masks(optical.composite([lake]), optical.composite([lake]))
    assert not masks["new_water_frac"].any()


def test_clouds_are_excluded():
    land = scene(green=0.06, nir=0.30)
    cloudy_wet = scene(green=0.10, nir=0.03, valid=False)
    masks, valid = optical.change_masks(optical.composite([land]), optical.composite([cloudy_wet]))
    assert not valid.any() and not masks["new_water_frac"].any()


def test_veg_loss():
    forest = scene(green=0.08, nir=0.40, red=0.04)
    cleared = scene(green=0.10, nir=0.20, red=0.15)
    masks, _ = optical.change_masks(optical.composite([forest]), optical.composite([cleared]))
    assert masks["veg_loss_frac"].all()


# ---------- 気象 ----------
def test_precip_anomaly_detects_extreme_rain():
    daily = {}
    for y in range(2009, 2025):
        for d in range(10, 20):
            daily[date(y, 4, d)] = 1.0 + (y % 3)
    for d in range(13, 18):
        daily[date(2024, 4, d)] = 50.0
    value, history, (z, lo, hi) = weather.precip_anomaly(daily, date(2024, 4, 13), date(2024, 4, 17))
    assert value == 250.0 and len(history) == 15 and z > 10 and lo <= z <= hi


def test_precip_missing_window_is_no_data():
    with pytest.raises(Exception) as e:
        weather.precip_anomaly({}, date(2024, 4, 13), date(2024, 4, 17))
    assert e.type.__name__ == "NoData"


# ---------- SAR ----------
def test_sar_flood_and_bright_masks():
    before = np.full((N, N), -9.0)
    after_med = before.copy(); after_min = before.copy()
    after_min[:64] = -20.0          # 上半分は一時的に水面
    after_med[64:, :32] = 2.0        # 下の一角に強い散乱体
    masks, valid = sar.sar_masks(before, after_med, after_min)
    assert abs(masks["vv_drop_frac"].mean() - 0.5) < 1e-9
    assert abs(masks["vv_bright_gain_frac"].mean() - 0.125) < 1e-9 and valid.all()


def test_sar_request_uses_terrain_corrected_backscatter():
    body = sar.request_body([55.7, 24.2, 55.8, 24.3], ["2024-04-01", "2024-04-15"], "ASCENDING", 512)
    proc = body["input"]["data"][0]["processing"]
    assert proc["backCoeff"] == "GAMMA0_TERRAIN" and proc["orthorectify"] is True
    assert body["input"]["data"][0]["dataFilter"]["orbitDirection"] == "ASCENDING"


# ---------- 契約 ----------
def test_every_signature_measure_is_produced_by_a_probe():
    produced = {
        "optical_change": set(optical.BANDS_FOR),
        "sar_change": {"vv_drop_frac", "vv_bright_gain_frac"},
        "weather_anomaly": {"precip_z"},
    }
    for probe, ms in known_measures().items():
        assert probe in PROBES and ms <= produced[probe], (probe, ms - produced.get(probe, set()))


def hyp(event_type="flood"):
    return Hypothesis(claim="test", event_type=event_type,
                      aoi=AOI(place="Al Ain", lat=24.2, lon=55.7, half_km=4),
                      timeframe=TimeFrame.around(date(2024, 4, 16), today=date(2026, 1, 1)),
                      signatures=default_signatures(event_type))


def test_plan_groups_measures_per_probe_with_seasonal_control(tmp_path):
    jobs = {j.probe: j for j in jobs_for(hyp(), tmp_path)}
    assert set(jobs) == {"optical_change", "sar_change", "weather_anomaly"}
    assert jobs["optical_change"].params["control"]["after"][0].startswith("2023-04")
    assert jobs["weather_anomaly"].params["measures"] == ["precip_z"]


def test_plan_reports_unsupported_signatures():
    h = hyp()
    h.signatures.append(Signature(id="x.lights", probe="night_lights", measure="radiance_drop_frac",
                                  sensor="viirs", direction="increase", min_effect=0.1))
    assert unsupported(h) == ["x.lights"]


# ---------- 実行層（偽プローブでローカル実行） ----------
OK = '''import os
from _common import emit, load_params, measure, run
def main():
    load_params()
    os.makedirs("out", exist_ok=True)
    open("out/x.png", "wb").write(b"png")
    emit("{probe}", {{"new_water_frac": measure(0.1, 0.05, 0.15)}}, 0.9, ["scene-1"], ["x.png"])
run(main)
'''
NODATA = '''from _common import NoData, run
def main():
    raise NoData("雲しかない")
run(main)
'''
BROKEN = '''from _common import emit, measure, run
def main():
    emit("{probe}", {{"new_water_frac": measure(0.1, 0.05, 0.15)}}, 0.9 BUG)
run(main)
'''


def fake_source(tmp_path, name, body):
    src = tmp_path / f"src_{name}"
    src.mkdir()
    for f in ("_common.py", "_stats.py"):
        (src / f).write_bytes((config.PROBES_DIR / f).read_bytes())
    (src / f"{name}.py").write_text(body.format(probe=name))
    return src


def test_runner_success_nodata_and_repair(tmp_path):
    run_dir = tmp_path / "run"
    jobs = [
        ProbeJob("optical_change", {"out_dir": "out"}, run_dir, fake_source(tmp_path, "optical_change", OK)),
        ProbeJob("weather_anomaly", {"out_dir": "out"}, run_dir, fake_source(tmp_path, "weather_anomaly", NODATA)),
        ProbeJob("sar_change", {"out_dir": "out"}, run_dir, fake_source(tmp_path, "sar_change", BROKEN)),
    ]
    calls = []

    async def repair(job, log):  # CodeAF の代役: 構文エラーを直す
        calls.append((job.probe, "SyntaxError" in log))
        job.script.write_text(job.script.read_text().replace(" BUG", ""))
        return True

    res = {r.probe: r for r in asyncio.run(run_jobs(jobs, LocalExecutor(), repair))}
    ok = res["optical_change"]
    assert ok.error is None and ok.measures["new_water_frac"].lo == 0.05 and len(ok.code_sha256) == 64
    assert Path(ok.artifacts["x.png"]).read_bytes() == b"png"
    assert res["weather_anomaly"].error.startswith("NO_DATA") and res["weather_anomaly"].repairs == 0
    assert res["sar_change"].error is None and res["sar_change"].repairs == 1
    assert calls == [("sar_change", True)]  # データ不足は修復に回さない


def test_runner_gives_up_after_max_repairs(tmp_path):
    job = ProbeJob("sar_change", {"out_dir": "out"}, tmp_path / "run", fake_source(tmp_path, "sar_change", BROKEN))

    async def useless_repair(job, log):
        return True

    [r] = asyncio.run(run_jobs([job], LocalExecutor(), useless_repair))
    assert r.error.startswith("exit 1") and r.repairs == 2


def test_code_hash_changes_when_repaired(tmp_path):
    job = ProbeJob("optical_change", {"out_dir": "out"}, tmp_path / "run", fake_source(tmp_path, "optical_change", OK))
    [a] = asyncio.run(run_jobs([job], LocalExecutor()))
    job.script.write_text(job.script.read_text() + "\n# patched\n")
    [b] = asyncio.run(run_jobs([job], LocalExecutor()))
    assert a.code_sha256 != b.code_sha256


# ---------- 光学プローブの main を通しで（通信だけ偽物） ----------
class FakeAsset:
    def __init__(self, href):
        self.href, self.extra_fields = href, {"raster:bands": [{"scale": 0.0001, "offset": 0.0}]}


class FakeItem:
    def __init__(self, id_, wet):
        self.id, self.properties = id_, {"eo:cloud_cover": 5, "s2:processing_baseline": "05.10"}
        bands = ["red", "green", "blue", "nir", "swir16", "swir22", "scl"]
        self.assets = {b: FakeAsset(f"{id_}|{b}|{int(wet)}") for b in bands}


def fake_read(href, g, resampling):
    _id, band, wet = href.split("|")
    size = g[2]
    arr = np.full((size, size), {"red": 500, "green": 600, "blue": 400, "nir": 3000,
                                 "swir16": 2000, "swir22": 1500, "scl": 4}[band], "uint16")
    if wet == "1" and band in ("green", "nir"):  # 左 1/4 が冠水
        arr[:, : size // 4] = 1000 if band == "green" else 300
    return arr


def test_optical_main_end_to_end(tmp_path, monkeypatch, capsys):
    import json
    windows = {}

    def fake_search(aoi, window, max_cloud, order="cloud"):
        key = tuple(window)
        windows[key] = True
        is_target_after = window[0].startswith("2024-04-16")
        return [FakeItem(f"S2_{window[0]}_{i}", wet=is_target_after and i == 0) for i in range(2)]

    monkeypatch.setattr(optical, "search", fake_search)
    monkeypatch.setattr(optical, "read_asset", fake_read)
    monkeypatch.chdir(tmp_path)
    job = jobs_for(hyp(), tmp_path)[0]
    assert job.probe == "optical_change"
    (tmp_path / "params.json").write_text(json.dumps({**job.params, "size": 128}))
    monkeypatch.setattr(sys, "argv", ["optical_change.py", "params.json"])
    optical.main()

    result = json.loads((tmp_path / "out" / "result.json").read_text())
    m = result["measures"]["new_water_frac"]
    assert abs(m["value"] - 0.25) < 1e-6 and m["detail"]["control_available"]
    assert len(windows) == 4 and len(result["scene_ids"]) == 8
    for f in result["artifacts"]:
        assert (tmp_path / "out" / f).stat().st_size > 0
