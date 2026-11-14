"""プローブ共通部品（サンドボックス内で動く。numpy / Pillow のみに依存）。

プローブの契約
  入力 : python <probe>.py params.json
  出力 : out/result.json と標準出力の RESULT_JSON= 行
  終了 : 0=成功 / 3=データ不足（コードは正しい。CodeAF で直さない）/ その他=コードの不具合
"""
import json
import math
import os
import sys

import numpy as np

EXIT_NO_DATA = 3


class NoData(Exception):
    """観測が無い・雲で使えないなど、コードではなくデータ側の問題。"""


def load_params() -> dict:
    with open(sys.argv[1] if len(sys.argv) > 1 else "params.json") as f:
        return json.load(f)


def bbox(aoi: dict) -> list:
    dlat = aoi["half_km"] / 111.0
    dlon = aoi["half_km"] / (111.0 * max(math.cos(math.radians(aoi["lat"])), 0.01))
    return [aoi["lon"] - dlon, aoi["lat"] - dlat, aoi["lon"] + dlon, aoi["lat"] + dlat]


def utm_epsg(lat: float, lon: float) -> int:
    zone = int((lon + 180) // 6) + 1
    return (32600 if lat >= 0 else 32700) + zone


def measure(value, lo, hi, **detail) -> dict:
    clean = lambda x: None if x is None or (isinstance(x, float) and math.isnan(x)) else float(x)
    return {"value": clean(value), "lo": clean(lo), "hi": clean(hi), "detail": detail}


def emit(probe: str, measures: dict, valid_ratio: float, scene_ids=(), artifacts=(), out="out"):
    os.makedirs(out, exist_ok=True)
    result = {"probe": probe, "measures": measures, "valid_ratio": float(valid_ratio),
              "scene_ids": list(scene_ids), "artifacts": list(artifacts)}
    with open(os.path.join(out, "result.json"), "w") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    print("RESULT_JSON=" + json.dumps(result, ensure_ascii=False))


def run(main):
    try:
        main()
    except NoData as e:
        print(f"NO_DATA: {e}")
        sys.exit(EXIT_NO_DATA)


# ---------- 画像 ----------
def save_rgb(r, g, b, path, max_reflectance=0.3):
    from PIL import Image
    rgb = np.stack([r, g, b], axis=-1)
    rgb = np.nan_to_num(np.clip(rgb / max_reflectance, 0, 1)) ** (1 / 1.8)
    Image.fromarray((rgb * 255).astype("uint8")).save(path)


def save_gray(arr, path, lo, hi):
    from PIL import Image
    t = np.nan_to_num(np.clip((arr - lo) / (hi - lo), 0, 1))
    Image.fromarray((t * 255).astype("uint8")).save(path)


def save_overlay(base_path, mask, path, color=(30, 120, 255), alpha=0.6):
    """変化マスクを背景画像に重ねる。"""
    from PIL import Image
    base = np.asarray(Image.open(base_path).convert("RGB")).astype("float32")
    over = base.copy()
    over[mask] = (1 - alpha) * base[mask] + alpha * np.array(color, "float32")
    Image.fromarray(over.clip(0, 255).astype("uint8")).save(path)
