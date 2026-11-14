"""環境変数を 1 か所で読む。キーは .env だけに置く。"""
import os
from pathlib import Path

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

ROOT = Path(__file__).resolve().parent.parent
RUNS_DIR = Path(os.environ.get("WITNESS_RUNS_DIR", ROOT / "runs"))
PROBES_DIR = Path(__file__).resolve().parent / "probes"

DAYTONA_API_KEY = os.environ.get("DAYTONA_API_KEY", "")
# scripts/build_snapshot.py で作るスナップショット名。空なら毎回 pip install（遅い）
WITNESS_SNAPSHOT = os.environ.get("WITNESS_SNAPSHOT", "")
# 1 ならデータ取得先以外への通信を遮断する
RESTRICT_NETWORK = os.environ.get("WITNESS_RESTRICT_NETWORK", "1") == "1"

# Copernicus Data Space（SAR）。Daytona の組織 Secret 名を指定すると平文をサンドボックスに入れない
CDSE_CLIENT_ID = os.environ.get("CDSE_CLIENT_ID", "")
CDSE_CLIENT_SECRET = os.environ.get("CDSE_CLIENT_SECRET", "")
CDSE_SECRET_NAME = os.environ.get("CDSE_DAYTONA_SECRET", "")

TAVILY_API_KEY = os.environ.get("TAVILY_API_KEY", "")
NOSANA_BASE_URL = os.environ.get("NOSANA_BASE_URL", "").rstrip("/")
NOSANA_MODEL = os.environ.get("NOSANA_MODEL", "qwen-vl")
NOSANA_API_KEY = os.environ.get("NOSANA_API_KEY", "none")
AGENTFIELD_SERVER = os.environ.get("AGENTFIELD_SERVER", "http://localhost:8080")
CODEAF_VIA_NOSANA = os.environ.get("CODEAF_VIA_NOSANA", "0") == "1"
# 1 なら既存プローブで測れないシグネチャを CodeAF に新規作成させる
WITNESS_SYNTH = os.environ.get("WITNESS_SYNTH", "0") == "1"


def require(name: str, value: str) -> str:
    if not value:
        raise RuntimeError(f"{name} が未設定です。.env を確認してください。")
    return value
