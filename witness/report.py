"""case.json → 1 ファイルの HTML レポート（画像は埋め込み）。

    python -m witness.report runs/<run_id>/case.json
"""
import base64
import html
import json
import sys
from pathlib import Path

LABEL = {"supported": ("衛星・気象の観測は主張を裏付けています", "#2E6A4C", "#7FC3A0"),
         "contradicted": ("衛星・気象の観測は主張と食い違っています", "#9E3A2B", "#E39A8C"),
         "inconclusive": ("観測だけでは判断できません", "#8A6A1C", "#D9B862")}
OUTCOME = {"confirm": "予測どおり", "refute": "予測と逆", "null": "判定に使わず"}
STANCE = {"support": "支持", "refute": "否定", "unrelated": "無関係"}
e = html.escape


def img(path):
    p = Path(path)
    return f"data:image/png;base64,{base64.b64encode(p.read_bytes()).decode()}" if p.exists() else ""


def render(case: dict) -> str:
    v, ex, hyp = case["verdict"], case.get("explanation") or {}, case["prereg"]["hypothesis"]
    label, light, dark = LABEL[v["label"]]
    notes = {n["signature_id"]: n["plain"] for n in ex.get("signatures", [])}
    rows = "".join(
        f"<tr><td>{e(x['signature_id'])}</td><td>{OUTCOME[x['outcome']]}</td><td>{x['log_lr']:+.2f}</td>"
        f"<td>{e(x['reason'])}<br><small>{e(notes.get(x['signature_id'], ''))}</small></td></tr>" for x in v["entries"])
    figs = "".join(f'<figure><img src="{img(path)}" alt="{e(r["probe"])} {e(name)}"><figcaption>{e(r["probe"])} / {e(name)}</figcaption></figure>'
                   for r in case["results"] for name, path in r["artifacts"].items() if img(path))
    probes = "".join(f"<li>{e(r['probe'])}: sandbox {e(r['sandbox_id'] or '-')}、修復 {r['repairs']} 回、"
                     f"code {e(r['code_sha256'][:16])}{'、<b>' + e(r['error'][:120]) + '</b>' if r.get('error') else ''}</li>"
                     for r in case["results"])
    sources = "".join(f'<li><a href="{e(s["url"])}">{e(s["title"] or s["url"])}</a> <small>{STANCE.get(s.get("stance"), "")}'
                      f'{"・公的機関" if s.get("authoritative") else ""}</small></li>'
                      for s in (case.get("corroboration") or {}).get("sources", [])[:10])
    alts = "".join(f"<li>{e(a)}</li>" for a in hyp.get("alternatives", []))
    log = "".join(f"<li>{e(x)}</li>" for x in case.get("plan_log", []))
    flags = "".join(f"<li>{e(x)}</li>" for x in ex.get("image_flags", []))
    return f"""<!doctype html><html lang="ja"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1"><title>Orbital Witness: {e(case['claim'][:40])}</title>
<style>
:root{{--paper:#EEF2EF;--ink:#18262F;--muted:#5B6B70;--rule:#C6D1CC;--v:{light};color-scheme:light}}
@media (prefers-color-scheme:dark){{:root{{--paper:#141C21;--ink:#E4EAE6;--muted:#9AA8AC;--rule:#2D3A40;--v:{dark};color-scheme:dark}}}}
body{{margin:0;background:var(--paper);color:var(--ink);font:16px/1.7 "Hiragino Sans","Noto Sans JP",system-ui,sans-serif}}
main{{max-width:1120px;margin:0 auto;padding:40px 24px 64px}}
.verdict{{border-left:6px solid var(--v);padding:4px 0 4px 18px;margin-bottom:24px}}
.verdict strong{{display:block;color:var(--v);font-size:1.1rem}}
h1{{font-size:clamp(1.4rem,3vw,2.1rem);line-height:1.35;margin:0 0 6px;max-width:32em}}
h2{{font-size:1rem;margin:32px 0 8px}} small,.muted{{color:var(--muted)}}
.seal{{font-family:ui-monospace,monospace;font-size:.85rem;color:var(--muted)}}
.frames{{display:grid;grid-template-columns:repeat(auto-fill,minmax(220px,1fr));gap:12px}}
figure{{margin:0}} figure img{{width:100%;aspect-ratio:1;object-fit:cover;border:1px solid var(--rule)}}
figcaption{{font-size:.8rem;color:var(--muted)}}
.scroll{{overflow-x:auto}} table{{border-collapse:collapse;width:100%;font-size:.9rem}}
td{{padding:6px 12px 6px 0;border-bottom:1px solid var(--rule);vertical-align:top}}
a{{color:inherit}} ul{{padding-left:1.2em;max-width:44em}}
</style></head><body><main>
<div class="verdict"><strong>{label}</strong><span class="muted">事後確率 {v['posterior']:.2f}（事前 {v['prior']:.2f}）</span></div>
<h1>{e(case['claim'])}</h1>
<p class="muted">{e(hyp['aoi']['place'])}（{hyp['aoi']['lat']:.4f}, {hyp['aoi']['lon']:.4f}）／出来事 {e(hyp['timeframe']['event_date'])}／{e(hyp['event_type'])}</p>
<p class="seal">事前登録 sha256 {e(case['prereg']['sha256'])}<br>封印 {e(str(case['prereg']['sealed_at']))}（観測より前）</p>
<p>{e(ex.get('summary', ''))}</p>
<div class="frames">{figs}</div>
<h2>証拠台帳（判定は数式で確定）</h2><div class="scroll"><table>{rows}</table></div>
<h2>データを見る前に検討した代替説明</h2><ul>{alts}</ul>
<h2>計画の調整（LLM の提案とガード）</h2><ul>{log}</ul>
<h2>報道と観測</h2><p>{e(ex.get('media_vs_observation', ''))}</p><ul>{sources or '<li><small>報道は取得していません（' + e((case.get("corroboration") or {}).get("skipped") or "該当なし") + '）。判定は衛星・気象の観測のみに基づきます。</small></li>'}</ul>
<h2>画像上の注意</h2><ul>{flags}</ul>
<h2>実行の記録</h2><ul>{probes}</ul>
</main></body></html>"""


if __name__ == "__main__":
    path = Path(sys.argv[1])
    out = path.with_name("report.html")
    out.write_text(render(json.loads(path.read_text())), encoding="utf-8")
    print(out)
