"""地名 → 座標。LLM に座標を推測させず、公開ジオコーダで引く。"""
import httpx


def geocode(place: str) -> tuple[float, float, str] | None:
    r = httpx.get("https://nominatim.openstreetmap.org/search",
                  params={"q": place, "format": "json", "limit": 1},
                  headers={"User-Agent": "orbital-witness/0.2 (hackathon)"}, timeout=15)
    r.raise_for_status()
    hits = r.json()
    if not hits:
        return None
    return float(hits[0]["lat"]), float(hits[0]["lon"]), hits[0].get("display_name", place)
