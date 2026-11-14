"""[CodeAF] プローブの修復と新規作成（AgentField の app.harness(provider="codeaf") 経由）。

修復のガード
- 直してよいのはプローブ本体だけ。_stats.py / _common.py の変更は捨てる
- プローブ内の数値定数（閾値）が消えた・変わった修復は拒否する
- 差分は runs/<id>/repairs/ に保存し、コードハッシュも変わる（証拠バンドルで監査できる）

CodeAF は git 管理下では別ブランチで作業するため、リポジトリ外の一時ディレクトリで作業させる。
"""
from __future__ import annotations

import ast
import difflib
import shutil
import tempfile
from collections import Counter
from pathlib import Path

from .llm import codeaf_harness_kwargs
from .sandbox import PROBES, SHARED, ProbeJob

CONTRACT = """プローブの契約:
- 起動: python <probe>.py params.json （params には aoi, event_date, target/control の before/after 期間, measures, out_dir）
- _common.py の load_params / emit / measure / run / NoData を使う。emit で out/result.json を書く
- データが無い・雲で使えないときは NoData を raise（終了コード 3）。コードのバグでは raise しない
- 依存は numpy / rasterio / pystac-client / pillow / 標準ライブラリのみ"""

REPAIR_PROMPT = """{probe}.py が Daytona サンドボックスで次のエラーで失敗しました。動くように最小限の修正をしてください。

制約:
- 修正してよいのは {probe}.py だけ。_stats.py と _common.py は変更しない
- 閾値や係数などの数値定数は変更・削除しない（科学的な判定基準は事前登録で固定されている）
- 入出力の契約を変えない

{contract}

エラー:
{log}
"""

SYNTH_PROMPT = """新しい観測プローブ {probe}.py を作ってください。

測る量: measures["{measure}"] — {rationale}
向き: 主張が本当なら {direction}
対象: {place}（lat={lat}, lon={lon}）、出来事の日付 {event_date}

要件:
- ファイル先頭に DATA_DOMAINS = ["..."] として、通信するホスト名をすべて列挙する（それ以外は遮断される）
- 対象期間と control（前年同時期）の両方を測り、_stats.did_frac か anomaly_z で値と 95% 区間を出す
- emit("{probe}", {{"{measure}": measure(value, lo, hi, ...)}}, valid_ratio, scene_ids, artifacts)
- キー不要の公開データだけを使う

{contract}

参考になる既存プローブ（weather_anomaly.py）:
```python
{example}
```
"""


def numeric_constants(src: str) -> Counter:
    tree = ast.parse(src)
    return Counter(n.value for n in ast.walk(tree)
                   if isinstance(n, ast.Constant) and isinstance(n.value, (int, float)) and not isinstance(n.value, bool))


def moved_goalposts(before: str, after: str) -> list:
    """修復前にあった数値定数のうち、修復後に消えたもの（= 変更・削除された閾値の疑い）。"""
    try:
        missing = numeric_constants(before) - numeric_constants(after)
    except SyntaxError:
        return []  # 修復前が構文エラーなら比較できない（構文修正は許可）
    return sorted(missing.elements(), key=str)


def _workspace(job: ProbeJob) -> Path:
    tmp = Path(tempfile.mkdtemp(prefix=f"ow-{job.probe}-"))
    for f in job.files() + [job.workdir / "params.json"]:
        shutil.copy(f, tmp / f.name)
    return tmp


async def codeaf_repair(app, job: ProbeJob, log: str, max_turns: int = 12) -> bool:
    """sandbox.run_jobs の repair コールバック。直せたら True。"""
    ws = _workspace(job)
    before = job.script.read_text()
    result = await app.harness(
        REPAIR_PROMPT.format(probe=job.probe, contract=CONTRACT, log=log[-3000:]),
        provider="codeaf", cwd=str(ws), max_turns=max_turns, **codeaf_harness_kwargs())
    after = (ws / job.script.name).read_text()

    notes = []
    for name in SHARED:  # 共通部品の変更は捨てる
        if (ws / name).read_bytes() != (job.workdir / name).read_bytes():
            notes.append(f"{name} の変更を破棄")
    moved = moved_goalposts(before, after)
    if moved:
        app.note(f"CodeAF の修復を拒否: 閾値 {moved} が変更されました", tags=["codeaf", "guard"])
        return False
    if after == before:
        app.note(f"CodeAF: {job.probe} に変更なし（{(result.error_message or '')[:120]}）", tags=["codeaf"])
        return False

    n = len(list((job.run_dir / "repairs").glob(f"{job.probe}-*.diff"))) + 1
    (job.run_dir / "repairs").mkdir(parents=True, exist_ok=True)
    diff = "".join(difflib.unified_diff(before.splitlines(True), after.splitlines(True),
                                        f"a/{job.script.name}", f"b/{job.script.name}"))
    (job.run_dir / "repairs" / f"{job.probe}-{n}.diff").write_text(diff)
    job.script.write_text(after)
    app.note(f"CodeAF が {job.probe} を修復（{diff.count(chr(10))} 行の差分）{' / ' + '、'.join(notes) if notes else ''}",
             tags=["codeaf"])
    return True


# ---------- 新規プローブ ----------
def declared_domains(src: str) -> list[str]:
    for node in ast.walk(ast.parse(src)):
        if isinstance(node, ast.Assign) and any(getattr(t, "id", "") == "DATA_DOMAINS" for t in node.targets):
            value = ast.literal_eval(node.value)
            if isinstance(value, list) and value and all(isinstance(x, str) and "/" not in x for x in value):
                return value
    raise ValueError("DATA_DOMAINS（ホスト名のリスト）が宣言されていません")


def validate_synthesized(src: str, probe: str, measure: str) -> list[str]:
    compile(src, f"{probe}.py", "exec")
    domains = declared_domains(src)
    for needle in ("emit(", f'"{measure}"', "load_params"):
        if needle not in src:
            raise ValueError(f"契約に必要な {needle} がありません")
    return domains


async def codeaf_synthesize(app, probe: str, measure: str, direction: str, rationale: str,
                            hyp_summary: dict, source_dir: Path, out_dir: Path, max_turns: int = 20) -> Path:
    """CodeAF に新しいプローブを書かせ、契約を満たせば PROBES に登録して置き場所を返す。"""
    ws = Path(tempfile.mkdtemp(prefix=f"ow-synth-{probe}-"))
    for name in SHARED + ["weather_anomaly.py"]:
        shutil.copy(source_dir / name, ws / name)
    prompt = SYNTH_PROMPT.format(probe=probe, measure=measure, direction=direction, rationale=rationale,
                                 contract=CONTRACT, example=(source_dir / "weather_anomaly.py").read_text(),
                                 **hyp_summary)
    await app.harness(prompt, provider="codeaf", cwd=str(ws), max_turns=max_turns, **codeaf_harness_kwargs())
    target = ws / f"{probe}.py"
    if not target.exists():
        raise RuntimeError(f"CodeAF が {probe}.py を作成しませんでした")
    domains = validate_synthesized(target.read_text(), probe, measure)
    out = out_dir
    out.mkdir(parents=True, exist_ok=True)
    for name in SHARED:
        shutil.copy(source_dir / name, out / name)
    shutil.copy(target, out / f"{probe}.py")
    PROBES[probe] = {"domains": domains, "synthesized": True}
    app.note(f"CodeAF が新しいプローブ {probe} を作成（通信先: {', '.join(domains)}）", tags=["codeaf", "synth"])
    return out
