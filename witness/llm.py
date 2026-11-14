"""[Nosana] すべての LLM / VLM 推論の行き先。

Nosana 上の vLLM（OpenAI 互換）を LiteLLM の openai/ ルートで指す。
AgentField の各ノードはこの AIConfig を使うので、app.ai の呼び出しはすべて Nosana の GPU で動く。
CodeAF も CODEAF_VIA_NOSANA=1 なら同じエンドポイントを使う。
"""
from agentfield import AIConfig

from . import config


def nosana_ai_config(temperature: float = 0.2, max_tokens: int = 1500) -> AIConfig:
    if config.LLM_BACKEND == "openrouter":  # 退避先（WITNESS_LLM=openrouter）
        return AIConfig(model=f"openai/{config.OPENROUTER_MODEL}", api_base="https://openrouter.ai/api/v1",
                        api_key=config.require("OPENROUTER_API_KEY", config.OPENROUTER_API_KEY),
                        temperature=temperature, max_tokens=max_tokens, retry_attempts=2, timeout=180)
    return AIConfig(
        model=f"openai/{config.NOSANA_MODEL}",
        # 未設定でもノードは起動できるようにし、初回の推論で接続エラーとして気付けるようにする
        api_base=config.NOSANA_BASE_URL or "http://nosana-not-configured.invalid/v1",
        api_key=config.NOSANA_API_KEY or "none",
        temperature=temperature,
        max_tokens=max_tokens,
        retry_attempts=2,
        timeout=180,
    )


def codeaf_harness_kwargs() -> dict:
    """CodeAF を Nosana の自前モデルで回すときの環境変数とモデル名。"""
    if not config.CODEAF_VIA_NOSANA:
        return {}
    return {"env": {"OPENAI_API_KEY": config.NOSANA_API_KEY or "none", "CODEAF_BASE_URL": config.NOSANA_BASE_URL},
            "model": config.NOSANA_MODEL}
