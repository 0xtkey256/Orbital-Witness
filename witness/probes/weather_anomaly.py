"""気象異常プローブ（Open-Meteo Historical API / ERA5 再解析、キー不要）。

出来事の前後数日の積算降水量を、過去 N 年の同じ暦期間の分布と比べた z 値を返す。
空間解像度は約 10〜25km なので「その地域で異常な雨があったか」の証拠であって、
特定の街区の冠水の証拠ではない（台帳側で特異度を低く設定している理由）。
"""
import json
import urllib.parse
import urllib.request
from datetime import date, timedelta

import numpy as np

from _common import NoData, emit, load_params, measure, run
from _stats import anomaly_z

API = "https://archive-api.open-meteo.com/v1/archive"
YEARS_BACK = 15


# ---------- 純粋な計算（テスト対象） ----------
def shift_year(d: date, years: int) -> date:
    try:
        return d.replace(year=d.year - years)
    except ValueError:
        return d.replace(year=d.year - years, day=28)


def window_sum(daily: dict, start: date, end: date):
    """欠測が 2 割を超える窓は None。"""
    vals, n = [], (end - start).days + 1
    for i in range(n):
        v = daily.get(start + timedelta(days=i))
        if v is not None:
            vals.append(v)
    return float(np.sum(vals)) if len(vals) >= 0.8 * n else None


def precip_anomaly(daily: dict, start: date, end: date, years_back: int = YEARS_BACK):
    value = window_sum(daily, start, end)
    if value is None:
        raise NoData("対象期間の降水データが欠けています")
    history = [window_sum(daily, shift_year(start, y), shift_year(end, y)) for y in range(1, years_back + 1)]
    history = [h for h in history if h is not None]
    z, lo, hi = anomaly_z(value, history)
    return value, history, (z, lo, hi)


# ---------- 入出力 ----------
def fetch_daily(lat, lon, start: date, end: date) -> dict:
    q = urllib.parse.urlencode({"latitude": lat, "longitude": lon, "start_date": start.isoformat(),
                                "end_date": end.isoformat(), "daily": "precipitation_sum", "timezone": "UTC"})
    with urllib.request.urlopen(f"{API}?{q}", timeout=60) as r:
        d = json.load(r)["daily"]
    return {date.fromisoformat(t): v for t, v in zip(d["time"], d["precipitation_sum"])}


def main():
    p = load_params()
    aoi, out = p["aoi"], p.get("out_dir", "out")
    ev = date.fromisoformat(p["event_date"])
    lead, lag = p.get("accum_days_before", 3), p.get("accum_days_after", 1)
    start, end = ev - timedelta(days=lead), ev + timedelta(days=lag)

    daily = fetch_daily(aoi["lat"], aoi["lon"], shift_year(start, YEARS_BACK), end)
    value, history, (z, lo, hi) = precip_anomaly(daily, start, end)
    n_days = (end - start).days + 1
    present = sum(1 for i in range(n_days) if daily.get(start + timedelta(days=i)) is not None)

    emit("weather_anomaly",
         {"precip_z": measure(z, lo, hi, precip_mm=value, window=[start.isoformat(), end.isoformat()],
                              climatology_mean_mm=float(np.mean(history)) if history else None,
                              history_years=len(history), source="Open-Meteo ERA5")},
         valid_ratio=present / n_days, scene_ids=[f"open-meteo:era5:{aoi['lat']:.3f},{aoi['lon']:.3f}"],
         artifacts=[], out=out)


if __name__ == "__main__":
    run(main)
