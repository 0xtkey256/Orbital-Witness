"""光学変化プローブ（Sentinel-2 L2A / Element 84 Earth Search、匿名アクセス）。

各期間で最大 MAX_SCENES 枚の低雲量シーンを共通の UTM グリッドに再投影し、
雲（SCL）を除いた中央値合成を作る。冠水だけは「期間中に一度でも水だった画素」
（最大浸水範囲）で判定する。対象期間の変化を、前年同時期の変化と差し引く（差の差）。
"""
import os
import warnings
from concurrent.futures import ThreadPoolExecutor

import numpy as np

from _common import NoData, bbox, emit, load_params, measure, run, save_overlay, save_rgb, utm_epsg
from _stats import did_frac

STAC_URL = "https://earth-search.aws.element84.com/v1"
COLLECTION = "sentinel-2-l2a"
MAX_SCENES = 4
CLOUD_SCL = (3, 8, 9, 10)  # 雲の影・雲（中/高）・巻雲
WATER_T = 0.1

BANDS_FOR = {
    "new_water_frac": {"green", "nir"},
    "water_loss_frac": {"green", "nir"},
    "veg_loss_frac": {"red", "nir"},
    "bare_gain_frac": {"red", "nir", "blue", "swir16"},
    "burned_frac": {"nir", "swir22"},
    "built_gain_frac": {"red", "nir", "swir16"},
}


# ---------- 純粋な計算（テスト対象） ----------
def nd(a, b):
    with np.errstate(divide="ignore", invalid="ignore"):
        return np.where((a + b) != 0, (a - b) / (a + b), np.nan)


def scene_indices(b: dict) -> dict:
    idx = {}
    if {"green", "nir"} <= b.keys():
        idx["ndwi"] = nd(b["green"], b["nir"])
    if {"red", "nir"} <= b.keys():
        idx["ndvi"] = nd(b["nir"], b["red"])
    if {"nir", "swir22"} <= b.keys():
        idx["nbr"] = nd(b["nir"], b["swir22"])
    if {"nir", "swir16"} <= b.keys():
        idx["ndbi"] = nd(b["swir16"], b["nir"])
    if {"red", "nir", "blue", "swir16"} <= b.keys():
        idx["bsi"] = nd(b["swir16"] + b["red"], b["nir"] + b["blue"])
    return idx


def composite(scenes: list) -> dict:
    """scenes: [{"idx": {...}, "valid": bool[], "bands": {...}}] → 中央値合成 + 最大浸水範囲。"""
    if not scenes:
        raise NoData("シーンがありません")
    out = {"valid": np.any([s["valid"] for s in scenes], axis=0)}
    for key in scenes[0]["idx"]:
        stack = np.stack([np.where(s["valid"], s["idx"][key], np.nan) for s in scenes])
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", RuntimeWarning)  # 全部雲の画素は NaN のままでよい
            out[key] = np.nanmedian(stack, axis=0)
        if key == "ndwi":
            out["water_any"] = np.any(np.nan_to_num(stack, nan=-1) > WATER_T, axis=0)
    for band in ("red", "green", "blue"):
        if band in scenes[0]["bands"]:
            stack = np.stack([np.where(s["valid"], s["bands"][band], np.nan) for s in scenes])
            with warnings.catch_warnings():
                warnings.simplefilter("ignore", RuntimeWarning)
                out[band] = np.nanmedian(stack, axis=0)
    return out


