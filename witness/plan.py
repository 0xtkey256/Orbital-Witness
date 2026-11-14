"""仮説（事前登録済み）→ プローブごとの実行ジョブ。

同じプローブを使うシグネチャはまとめて 1 回で測る（measures にキーを並べる）。
対象期間と、前年同時期の対照期間を両方渡す。
"""
from __future__ import annotations

from pathlib import Path

from .sandbox import PROBES, ProbeJob
from .schemas import Hypothesis


def _period(tf):
    return {"before": [d.isoformat() for d in tf.before], "after": [d.isoformat() for d in tf.after]}


def jobs_for(hyp: Hypothesis, run_dir: Path, size: int = 512, max_cloud: int = 40) -> list[ProbeJob]:
    measures: dict[str, list[str]] = {}
    for sig in hyp.signatures:
        if sig.probe in PROBES:
            measures.setdefault(sig.probe, [])
            if sig.measure not in measures[sig.probe]:
                measures[sig.probe].append(sig.measure)
    common = {
        "aoi": hyp.aoi.model_dump(),
        "event_date": hyp.timeframe.event_date.isoformat(),
        "target": _period(hyp.timeframe),
        "control": _period(hyp.timeframe.seasonal()),
        "size": size,
        "max_cloud": max_cloud,
        "out_dir": "out",
    }
    return [ProbeJob(probe=p, params={**common, "measures": m}, run_dir=run_dir) for p, m in measures.items()]


def unsupported(hyp: Hypothesis) -> list[str]:
    """既存プローブで測れないシグネチャ（Part 4 で CodeAF に新規作成させる候補）。"""
    return [s.id for s in hyp.signatures if s.probe not in PROBES]
