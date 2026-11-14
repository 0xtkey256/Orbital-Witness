import asyncio
from datetime import date
from pathlib import Path
from types import SimpleNamespace

import pytest

from witness import config, repair, scout
from witness.planning import (PlanDraft, PlanError, SignatureProposal, SkepticReview, apply_review,
                              build_hypothesis, merge_signatures, parse_event_date)
from witness.sandbox import PROBES, ProbeJob, prepare
from witness.signatures import default_signatures

TODAY = date(2026, 11, 14)


def prop(id_, min_effect, probe="optical_change", measure="new_water_frac", sensor="s2"):
    return SignatureProposal(id=id_, probe=probe, measure=measure, sensor=sensor, direction="increase",
                             min_effect=min_effect, rationale="test")


# ---------- 計画のガード ----------
def test_llm_can_tighten_but_not_loosen():
    sigs, log = merge_signatures(default_signatures("flood"),
                                 [prop("flood.new_water.s2", 0.05), prop("flood.vv_drop.s1", 0.0001)])
    by = {s.id: s for s in sigs}
    assert by["flood.new_water.s2"].min_effect == 0.05
    assert by["flood.vv_drop.s1"].min_effect == 0.02
    assert any("厳格化" in x for x in log) and any("却下" in x for x in log)


def test_llm_cannot_drop_default_signatures_but_can_add():
    sigs, _ = merge_signatures(default_signatures("flood"), [prop("flood.lights", 0.1, "night_lights", "drop", "viirs")])
    ids = [s.id for s in sigs]
    assert ids[:3] == [s.id for s in default_signatures("flood")] and ids[-1] == "flood.lights"


@pytest.mark.parametrize("bad", ["2027-01-01", "2010-01-01", "last tuesday"])
def test_bad_dates_rejected(bad):
    with pytest.raises(PlanError):
        parse_event_date(bad, TODAY)


def test_other_event_without_signatures_is_rejected():
    with pytest.raises(PlanError):
        build_hypothesis("x", PlanDraft(place="p", event_type="other", event_date="2024-04-16"), 0, 0, TODAY)


def test_review_adds_alternatives_and_tightens():
    hyp, _ = build_hypothesis("c", PlanDraft(place="Dubai", event_type="flood", event_date="2024-04-16"), 25.2, 55.3, TODAY)
    hyp2, log = apply_review(hyp, SkepticReview(alternatives=["潮位の高い時刻に撮影"], signatures=[prop("flood.new_water.s2", 0.04)]))
    assert hyp2.alternatives == ["潮位の高い時刻に撮影"] and log


# ---------- CodeAF 修復のガード ----------
PROBE_SRC = '''from _common import emit, measure, run
WATER_T = 0.1
def main():
    x = undefined_name
    emit("optical_change", {"new_water_frac": measure(0.1 * WATER_T, 0.0, 0.2)}, 0.9)
run(main)
'''


def test_moved_goalposts_detects_threshold_change():
    assert repair.moved_goalposts(PROBE_SRC, PROBE_SRC.replace("WATER_T = 0.1", "WATER_T = 0.05")) == [0.1]
    assert repair.moved_goalposts(PROBE_SRC, PROBE_SRC.replace("x = undefined_name", "x = 1")) == []
    assert repair.moved_goalposts("x = (", "x = 1") == []  # 修復前が構文エラーなら比較しない


class FakeApp:
    def __init__(self, edit):
        self.edit, self.notes, self.prompts = edit, [], []

    async def harness(self, prompt, provider, cwd, **kw):
        assert provider == "codeaf"
        self.prompts.append(prompt)
        self.edit(Path(cwd))
        return SimpleNamespace(text="done", error_message=None)

    def note(self, msg, tags=None):
        self.notes.append(msg)


def make_job(tmp_path):
    src = tmp_path / "src"
    src.mkdir()
    for f in ("_common.py", "_stats.py"):
        (src / f).write_bytes((config.PROBES_DIR / f).read_bytes())
    (src / "optical_change.py").write_text(PROBE_SRC)
    job = ProbeJob("optical_change", {"out_dir": "out"}, tmp_path / "run", source_dir=src)
    prepare(job)
    return job


def test_repair_accepts_bug_fix_and_records_diff(tmp_path):
    job = make_job(tmp_path)
    app = FakeApp(lambda ws: (ws / "optical_change.py").write_text(PROBE_SRC.replace("x = undefined_name", "x = 1")))
    assert asyncio.run(repair.codeaf_repair(app, job, "NameError: undefined_name"))
    assert "x = 1" in job.script.read_text()
    diffs = list((job.run_dir / "repairs").glob("*.diff"))
    assert len(diffs) == 1 and "+    x = 1" in diffs[0].read_text()
    assert "閾値" in app.prompts[0] and "NameError" in app.prompts[0]


def test_repair_rejects_moving_threshold(tmp_path):
    job = make_job(tmp_path)
    bad = PROBE_SRC.replace("x = undefined_name", "x = 1").replace("WATER_T = 0.1", "WATER_T = 0.01")
    app = FakeApp(lambda ws: (ws / "optical_change.py").write_text(bad))
    assert not asyncio.run(repair.codeaf_repair(app, job, "NameError"))
    assert job.script.read_text() == PROBE_SRC and any("拒否" in n for n in app.notes)


