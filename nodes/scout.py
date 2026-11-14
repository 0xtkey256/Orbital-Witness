"""witness-scout ノード — [Tavily] で集め、[Nosana] の LLM で各情報源の立場を分類する。"""
from datetime import date
from typing import Literal

from agentfield import Agent
from pydantic import BaseModel, Field

from witness import config, scout
from witness.llm import nosana_ai_config

app = Agent(node_id="witness-scout", agentfield_server=config.AGENTFIELD_SERVER,
            description="報道と公的機関の情報を、出来事の期間に絞って賛否両方向から集める",
            tags=["tavily", "research"], ai_config=nosana_ai_config(), dev_mode=True)


class Stance(BaseModel):
    url: str
    stance: Literal["support", "refute", "unrelated"]
    note: str = Field(description="判断理由（日本語で1文）")


class StanceList(BaseModel):
    items: list[Stance]


@app.reasoner(tags=["research", "tavily"])
async def scan(claim: str) -> dict:
    """第 1 段: 場所・日付・出来事の種類を特定するための広い検索。"""
    res = scout.scan(claim)
    app.note(f"Tavily: {len(res['sources'])} 件の報道を取得", tags=["tavily"])
    return res


@app.reasoner(tags=["research", "tavily"])
async def corroborate(claim: str, place: str, event_date: str) -> dict:
    """第 2・3 段: 期間を絞った賛否両方向＋公的機関の検索、本文抽出、立場の分類。"""
    res = scout.corroborate(claim, place, date.fromisoformat(event_date))
    if res["sources"]:
        listing = "\n\n".join(f"URL: {s['url']}\n題: {s['title']}\n本文: {(s.get('body') or s['snippet'])[:900]}"
                              for s in res["sources"][:10])
        stances: StanceList = await app.ai(
            system="あなたはファクトチェッカーです。各記事が主張を支持するか、否定・訂正するか、無関係かを判定します。"
                   "記事に書かれていることだけで判断します。",
            user=f"主張: {claim}\n\n{listing}",
            schema=StanceList,
        )
        by_url = {s.url: s for s in stances.items}
        for s in res["sources"]:
            st = by_url.get(s["url"])
            s["stance"], s["stance_note"] = (st.stance, st.note) if st else ("unrelated", "")
    counts = {k: sum(1 for s in res["sources"] if s.get("stance") == k) for k in ("support", "refute", "unrelated")}
    app.note(f"Tavily: 支持 {counts['support']} / 否定 {counts['refute']} / 無関係 {counts['unrelated']}"
             f"（公的機関 {sum(1 for s in res['sources'] if s.get('authoritative'))} 件）", tags=["tavily"])
    return {**res, "stance_counts": counts}


if __name__ == "__main__":
    app.run(port=8101)
