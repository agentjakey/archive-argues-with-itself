"""A job spec (docs/formats/jobs.md): config/jobs/<name>.toml read into one value. The build key is a
hash of everything that changes a job's output (kind, code version, model, parameters and the input
fingerprint), so a changed job writes to a new versioned folder and never mixes with an old run."""
from __future__ import annotations

import hashlib
import json
import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

REPO = Path(__file__).resolve().parents[3]
JOBS_DIR = REPO / "config" / "jobs"
KINDS = ("embed", "ocr", "judge", "compile")
EXECUTORS = ("local", "workers_ai", "k8s")


class SpecError(Exception):
    pass


@dataclass(frozen=True)
class JobSpec:
    name: str
    kind: str
    code_version: str
    input_prefix: str           # where the prepared input units live in the store
    output_prefix: str          # where outputs go: <output_prefix>/<name>/<build_key>/
    model: dict                 # name, licence, and per-executor model ids
    params: dict
    executors: dict             # executor name -> its settings
    path: Path
    extra: dict = field(default_factory=dict)

    def build_key(self, input_fingerprint: str) -> str:
        body = {"kind": self.kind, "code_version": self.code_version, "model": self.model,
                "params": self.params, "input": input_fingerprint}
        return hashlib.sha256(json.dumps(body, sort_keys=True).encode("utf-8")).hexdigest()[:16]

    def run_prefix(self, input_fingerprint: str) -> str:
        return f"{self.output_prefix.rstrip('/')}/{self.name}/{self.build_key(input_fingerprint)}"


def load(name_or_path: str, jobs_dir: Path = JOBS_DIR) -> JobSpec:
    path = Path(name_or_path)
    if not path.suffix:
        path = Path(jobs_dir) / f"{name_or_path}.toml"
    if not path.exists():
        raise SpecError(f"no job spec at {path}")
    with path.open("rb") as fh:
        raw = tomllib.load(fh)
    job = raw.get("job") or {}
    for key in ("name", "kind", "code_version"):
        if key not in job:
            raise SpecError(f"{path}: [job] needs {key}")
    if job["kind"] not in KINDS:
        raise SpecError(f"{path}: kind must be one of {KINDS}")
    executors = raw.get("executor") or {}
    unknown = sorted(set(executors) - set(EXECUTORS))
    if unknown:
        raise SpecError(f"{path}: unknown executors {unknown}")
    if not (raw.get("model") or {}).get("licence"):
        raise SpecError(f"{path}: [model] needs a licence (no non-commercial or no-redistribution models)")
    return JobSpec(name=job["name"], kind=job["kind"], code_version=str(job["code_version"]),
                   input_prefix=(raw.get("input") or {}).get("prefix", f"jobs-input/{job['name']}"),
                   output_prefix=(raw.get("output") or {}).get("prefix", "jobs"),
                   model=dict(raw.get("model") or {}), params=dict(raw.get("params") or {}),
                   executors=executors, path=path,
                   extra={k: v for k, v in raw.items() if k not in ("job", "input", "output", "model", "params", "executor")})


def executor_settings(spec: JobSpec, executor: str) -> dict:
    if executor not in spec.executors:
        raise SpecError(f"{spec.path}: no [executor.{executor}] section: this job does not run there")
    return dict(spec.executors[executor])


def model_id(spec: JobSpec, executor: str) -> Optional[str]:
    return executor_settings(spec, executor).get("model") or spec.model.get("name")
