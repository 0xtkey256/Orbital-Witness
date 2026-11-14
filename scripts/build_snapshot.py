"""地理空間ライブラリ入りの Daytona スナップショットを作る（前日に 1 回だけ）。

毎回の pip install（数分）が無くなり、サンドボックスは数秒で解析を始められる。
作ったら .env に WITNESS_SNAPSHOT=orbital-witness-geo を設定する。
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from daytona import CreateSnapshotParams, Daytona, DaytonaConfig, Image  # noqa: E402

from witness import config  # noqa: E402
from witness.sandbox import DEPS  # noqa: E402

NAME = sys.argv[1] if len(sys.argv) > 1 else "orbital-witness-geo"

if __name__ == "__main__":
    d = Daytona(DaytonaConfig(api_key=config.require("DAYTONA_API_KEY", config.DAYTONA_API_KEY)))
    image = Image.debian_slim("3.12").pip_install(DEPS)
    d.snapshot.create(CreateSnapshotParams(name=NAME, image=image), on_logs=lambda line: print(line, end=""))
    print(f"\nスナップショット {NAME} を作成しました。.env に WITNESS_SNAPSHOT={NAME} を設定してください。")
