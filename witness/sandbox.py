"""[Daytona] プローブを隔離サンドボックスで並列実行する。

- プローブごとに 1 サンドボックス。asyncio.gather で同時に走らせる
- 通信はデータ取得先のドメインだけ許可（生成・修復されたコードでも外へ持ち出せない）
- 終了コード 3（データ不足）はそのまま返し、それ以外の失敗だけ repair（CodeAF）に回す
- 実行したコードの SHA-256 を結果に刻む（証拠バンドルと再実行の基礎）
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Awaitable, Callable, Optional, Protocol

from . import config
from .schemas import Measure, ProbeResult

EXIT_NO_DATA = 3
SHARED = ["_common.py", "_stats.py"]
DEPS = ["numpy", "rasterio", "pystac-client", "pillow"]
PIP_DOMAINS = ["pypi.org", "files.pythonhosted.org"]

PROBES: dict[str, dict] = {
    "optical_change": {"domains": ["earth-search.aws.element84.com", "sentinel-cogs.s3.us-west-2.amazonaws.com"]},
    "weather_anomaly": {"domains": ["archive-api.open-meteo.com"]},
    "sar_change": {"domains": ["identity.dataspace.copernicus.eu", "sh.dataspace.copernicus.eu"], "cdse": True},
}

def enabled_probes() -> list[str]:
    """認証情報が無いプローブは外す（SAR は Copernicus のアカウントが必要）。"""
    return [p for p, spec in PROBES.items() if not spec.get("cdse") or config.CDSE_CLIENT_ID]


Repair = Callable[["ProbeJob", str], Awaitable[bool]]


@dataclass
class ProbeJob:
    probe: str
    params: dict
    run_dir: Path
    source_dir: Path = config.PROBES_DIR

    @property
    def workdir(self) -> Path:
        return self.run_dir / "probes" / self.probe

    @property
    def outdir(self) -> Path:
        return self.run_dir / "artifacts" / self.probe

    @property
    def script(self) -> Path:
        return self.workdir / f"{self.probe}.py"

    def files(self) -> list[Path]:
        return [self.workdir / n for n in SHARED + [f"{self.probe}.py"]]


@dataclass
class ExecOutcome:
    exit_code: int
    log: str
    result: Optional[dict] = None
    files: dict[str, bytes] = field(default_factory=dict)


class Executor(Protocol):
    name: str
    def open(self, job: ProbeJob): ...
    def exec(self, handle, job: ProbeJob) -> ExecOutcome: ...
    def handle_id(self, handle) -> str: ...
    def close(self, handle) -> None: ...


def prepare(job: ProbeJob) -> None:
    """プローブのコピーを run ごとの作業ディレクトリに置く（修復はこのコピーに対して行う）。"""
    job.workdir.mkdir(parents=True, exist_ok=True)
    for name in SHARED + [f"{job.probe}.py"]:
        if not (job.workdir / name).exists():
            shutil.copy(job.source_dir / name, job.workdir / name)
    (job.workdir / "params.json").write_text(json.dumps(job.params, ensure_ascii=False, default=str))


def code_sha256(job: ProbeJob) -> str:
    h = hashlib.sha256()
    for f in sorted(job.files()):
        h.update(f.name.encode() + b"\0" + f.read_bytes() + b"\0")
    return h.hexdigest()


# ---------- 実行環境 ----------
class LocalExecutor:
    """開発・テスト用。Daytona が使えないときの退避先でもある（sandbox_id は local になる）。"""
    name = "local"

    def open(self, job):
        return None

    def handle_id(self, handle):
        return "local"

    def exec(self, handle, job):
        p = subprocess.run([sys.executable, job.script.name, "params.json"], cwd=job.workdir,
                           capture_output=True, text=True, timeout=900)
        log = p.stdout + p.stderr
        out = job.workdir / job.params.get("out_dir", "out")
        result = json.loads((out / "result.json").read_text()) if p.returncode == 0 and (out / "result.json").exists() else None
        files = {n: (out / n).read_bytes() for n in (result or {}).get("artifacts", []) if (out / n).exists()}
        return ExecOutcome(p.returncode, log, result, files)

    def close(self, handle):
        pass


class DaytonaExecutor:
    name = "daytona"

    def __init__(self, snapshot: str = config.WITNESS_SNAPSHOT, restrict_network: bool = config.RESTRICT_NETWORK):
        from daytona import Daytona, DaytonaConfig
        self.daytona = Daytona(DaytonaConfig(api_key=config.require("DAYTONA_API_KEY", config.DAYTONA_API_KEY)))
        self.snapshot, self.restrict = snapshot, restrict_network

    def _create_params(self, job: ProbeJob):
        from daytona import CreateSandboxFromSnapshotParams
        spec = PROBES[job.probe]
        kw: dict = {"labels": {"app": "orbital-witness", "probe": job.probe, "run": job.run_dir.name},
                    "auto_stop_interval": 15, "ephemeral": True, "env_vars": {}}
        if spec.get("cdse"):
            kw["env_vars"]["CDSE_CLIENT_ID"] = config.CDSE_CLIENT_ID
            if config.CDSE_SECRET_NAME:  # 平文をサンドボックスに入れない
                kw["secrets"] = {"CDSE_CLIENT_SECRET": config.CDSE_SECRET_NAME}
            else:
                kw["env_vars"]["CDSE_CLIENT_SECRET"] = config.CDSE_CLIENT_SECRET
        if self.restrict:
            kw["domain_allow_list"] = ",".join(spec["domains"] + ([] if self.snapshot else PIP_DOMAINS))
        if self.snapshot:
            return CreateSandboxFromSnapshotParams(snapshot=self.snapshot, **kw)
        return CreateSandboxFromSnapshotParams(language="python", **kw)

    def open(self, job):
        sb = self.daytona.create(self._create_params(job), timeout=180)
        if not self.snapshot:
            r = sb.process.exec(f"pip install -q {' '.join(DEPS)}", timeout=600)
            if r.exit_code != 0:
                self.daytona.delete(sb)
                raise RuntimeError(f"依存の導入に失敗: {(r.result or '')[-500:]}")
        return sb

    def handle_id(self, sb):
        return sb.id

    def exec(self, sb, job):
        jd = f"{sb.get_work_dir()}/job"
        out = job.params.get("out_dir", "out")
        sb.process.exec(f"mkdir -p {jd}/{out}")
        for f in job.files() + [job.workdir / "params.json"]:
            sb.fs.upload_file(f.read_bytes(), f"{jd}/{f.name}")
        r = sb.process.exec(f"python {job.script.name} params.json", cwd=jd, timeout=900)
        log = r.result or ""
        if r.exit_code != 0:
            return ExecOutcome(r.exit_code, log)
        result = json.loads(sb.fs.download_file(f"{jd}/{out}/result.json"))
        files = {n: sb.fs.download_file(f"{jd}/{out}/{n}") for n in result.get("artifacts", [])}
        return ExecOutcome(0, log, result, files)

    def close(self, sb):
        try:
            self.daytona.delete(sb)
        except Exception:
            pass


# ---------- 実行と結果の組み立て ----------
def _to_result(job: ProbeJob, outc: ExecOutcome, sandbox_id: str, repairs: int) -> ProbeResult:
    job.outdir.mkdir(parents=True, exist_ok=True)
    artifacts = {}
    for name, data in outc.files.items():
        (job.outdir / name).write_bytes(data)
        artifacts[name] = str(job.outdir / name)
    nan = float("nan")
    measures = {k: Measure(value=nan if m["value"] is None else m["value"],
                           lo=nan if m["lo"] is None else m["lo"],
                           hi=nan if m["hi"] is None else m["hi"], detail=m.get("detail", {}))
                for k, m in outc.result["measures"].items()}
    return ProbeResult(probe=job.probe, measures=measures, valid_ratio=outc.result["valid_ratio"],
                       scene_ids=outc.result.get("scene_ids", []), code_sha256=code_sha256(job),
                       sandbox_id=sandbox_id, artifacts=artifacts, repairs=repairs)


def _failed(job, sandbox_id, error, repairs=0) -> ProbeResult:
    return ProbeResult(probe=job.probe, measures={}, valid_ratio=0.0, error=error,
                       sandbox_id=sandbox_id, repairs=repairs,
                       code_sha256=code_sha256(job) if job.script.exists() else "")


async def run_job(job: ProbeJob, executor: Executor, repair: Optional[Repair] = None,
                  max_repairs: int = 2) -> ProbeResult:
    prepare(job)
    try:
        handle = await asyncio.to_thread(executor.open, job)
    except Exception as e:
        return _failed(job, "", f"サンドボックス起動失敗: {e}")
    sid = executor.handle_id(handle)
    repairs = 0
    try:
        while True:
            outc = await asyncio.to_thread(executor.exec, handle, job)
            if outc.exit_code == 0 and outc.result:
                return _to_result(job, outc, sid, repairs)
            tail = outc.log[-3000:]
            if outc.exit_code == EXIT_NO_DATA:
                return _failed(job, sid, "NO_DATA: " + tail.strip().splitlines()[-1] if tail.strip() else "NO_DATA", repairs)
            if repair and repairs < max_repairs and await repair(job, tail):
                repairs += 1
                continue
            return _failed(job, sid, f"exit {outc.exit_code}: {tail[-800:]}", repairs)
    finally:
        await asyncio.to_thread(executor.close, handle)


async def run_jobs(jobs: list[ProbeJob], executor: Executor, repair: Optional[Repair] = None) -> list[ProbeResult]:
    async def safe(job):
        try:
            return await run_job(job, executor, repair)
        except Exception as e:  # 1 本の失敗で全体を止めない
            return _failed(job, "", f"{type(e).__name__}: {e}")
    return list(await asyncio.gather(*(safe(j) for j in jobs)))
