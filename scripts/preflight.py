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
    """サンドボックスを作り、許可ドメインは通り・それ以外は遮断されることを確かめる。"""
    from daytona import CreateSandboxFromSnapshotParams, Daytona, DaytonaConfig
    d = Daytona(DaytonaConfig(api_key=config.require("DAYTONA_API_KEY", config.DAYTONA_API_KEY)))
    kw = {"domain_allow_list": "archive-api.open-meteo.com", "ephemeral": True}
    params = CreateSandboxFromSnapshotParams(snapshot=config.WITNESS_SNAPSHOT, **kw) if config.WITNESS_SNAPSHOT \
        else CreateSandboxFromSnapshotParams(language="python", **kw)
    t = time.time()
    sb = d.create(params, timeout=180)
    try:
        probe = ("import urllib.request as u\n"
                 "def ok(x):\n    try: u.urlopen(x, timeout=10); return 'OPEN'\n    except Exception as e: return 'BLOCKED'\n"
                 "print(ok('https://archive-api.open-meteo.com/v1/archive?latitude=0&longitude=0"
                 "&start_date=2024-01-01&end_date=2024-01-02&daily=precipitation_sum'), ok('https://example.com'))")
        r = sb.process.code_run(probe)
        allowed, blocked = (r.result or "").split()[-2:]
        assert allowed == "OPEN", f"許可したドメインに届かない: {r.result}"
        assert blocked == "BLOCKED", "許可していないドメインに届いてしまう（通信制限が効いていない）"
        return f"sandbox {sb.id} 起動 {time.time() - t:.0f} 秒 / 許可先 OPEN / 他 BLOCKED"
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
