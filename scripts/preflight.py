"""4 社＋AgentField を本物の API で 1 つずつ確認する（前日と当日の朝に実行）。

    python scripts/preflight.py                  # 全部
    python scripts/preflight.py nosana daytona   # 一部だけ
"""
import asyncio
import shutil
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from witness import config  # noqa: E402


def tavily():
    from witness.scout import scan
    r = scan("Dubai floods April 2024")
    if r.get("skipped"):  # 任意。無くても観測だけで判定できる
        return f"⚠️ 省略（{r['skipped'][:120]}）— 報道なしで続行します"
    assert r["sources"], "検索結果が空"
    return f"{len(r['sources'])} 件 / 先頭: {r['sources'][0]['title'][:50]}"


def nosana():
    from openai import OpenAI
    c = OpenAI(base_url=config.require("NOSANA_BASE_URL", config.NOSANA_BASE_URL), api_key=config.NOSANA_API_KEY)
    models = [m.id for m in c.models.list().data]
    assert config.NOSANA_MODEL in models, f"{config.NOSANA_MODEL} が無い: {models}"
    t = time.time()
    out = c.chat.completions.create(model=config.NOSANA_MODEL, max_tokens=20,
                                    messages=[{"role": "user", "content": "「準備完了」とだけ返して"}])
    return f"{out.choices[0].message.content!r}（{time.time() - t:.1f} 秒）"


def daytona():
    """サンドボックスを作り、データ取得先に届くかを確かめる。
    RESTRICT_NETWORK=1 のときは、許可外のドメインが遮断されることも確かめる。"""
    from daytona import CreateSandboxFromSnapshotParams, Daytona, DaytonaConfig
    d = Daytona(DaytonaConfig(api_key=config.require("DAYTONA_API_KEY", config.DAYTONA_API_KEY)))
    targets = {
        "open-meteo": "https://archive-api.open-meteo.com/v1/archive?latitude=0&longitude=0"
                      "&start_date=2024-01-01&end_date=2024-01-02&daily=precipitation_sum",
        "earth-search": "https://earth-search.aws.element84.com/v1/collections/sentinel-2-l2a",
        "s2-cogs": "https://sentinel-cogs.s3.us-west-2.amazonaws.com/",
        "pypi": "https://pypi.org/simple/rasterio/",
    }
    kw = {"ephemeral": True}
    if config.RESTRICT_NETWORK:
        kw["domain_allow_list"] = "archive-api.open-meteo.com"
        targets = {"open-meteo": targets["open-meteo"], "example.com": "https://example.com"}
    params = CreateSandboxFromSnapshotParams(snapshot=config.WITNESS_SNAPSHOT, **kw) if config.WITNESS_SNAPSHOT \
        else CreateSandboxFromSnapshotParams(language="python", **kw)
    t = time.time()
    sb = d.create(params, timeout=180)
    try:
        probe = ("import urllib.request as u, urllib.error as e\n"
                 "def ok(x):\n"
                 "    try: u.urlopen(x, timeout=10); return 'OPEN'\n"
                 "    except e.HTTPError: return 'OPEN'\n"
                 "    except Exception: return 'BLOCKED'\n"
                 f"print(' '.join(ok(x) for x in {list(targets.values())!r}))")
        r = sb.process.code_run(probe)
        res = dict(zip(targets, (r.result or "").split()[-len(targets):]))
        if config.RESTRICT_NETWORK:
            assert res.get("open-meteo") == "OPEN", f"許可したドメインに届かない: {r.result}"
            assert res.get("example.com") == "BLOCKED", "許可していないドメインに届いてしまう（通信制限が効いていない）"
        else:
            # PREFETCH=1 なら STAC 検索と気象 API は手元で引くので、サンドボックスは S3 の画素だけ読めればよい
            need = ["s2-cogs"] if config.PREFETCH else list(targets)
            if not config.WITNESS_SNAPSHOT:
                need.append("pypi")
            blocked = [k for k in need if res.get(k) != "OPEN"]
            assert not blocked, f"サンドボックスから届かない取得先: {blocked}（Daytona のティア制限の可能性）"
        return f"sandbox {sb.id} 起動 {time.time() - t:.0f} 秒 / " + " ".join(f"{k}:{v}" for k, v in res.items())
    finally:
        d.delete(sb)


def codeaf():
    from agentfield import Agent
    from witness.llm import codeaf_harness_kwargs
    app = Agent(node_id="preflight", agentfield_server=config.AGENTFIELD_SERVER, dev_mode=True)
    ws = Path(tempfile.mkdtemp())
    (ws / "hello.py").write_text("print('hello'\n")
    r = asyncio.run(app.harness("hello.py の構文エラーを直して", provider="codeaf", cwd=str(ws), max_turns=6,
                                **codeaf_harness_kwargs()))
    fixed = (ws / "hello.py").read_text().strip()
    shutil.rmtree(ws, ignore_errors=True)
    assert fixed == "print('hello')", f"直っていない: {fixed!r} / {r.error_message}"
    return f"修復成功（{'Nosana' if config.CODEAF_VIA_NOSANA else 'OpenRouter'} 経由、{r.num_turns} ターン）"


def agentfield():
    from agentfield import Agent
    app = Agent(node_id="preflight", agentfield_server=config.AGENTFIELD_SERVER, dev_mode=True)
    found = app.discover(tags=["probe"]).json
    probes = [r.id for c in found.capabilities for r in c.reasoners if r.id.startswith("probe_")]
    assert probes, "プローブが見つからない（nodes.lab を起動したか？）"
    return f"control plane OK / 発見したプローブ: {', '.join(probes)}"


if __name__ == "__main__":
    names = sys.argv[1:] or ["tavily", "nosana", "daytona", "codeaf", "agentfield"]
    ok = True
    for n in names:
        try:
            print(f"✅ {n:10s} {globals()[n]()}")
        except Exception as e:
            ok = False
            print(f"❌ {n:10s} {type(e).__name__}: {e}")
    sys.exit(0 if ok else 1)
