"""SAR 変化プローブ（Sentinel-1 GRD / Copernicus Data Space Ecosystem、無料アカウント）。

雲を透過するので、冠水当日が曇っていても使える。各期間について
γ0 地形補正・オルソ補正済みの VV を、軌道ごとのモザイクから
[中央値, 最小値] の 2 バンドで取得する（最小値 = 期間中に一度でも暗くなった = 水面）。
前後で同じ軌道方向を使い、前年同時期との差の差をとる。

認証情報は Daytona Secrets で渡す想定（サンドボックス内の値は代替文字列で、
許可したホストへの通信時だけ本物に置き換わる）。
"""
import io
import json
import os
import urllib.parse
import urllib.request

import numpy as np

from _common import NoData, emit, load_params, measure, run, save_gray, save_overlay, bbox
from _stats import did_frac

TOKEN_URL = "https://identity.dataspace.copernicus.eu/auth/realms/CDSE/protocol/openid-connect/token"
PROCESS_URL = "https://sh.dataspace.copernicus.eu/api/v1/process"

EVALSCRIPT = """//VERSION=3
function setup() {
  return { input: [{ bands: ["VV", "dataMask"] }],
           output: { bands: 2, sampleType: "FLOAT32" }, mosaicking: "ORBIT" };
}
function evaluatePixel(samples) {
  var v = [];
  for (var i = 0; i < samples.length; i++) {
    if (samples[i].dataMask === 1 && samples[i].VV > 0) v.push(samples[i].VV);
  }
  if (v.length === 0) return [NaN, NaN];
  v.sort(function (a, b) { return a - b; });
  return [v[Math.floor(v.length / 2)], v[0]];
}
"""


# ---------- 純粋な計算（テスト対象） ----------
def to_db(linear):
    with np.errstate(divide="ignore", invalid="ignore"):
        return 10 * np.log10(np.where(linear > 0, linear, np.nan))


def sar_masks(before_med_db, after_med_db, after_min_db):
    valid = np.isfinite(before_med_db) & np.isfinite(after_med_db) & np.isfinite(after_min_db)
    b, am, an = (np.nan_to_num(x, nan=0.0) for x in (before_med_db, after_med_db, after_min_db))
    return {
        # 平常時より 3dB 以上暗くなり、かつ水面らしい暗さ（-15dB 未満）
        "vv_drop_frac": (b - an > 3.0) & (an < -15.0) & valid,
        # 5dB 以上明るくなり、強い散乱体らしい明るさ（-5dB 超）
        "vv_bright_gain_frac": (am - b > 5.0) & (am > -5.0) & valid,
    }, valid


def request_body(bb, window, orbit, size):
    return {
        "input": {
            "bounds": {"bbox": bb, "properties": {"crs": "http://www.opengis.net/def/crs/EPSG/0/4326"}},
            "data": [{
                "type": "sentinel-1-grd",
                "dataFilter": {"timeRange": {"from": f"{window[0]}T00:00:00Z", "to": f"{window[1]}T23:59:59Z"},
                               "acquisitionMode": "IW", "polarization": "DV", "orbitDirection": orbit},
                "processing": {"backCoeff": "GAMMA0_TERRAIN", "orthorectify": True, "demInstance": "COPERNICUS_30"},
            }],
        },
        "output": {"width": size, "height": size,
                   "responses": [{"identifier": "default", "format": {"type": "image/tiff"}}]},
        "evalscript": EVALSCRIPT,
    }


# ---------- 入出力 ----------
def token():
    data = urllib.parse.urlencode({"grant_type": "client_credentials",
                                   "client_id": os.environ["CDSE_CLIENT_ID"],
                                   "client_secret": os.environ["CDSE_CLIENT_SECRET"]}).encode()
    with urllib.request.urlopen(urllib.request.Request(TOKEN_URL, data=data), timeout=30) as r:
        return json.load(r)["access_token"]


def fetch(tok, bb, window, orbit, size):
    import rasterio
    req = urllib.request.Request(PROCESS_URL, data=json.dumps(request_body(bb, window, orbit, size)).encode(),
                                 headers={"Authorization": f"Bearer {tok}", "Content-Type": "application/json",
                                          "Accept": "image/tiff"})
    with urllib.request.urlopen(req, timeout=180) as r:
        raw = r.read()
    with rasterio.MemoryFile(io.BytesIO(raw)) as mf, mf.open() as ds:
        med, mn = ds.read(1).astype("float32"), ds.read(2).astype("float32")
    if not np.isfinite(med).any():
        raise NoData(f"{window} ({orbit}) に Sentinel-1 の観測がありません")
    return to_db(med), to_db(mn)


def load_period(tok, bb, period, orbit, size):
    b_med, _ = fetch(tok, bb, period["before"], orbit, size)
    a_med, a_min = fetch(tok, bb, period["after"], orbit, size)
    return b_med, a_med, a_min


def main():
    p = load_params()
    aoi, out, size = p["aoi"], p.get("out_dir", "out"), p.get("size", 512)
    os.makedirs(out, exist_ok=True)
    wanted = [m for m in p["measures"] if m in ("vv_drop_frac", "vv_bright_gain_frac")] or ["vv_drop_frac"]
    tok, bb = token(), bbox(aoi)

    target, orbit, last = None, None, None
    for orbit in p.get("orbits", ["ASCENDING", "DESCENDING"]):  # 前後で同じ軌道方向がそろうものを使う
        try:
            target = load_period(tok, bb, p["target"], orbit, size)
            break
        except NoData as e:
            last = e
    if target is None:
        raise last or NoData("Sentinel-1 の観測がありません")
    try:
        c_masks, c_valid = sar_masks(*load_period(tok, bb, p["control"], orbit, size))
    except NoData:
        c_masks, c_valid = {}, np.zeros((size, size), bool)

    t_masks, t_valid = sar_masks(*target)
    measures = {}
    for m in wanted:
        v, lo, hi, d = did_frac(t_masks[m], t_valid, c_masks.get(m, np.zeros_like(t_valid)), c_valid)
        measures[m] = measure(v, lo, hi, orbit=orbit, **d)

    save_gray(target[0], f"{out}/sar_before.png", -25, 0)
    save_gray(target[2], f"{out}/sar_after_min.png", -25, 0)
    artifacts = ["sar_before.png", "sar_after_min.png"]
    for m in wanted:
        save_overlay(f"{out}/sar_after_min.png", t_masks[m], f"{out}/change_{m}.png", color=(255, 90, 40))
        artifacts.append(f"change_{m}.png")
    windows = [p["target"]["before"], p["target"]["after"], p["control"]["before"], p["control"]["after"]]
    emit("sar_change", measures, t_valid.mean(),
         [f"cdse:s1grd:{orbit}:{w[0]}/{w[1]}" for w in windows], artifacts, out)


if __name__ == "__main__":
    run(main)