def test_repair_discards_changes_to_stats(tmp_path):
    job = make_job(tmp_path)

    def edit(ws):
        (ws / "_stats.py").write_text("# hacked\n")
        (ws / "optical_change.py").write_text(PROBE_SRC.replace("x = undefined_name", "x = 1"))

    app = FakeApp(edit)
    assert asyncio.run(repair.codeaf_repair(app, job, "NameError"))
    assert (job.workdir / "_stats.py").read_bytes() == (config.PROBES_DIR / "_stats.py").read_bytes()
    assert any("_stats.py の変更を破棄" in n for n in app.notes)


def test_repair_without_change_returns_false(tmp_path):
    job = make_job(tmp_path)
    assert not asyncio.run(repair.codeaf_repair(FakeApp(lambda ws: None), job, "boom"))


# ---------- CodeAF による新規プローブ ----------
SYNTH_OK = '''DATA_DOMAINS = ["example.org"]
from _common import emit, load_params, measure, run
def main():
    load_params()
    emit("night_lights", {"radiance_drop_frac": measure(0.2, 0.1, 0.3)}, 1.0)
run(main)
'''


def test_synthesis_validates_contract_and_registers(tmp_path):
    app = FakeApp(lambda ws: (ws / "night_lights.py").write_text(SYNTH_OK))
    try:
        out = asyncio.run(repair.codeaf_synthesize(
            app, "night_lights", "radiance_drop_frac", "increase", "停電で夜間光が減る",
            {"place": "X", "lat": 0, "lon": 0, "event_date": "2024-04-16"}, config.PROBES_DIR, tmp_path / "synth"))
        assert (out / "night_lights.py").exists() and PROBES["night_lights"]["domains"] == ["example.org"]
    finally:
        PROBES.pop("night_lights", None)


def test_synthesis_without_declared_domains_is_rejected(tmp_path):
    app = FakeApp(lambda ws: (ws / "night_lights.py").write_text(SYNTH_OK.replace('DATA_DOMAINS = ["example.org"]\n', "")))
    with pytest.raises(ValueError):
        asyncio.run(repair.codeaf_synthesize(app, "night_lights", "radiance_drop_frac", "increase", "",
                                             {"place": "X", "lat": 0, "lon": 0, "event_date": "2024-04-16"},
                                             config.PROBES_DIR, tmp_path / "synth"))
    assert "night_lights" not in PROBES


# ---------- Tavily の呼び方 ----------
class FakeTavily:
    def __init__(self):
        self.calls = []

    def search(self, query, **kw):
        self.calls.append(("search", query, kw))
        url = {"support": "https://news.example/a", "refute": "https://check.example/b"}
        kind = "refute" if "fact check" in query else "support"
        if kw.get("include_domains"):
            return {"results": [{"url": "https://reliefweb.int/report/x", "title": "OCHA", "score": 0.9}]}
        return {"results": [{"url": url[kind], "title": kind, "score": 0.5},
                            {"url": "https://news.example/a/", "title": "dup", "score": 0.1}]}

    def extract(self, urls, **kw):
        self.calls.append(("extract", urls, kw))
        return {"results": [{"url": u, "raw_content": f"body of {u}"} for u in urls]}


def test_corroborate_is_time_bounded_two_sided_and_prefers_authorities():
    t = FakeTavily()
    res = scout.corroborate("豪雨で冠水", "Dubai", date(2024, 4, 16), tavily=t)
    searches = [c for c in t.calls if c[0] == "search"]
    assert all(c[2]["start_date"] == "2024-04-09" and c[2]["end_date"] == "2024-05-16" for c in searches)
    assert any("fact check" in c[1] for c in searches)
    official = [c for c in searches if c[2].get("include_domains")]
    assert official and official[0][2]["include_domains_mode"] == "prefer"
    urls = [s["url"] for s in res["sources"]]
    assert len(urls) == len(set(u.rstrip("/") for u in urls)) == 3
    assert next(s for s in res["sources"] if "reliefweb" in s["url"])["authoritative"]
    assert all(s.get("body", "").startswith("body of") for s in res["sources"])


# ---------- Tavily は任意 ----------
def test_tavily_skipped_without_key(monkeypatch):
    from witness import config, scout
    monkeypatch.setattr(config, "TAVILY_API_KEY", "")
    r = scout.scan("Dubai flood")
    assert r["sources"] == [] and "未設定" in r["skipped"]
    c = scout.corroborate("Dubai flood", "Dubai", __import__("datetime").date(2024, 4, 16))
    assert c["sources"] == [] and c["skipped"]


def test_tavily_quota_error_trips_breaker(monkeypatch):
    from witness import config, scout
    monkeypatch.setattr(config, "TAVILY_API_KEY", "tvly-real")
    monkeypatch.setattr(config, "TAVILY_MODE", "auto")
    monkeypatch.setattr(scout, "_disabled_reason", None)
    calls = []

    class Broke:
        def search(self, *a, **k):
            calls.append(1)
            raise RuntimeError("UsageLimitExceededError: This request exceeds your plan's set usage limit")

    monkeypatch.setattr(scout, "client", lambda: Broke())
    assert scout.scan("x")["skipped"]
    assert scout.scan("x")["skipped"].startswith("Tavily が使えない")
    assert len(calls) == 1  # 2 回目は呼ばずに飛ばす
