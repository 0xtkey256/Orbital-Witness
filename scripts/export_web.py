"""Export finished runs into the static demo site (web/data/).

Usage: python scripts/export_web.py <run_id> [<run_id> ...]

Copies runs/<id>/case.json and the artifact images into web/data/<id>/,
rewrites absolute artifact paths to relative URLs, drops bulky scraped
article bodies, refuses to export anything that looks like a secret, and
(re)writes web/data/index.json.
"""

from __future__ import annotations

import json
import re
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RUNS = ROOT / "runs"
DATA = ROOT / "web" / "data"
IMAGE_EXT = {".png", ".jpg", ".jpeg", ".webp", ".gif"}

SECRET_PATTERNS = [
    re.compile(p)
    for p in (
        r"sk-[A-Za-z0-9_\-]{20,}",          # OpenAI / OpenRouter style
        r"tvly-[A-Za-z0-9_\-]{16,}",        # Tavily
        r"dtn_[A-Za-z0-9_\-]{16,}",         # Daytona
        r"AKIA[0-9A-Z]{16}",                # AWS access key id
        r"ghp_[A-Za-z0-9]{30,}",            # GitHub token
        r"(?i)\"[a-z_]*(api_key|secret|password|token)\"\s*:\s*\"[^\"]{8,}\"",
    )
]


def _scrub_sources(block: dict | None) -> None:
    if not isinstance(block, dict):
        return
    for s in block.get("sources") or []:
        s.pop("body", None)
        if isinstance(s.get("snippet"), str) and len(s["snippet"]) > 280:
            s["snippet"] = s["snippet"][:280].rstrip() + "…"


def export_run(run_id: str) -> dict:
    src = RUNS / run_id
    case_path = src / "case.json"
    if not case_path.is_file():
        raise SystemExit(f"no case.json for run {run_id}: {case_path}")
    case = json.loads(case_path.read_text(encoding="utf-8"))

    out = DATA / run_id
    if out.exists():
        shutil.rmtree(out)
    (out / "img").mkdir(parents=True)

    for res in case.get("results") or []:
        arts = res.get("artifacts") or {}
        probe = res.get("probe", "probe")
        new_arts = {}
        for name, path in arts.items():
            p = Path(path)
            if not p.is_absolute():
                p = src / p
            if p.suffix.lower() not in IMAGE_EXT or not p.is_file():
                continue
            # only copy files that live inside this run's directory
            try:
                p.resolve().relative_to(src.resolve())
            except ValueError:
                continue
            dest_name = f"{probe}__{p.name}"
            shutil.copy2(p, out / "img" / dest_name)
            new_arts[name] = f"data/{run_id}/img/{dest_name}"
        res["artifacts"] = new_arts

    _scrub_sources(case.get("scan"))
    _scrub_sources(case.get("corroboration"))

    text = json.dumps(case, ensure_ascii=False, indent=1)
    for pat in SECRET_PATTERNS:
        m = pat.search(text)
        if m:
            shutil.rmtree(out)
            raise SystemExit(f"refusing to export {run_id}: possible secret ({pat.pattern})")
    if str(ROOT) in text:
        text = text.replace(str(ROOT) + "/", "")
    (out / "case.json").write_text(text, encoding="utf-8")

    verdict = case.get("verdict") or {}
    return {
        "run_id": run_id,
        "claim": case.get("claim"),
        "label": verdict.get("label"),
        "posterior": verdict.get("posterior"),
        "event_date": ((case.get("prereg") or {}).get("hypothesis") or {})
        .get("timeframe", {})
        .get("event_date"),
    }


def main(argv: list[str]) -> None:
    if not argv:
        raise SystemExit(__doc__)
    DATA.mkdir(parents=True, exist_ok=True)
    index_path = DATA / "index.json"
    existing = {}
    if index_path.is_file():
        for r in json.loads(index_path.read_text(encoding="utf-8")).get("runs", []):
            if (DATA / r["run_id"] / "case.json").is_file():
                existing[r["run_id"]] = r
    for run_id in argv:
        existing[run_id] = export_run(run_id)
        print(f"exported {run_id} -> {DATA / run_id}")
    # featured run first: the ones named on this invocation, in order
    order = list(argv) + [k for k in existing if k not in argv]
    index_path.write_text(
        json.dumps({"runs": [existing[k] for k in order]}, ensure_ascii=False, indent=1),
        encoding="utf-8",
    )
    print(f"wrote {index_path}")


if __name__ == "__main__":
    main(sys.argv[1:])
