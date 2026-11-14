"""[Tavily] 報道・公的情報の収集。

方針: 報道は「仮説を立てる材料」であって判定の根拠ではない。
判定は衛星・気象の観測だけで出し、報道の賛否はレポートで並べて見せる
（「報道が言っていること」と「衛星が見たもの」の対比）。
"""
from __future__ import annotations

from datetime import date, timedelta
from typing import Optional

from tavily import TavilyClient

from . import config

AUTHORITATIVE = ["reliefweb.int", "emergency.copernicus.eu", "gdacs.org", "disasterscharter.org",
                 "earthobservatory.nasa.gov", "wmo.int"]
DEBUNK_HINT = "fact check OR debunked OR false OR misleading OR old video"

_client: Optional[TavilyClient] = None


def client() -> TavilyClient:
    global _client
    if _client is None:
        _client = TavilyClient(api_key=config.require("TAVILY_API_KEY", config.TAVILY_API_KEY))
    return _client


def _source(r: dict, query_kind: str) -> dict:
    return {"title": r.get("title", ""), "url": r["url"], "published": r.get("published_date", ""),
            "snippet": (r.get("content") or "")[:600], "score": r.get("score", 0.0), "found_by": query_kind}


def dedupe(sources: list[dict]) -> list[dict]:
    seen, out = set(), []
    for s in sorted(sources, key=lambda s: -float(s.get("score") or 0)):
        key = s["url"].split("#")[0].rstrip("/")
        if key not in seen:
            seen.add(key)
            out.append(s)
    return out


def event_window(event_date: date, before: int = 7, after: int = 30, today: Optional[date] = None) -> tuple[str, str]:
    today = today or date.today()
    return (event_date - timedelta(days=before)).isoformat(), min(event_date + timedelta(days=after), today).isoformat()


def scan(claim: str, tavily: Optional[TavilyClient] = None) -> dict:
    """第 1 段: 期間を絞らず、主張の場所・日付・出来事の種類を探る。"""
    t = tavily or client()
    res = t.search(claim, topic="news", search_depth="advanced", max_results=8, include_answer="advanced")
    return {"answer": res.get("answer", ""), "sources": dedupe([_source(r, "scan") for r in res.get("results", [])])}


def corroborate(claim: str, place: str, event_date: date, tavily: Optional[TavilyClient] = None,
                extract_top: int = 4) -> dict:
    """第 2・3 段: 出来事の期間に絞って、賛否両方向と公的機関の情報を集め、上位を本文抽出する。"""
    t = tavily or client()
    start, end = event_window(event_date)
    q_support = f"{claim} {place}"
    q_refute = f"{place} {claim} {DEBUNK_HINT}"
    support = t.search(q_support, topic="news", start_date=start, end_date=end, max_results=6)
    refute = t.search(q_refute, topic="news", start_date=start, end_date=end, max_results=6)
    official = t.search(f"{place} {event_date.isoformat()} disaster situation report", topic="general",
                        include_domains=AUTHORITATIVE, include_domains_mode="prefer",
                        start_date=start, end_date=end, max_results=5)
    sources = dedupe([_source(r, "support") for r in support.get("results", [])]
                     + [_source(r, "refute") for r in refute.get("results", [])]
                     + [_source(r, "official") for r in official.get("results", [])])
    for s in sources:
        s["authoritative"] = any(d in s["url"] for d in AUTHORITATIVE)

    urls = [s["url"] for s in sources[:extract_top]]
    if urls:
        ext = t.extract(urls=urls, format="text", query=claim, chunks_per_source=3)
        body = {r["url"]: (r.get("raw_content") or "")[:2500] for r in ext.get("results", [])}
        for s in sources:
            s["body"] = body.get(s["url"], "")
    return {"window": [start, end], "sources": sources}
