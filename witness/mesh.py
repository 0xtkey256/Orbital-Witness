"""ノード間呼び出し。通常は AgentField の control plane 経由（トレースと DAG に載る）。

WITNESS_DIRECT=1 のときは関数を直接呼ぶ（control plane が不調なときのデモ用の退避路）。
"""
import os

DIRECT = os.environ.get("WITNESS_DIRECT") == "1"


async def call(app, target: str, fn, **kwargs) -> dict:
    if DIRECT:
        return await fn(**kwargs)
    return await app.call(target, **kwargs)
