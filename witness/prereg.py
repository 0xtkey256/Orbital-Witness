"""事前登録: データを見る前に仮説と閾値を固定し、ハッシュで封をする。

封をした後に閾値やシグネチャを書き換えると verify が失敗し、
封より前に取得された観測結果は check_order で弾かれる。
"""
from __future__ import annotations

import hashlib
import json

from .schemas import Preregistration, ProbeResult, utcnow


class PreregistrationError(RuntimeError):
    pass


def canonical(prereg: Preregistration) -> bytes:
    body = prereg.model_dump(mode="json", exclude={"sha256"})
    return json.dumps(body, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode()


def seal(prereg: Preregistration) -> Preregistration:
    if prereg.sha256:
        raise PreregistrationError("すでに封印済みです")
    sealed = prereg.model_copy(update={"sealed_at": utcnow()})
    return sealed.model_copy(update={"sha256": hashlib.sha256(canonical(sealed)).hexdigest()})


def verify(prereg: Preregistration) -> None:
    if not prereg.sha256 or not prereg.sealed_at:
        raise PreregistrationError("封印されていません")
    actual = hashlib.sha256(canonical(prereg)).hexdigest()
    if actual != prereg.sha256:
        raise PreregistrationError(f"封印後に改変されています: {prereg.sha256[:12]} != {actual[:12]}")


def check_order(prereg: Preregistration, results: list[ProbeResult]) -> None:
    """観測は封印の後でなければならない（見てから予測を書く、を禁止）。"""
    verify(prereg)
    for r in results:
        if r.finished_at <= prereg.sealed_at:
            raise PreregistrationError(f"{r.probe} の結果が封印より前の時刻です")


def short(prereg: Preregistration) -> str:
    return (prereg.sha256 or "")[:12]