def change_masks(before: dict, after: dict) -> dict:
    g = lambda c, k: c[k]
    m = {}
    if "ndwi" in before and "ndwi" in after:
        m["new_water_frac"] = after["water_any"] & (np.nan_to_num(g(before, "ndwi"), nan=1) <= WATER_T)
        m["water_loss_frac"] = (np.nan_to_num(g(before, "ndwi"), nan=-1) > WATER_T) & (np.nan_to_num(g(after, "ndwi"), nan=1) <= 0.0)
    if "ndvi" in before and "ndvi" in after:
        b, a = np.nan_to_num(g(before, "ndvi"), nan=0), np.nan_to_num(g(after, "ndvi"), nan=1)
        m["veg_loss_frac"] = (b > 0.4) & (b - a > 0.2)
    if "bsi" in before and "bsi" in after:
        m["bare_gain_frac"] = (np.nan_to_num(g(after, "bsi") - g(before, "bsi"), nan=0) > 0.1) & (np.nan_to_num(g(after, "ndvi"), nan=1) < 0.25)
    if "nbr" in before and "nbr" in after:
        m["burned_frac"] = np.nan_to_num(g(before, "nbr") - g(after, "nbr"), nan=0) > 0.27
    if "ndbi" in before and "ndbi" in after:
        m["built_gain_frac"] = (np.nan_to_num(g(after, "ndbi") - g(before, "ndbi"), nan=0) > 0.1) & (np.nan_to_num(g(after, "ndvi"), nan=1) < 0.3)
    valid = before["valid"] & after["valid"]
    return {k: v & valid for k, v in m.items()}, valid


def to_reflectance(dn, asset_extra: dict, processing_baseline: str | None):
    """DN → 反射率。処理系 04.00 以降は +1000 のオフセットが入っている。"""
    rb = (asset_extra or {}).get("raster:bands") or [{}]
    scale, offset = rb[0].get("scale"), rb[0].get("offset")
    if scale is None:
        scale = 1e-4
        offset = -0.1 if (processing_baseline or "0") >= "04.00" else 0.0
    out = dn.astype("float32") * scale + (offset or 0.0)
    out[dn == 0] = np.nan  # 0 は nodata
    return out


# ---------- 入出力 ----------
def grid(aoi, size):
    from rasterio.transform import from_bounds
    from rasterio.warp import transform_bounds
    crs = f"EPSG:{utm_epsg(aoi['lat'], aoi['lon'])}"
    b = transform_bounds("EPSG:4326", crs, *bbox(aoi))
    return crs, from_bounds(*b, size, size), size


def read_asset(href, g, resampling):
    import rasterio
    from rasterio.enums import Resampling
    from rasterio.vrt import WarpedVRT
    crs, transform, size = g
    with rasterio.open(href) as src, WarpedVRT(src, crs=crs, transform=transform, width=size, height=size,
                                               resampling=getattr(Resampling, resampling)) as vrt:
        return vrt.read(1)


# オーケストレーター側で引いた STAC の検索結果（params["_prefetch"]）。あればネットに出ない
PREFETCH: dict = {}


# 冠水は数日で引く。事後の窓は「雲が少ない順」ではなく「出来事に近い順」に選ぶ
SHORT_LIVED = {"new_water_frac"}


def stac_key(window, max_cloud, order="cloud") -> str:
    return f"stac:{window[0]}/{window[1]}:lt{max_cloud}:{order}"


def pick(items, order):
    if order == "early":
        return sorted(items, key=lambda it: it.properties.get("datetime", ""))[:MAX_SCENES]
    return sorted(items, key=lambda it: it.properties.get("eo:cloud_cover", 100))[:MAX_SCENES]


def after_order(measures) -> str:
    return "early" if SHORT_LIVED & set(measures) else "cloud"


def search(aoi, window, max_cloud, order="cloud"):
    hit = PREFETCH.get(stac_key(window, max_cloud, order))
    if hit is not None:
        import pystac
        return [pystac.Item.from_dict(d) for d in hit]
    from pystac_client import Client
    items = Client.open(STAC_URL).search(
        collections=[COLLECTION], bbox=bbox(aoi), datetime=f"{window[0]}/{window[1]}",
        query={"eo:cloud_cover": {"lt": max_cloud}}, max_items=40).item_collection()
    return pick(items, order)


