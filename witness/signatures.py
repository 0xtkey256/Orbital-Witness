"""観測シグネチャのオントロジー: 出来事の種類 → 物理的に何がどれだけ変わるはずか。

Planner（LLM）はここを出発点に追加・調整を提案できるが、最低限この既定値で
どの出来事も検証可能にする。数値は AOI に対する割合なので AOI の大きさに依存しない。

measure のキーは各プローブが返す量の名前と一致させる（probes/ 側の契約）。
"""
from __future__ import annotations

from .schemas import EventType, Signature

# (id, probe, measure, sensor, direction, min_effect, rationale)
_TABLE: dict[str, list[tuple]] = {
    "flood": [
        ("flood.new_water.s2", "optical_change", "new_water_frac", "s2", "increase", 0.005,
         "冠水域では NDWI が上がり、平常時は陸の画素が水になる。市街地を含む 8km 四方では"
         "冠水は面積の 1% 前後（数 km²）になるため、差の差で 0.5% を最小効果とする"),
        ("flood.vv_drop.s1", "sar_change", "vv_drop_frac", "s1", "increase", 0.02,
         "水面は鏡面反射で VV 後方散乱が 3dB 以上下がる。雲を透過する"),
        ("flood.precip.meteo", "weather_anomaly", "precip_z", "meteo", "increase", 2.0,
         "大規模冠水の直前には平年を大きく上回る降水がある"),
    ],
    "deforestation": [
        ("defo.veg_loss.s2", "optical_change", "veg_loss_frac", "s2", "increase", 0.02,
         "伐採地では NDVI>0.4 の画素が失われる"),
        ("defo.bare_gain.s2", "optical_change", "bare_gain_frac", "s2", "increase", 0.01,
         "裸地指数が上がる"),
    ],
    "fire": [
        ("fire.burned.s2", "optical_change", "burned_frac", "s2", "increase", 0.02,
         "焼失域は dNBR>0.27 になる"),
        ("fire.dry.meteo", "weather_anomaly", "precip_z", "meteo", "decrease", 0.5,
         "大規模火災の前は平年より乾燥していることが多い（弱い証拠）"),
    ],
    "construction": [
        ("cons.built_gain.s2", "optical_change", "built_gain_frac", "s2", "increase", 0.01,
         "造成地では NDBI が上がり植生が消える"),
        ("cons.bright_gain.s1", "sar_change", "vv_bright_gain_frac", "s1", "increase", 0.005,
         "建物や重機は強い散乱体として SAR で明るくなる"),
    ],
    "drought": [
        ("drought.water_loss.s2", "optical_change", "water_loss_frac", "s2", "increase", 0.05,
         "貯水池や湖の水面が縮む"),
        ("drought.precip.meteo", "weather_anomaly", "precip_z", "meteo", "decrease", 1.0,
         "少雨が続く"),
    ],
    "landslide": [
        ("slide.veg_loss.s2", "optical_change", "veg_loss_frac", "s2", "increase", 0.005,
         "崩壊地で植生が剥がれる"),
        ("slide.precip.meteo", "weather_anomaly", "precip_z", "meteo", "increase", 1.5,
         "豪雨が引き金になることが多い"),
    ],
    "other": [],
}


def default_signatures(event_type: EventType) -> list[Signature]:
    return [
        Signature(id=i, probe=p, measure=m, sensor=s, direction=d, min_effect=e, rationale=r)
        for (i, p, m, s, d, e, r) in _TABLE.get(event_type, [])
    ]


def known_measures() -> dict[str, set[str]]:
    """プローブごとに返すべき measure の一覧（プローブの契約テストに使う）。"""
    out: dict[str, set[str]] = {}
    for rows in _TABLE.values():
        for (_, probe, measure, *_rest) in rows:
            out.setdefault(probe, set()).add(measure)
    return out
