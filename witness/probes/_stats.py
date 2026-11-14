"""numpy だけに依存する統計関数。Daytona サンドボックスにもそのままアップロードする。

隣り合う画素は独立ではない（空間的自己相関）ので、画素単位ではなく
ブロック単位でリサンプリングして信頼区間を出す。
"""
import numpy as np


def _block_sums(mask: np.ndarray, valid: np.ndarray, block: int):
    h, w = mask.shape
    hb, wb = h // block, w // block
    m = (mask & valid)[: hb * block, : wb * block].reshape(hb, block, wb, block).sum(axis=(1, 3)).ravel()
    v = valid[: hb * block, : wb * block].reshape(hb, block, wb, block).sum(axis=(1, 3)).ravel()
    keep = v > 0
    return m[keep].astype(float), v[keep].astype(float)


def _boot_fracs(m, v, n, rng):
    if len(v) == 0:
        return np.full(n, np.nan)
    idx = rng.integers(0, len(v), size=(n, len(v)))
    return m[idx].sum(axis=1) / v[idx].sum(axis=1)


def block_bootstrap_frac(mask, valid, block=32, n=1000, alpha=0.05, seed=0):
    """有効画素のうち mask が立つ割合と、その (1-alpha) 信頼区間。"""
    rng = np.random.default_rng(seed)
    m, v = _block_sums(np.asarray(mask, bool), np.asarray(valid, bool), block)
    if v.sum() == 0:
        return float("nan"), float("nan"), float("nan")
    boots = _boot_fracs(m, v, n, rng)
    return float(m.sum() / v.sum()), float(np.nanquantile(boots, alpha / 2)), float(np.nanquantile(boots, 1 - alpha / 2))


def did_frac(target_mask, target_valid, control_mask, control_valid, block=32, n=1000, alpha=0.05, seed=0):
    """差の差: 対象期間の変化割合 − 対照（前年同時期など）の変化割合。

    戻り値: (value, lo, hi, detail)
    """
    rng = np.random.default_rng(seed)
    tm, tv = _block_sums(np.asarray(target_mask, bool), np.asarray(target_valid, bool), block)
    cm, cv = _block_sums(np.asarray(control_mask, bool), np.asarray(control_valid, bool), block)
    t = tm.sum() / tv.sum() if tv.sum() else float("nan")
    c = cm.sum() / cv.sum() if cv.sum() else 0.0  # 対照が取れなければ 0（保守的でない点は detail に残す）
    tb = _boot_fracs(tm, tv, n, rng)
    cb = _boot_fracs(cm, cv, n, rng) if cv.sum() else np.zeros(n)
    diff = tb - cb
    detail = {"target": float(t), "control": float(c), "control_available": bool(cv.sum())}
    return float(t - c), float(np.nanquantile(diff, alpha / 2)), float(np.nanquantile(diff, 1 - alpha / 2)), detail


def anomaly_z(value: float, history: list[float]):
    """過去の同時期の分布に対する z 値。履歴が少ないときは区間を広げる。

    戻り値: (z, lo, hi)。区間は履歴の標準偏差の推定誤差を粗く反映したもの。
    """
    h = np.asarray([x for x in history if x is not None and not np.isnan(x)], float)
    if len(h) < 3:
        return float("nan"), float("nan"), float("nan")
    mu, sd = h.mean(), h.std(ddof=1)
    sd = max(sd, 1e-6)
    z = (value - mu) / sd
    # sd の相対誤差 ≈ 1/sqrt(2(n-1)) を使った簡易な幅
    rel = 1.0 / np.sqrt(2 * (len(h) - 1))
    lo, hi = sorted([(value - mu) / (sd * (1 + 2 * rel)), (value - mu) / (sd * max(1 - 2 * rel, 0.2))])
    return float(z), float(lo), float(hi)