def load_window(aoi, window, bands, g, max_cloud, pool, order="cloud"):
    items = search(aoi, window, max_cloud, order)
    if not items:
        raise NoData(f"{window} に雲量 {max_cloud}% 未満のシーンがありません")
    jobs = {(it.id, b): pool.submit(read_asset, it.assets[b].href, g, "bilinear") for it in items for b in bands}
    jobs.update({(it.id, "scl"): pool.submit(read_asset, it.assets["scl"].href, g, "nearest") for it in items})
    scenes = []
    for it in items:
        pb = it.properties.get("s2:processing_baseline")
        bd = {b: to_reflectance(jobs[(it.id, b)].result(), it.assets[b].extra_fields, pb) for b in bands}
        scl = jobs[(it.id, "scl")].result()
        valid = ~np.isin(scl, CLOUD_SCL) & (scl > 0) & np.all([np.isfinite(v) for v in bd.values()], axis=0)
        scenes.append({"idx": scene_indices(bd), "valid": valid, "bands": bd})
    return composite(scenes), [it.id for it in items]


def prefetch(p) -> dict:
    """[オーケストレーター側で実行] 4 つの期間の STAC 検索を先に済ませる。
    サンドボックスは S3 の COG を読むだけになり、カタログ API への通信が要らなくなる。"""
    aoi, max_cloud, res = p["aoi"], p.get("max_cloud", 40), {}
    order_after = after_order(p.get("measures", []))
    for grp in ("target", "control"):
        for k in ("before", "after"):
            w = p.get(grp, {}).get(k)
            if w:
                order = order_after if k == "after" else "cloud"
                res[stac_key(w, max_cloud, order)] = [it.to_dict() for it in search(aoi, w, max_cloud, order)]
    return res


def main():
    p = load_params()
    PREFETCH.update(p.get("_prefetch", {}))
    aoi, out, size = p["aoi"], p.get("out_dir", "out"), p.get("size", 512)
    os.makedirs(out, exist_ok=True)
    wanted = [m for m in p["measures"] if m in BANDS_FOR] or ["new_water_frac"]
    bands = sorted({"red", "green", "blue"}.union(*(BANDS_FOR[m] for m in wanted)))
    g, max_cloud = grid(aoi, size), p.get("max_cloud", 40)

    oa = after_order(wanted)
    with ThreadPoolExecutor(16) as pool:
        tb, ids_b = load_window(aoi, p["target"]["before"], bands, g, max_cloud, pool)
        ta, ids_a = load_window(aoi, p["target"]["after"], bands, g, max_cloud, pool, oa)
        try:
            cb, ids_cb = load_window(aoi, p["control"]["before"], bands, g, max_cloud, pool)
            ca, ids_ca = load_window(aoi, p["control"]["after"], bands, g, max_cloud, pool, oa)
            c_masks, c_valid = change_masks(cb, ca)
        except NoData:
            ids_cb = ids_ca = []
            c_masks, c_valid = {}, np.zeros((size, size), bool)

    t_masks, t_valid = change_masks(tb, ta)
    measures = {}
    for m in wanted:
        cm = c_masks.get(m, np.zeros_like(t_valid))
        v, lo, hi, d = did_frac(t_masks[m], t_valid, cm, c_valid)
        measures[m] = measure(v, lo, hi, **d)

    save_rgb(tb["red"], tb["green"], tb["blue"], f"{out}/before.png")
    save_rgb(ta["red"], ta["green"], ta["blue"], f"{out}/after.png")
    artifacts = ["before.png", "after.png"]
    for m in wanted:
        save_overlay(f"{out}/after.png", t_masks[m], f"{out}/change_{m}.png")
        artifacts.append(f"change_{m}.png")

    emit("optical_change", measures, t_valid.mean(), ids_b + ids_a + ids_cb + ids_ca, artifacts, out)


if __name__ == "__main__":
    run(main)
