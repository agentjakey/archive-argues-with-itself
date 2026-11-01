"""Run batch jobs on a Kubernetes cluster from one values file (docs/CLUSTER.md).

  render   write the manifests for a job to k8s/out/<job>/ (no cluster needed)
  up       render, then kubectl apply: namespace (when we may create it), quota, the job, and the
           optional judge server
  finish   run the job's finish and verify step as a one-pod Job
  status   the job's pods and how many units are done
  down     delete every object this project created (by its label), and the namespace when we
           created it: one command, nothing left behind

    python scripts/v2/cluster.py render --values k8s/values.example.toml --job embed-sample
    python scripts/v2/cluster.py up --values k8s/values.toml --job embed-sample
    python scripts/v2/cluster.py down --values k8s/values.toml

Pods run as a non-root user with no privilege escalation, all capabilities dropped, a read-only root
filesystem and the default seccomp profile; they get a per-pod scratch volume, Secrets by name only,
and no service account token. Every object carries app.kubernetes.io/part-of=<owner_label> and a
contact annotation, so the cluster's owner can see what is ours.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tomllib
from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "src"))

from archive_debugger.jobs import spec as spec_mod  # noqa: E402

PART_OF = "app.kubernetes.io/part-of"
NAME = "app.kubernetes.io/name"


def load_values(path: Path) -> dict:
    with Path(path).open("rb") as fh:
        return tomllib.load(fh)


def meta(values: dict, name: str, component: str) -> dict:
    return {"name": name, "namespace": values["cluster"]["namespace"],
            "labels": {PART_OF: values["cluster"]["owner_label"], NAME: name, "app.kubernetes.io/component": component},
            "annotations": {"archive-argues/contact": values["cluster"]["contact"]}}


def security(read_only: bool = True) -> dict:
    return {"runAsNonRoot": True, "runAsUser": 10001, "runAsGroup": 10001, "allowPrivilegeEscalation": False,
            "privileged": False, "readOnlyRootFilesystem": read_only, "capabilities": {"drop": ["ALL"]},
            "seccompProfile": {"type": "RuntimeDefault"}}


def env_from(values: dict, spec) -> list:
    out = []
    if values["job"].get("store") == "r2" and values["secrets"].get("r2"):
        out.append({"secretRef": {"name": values["secrets"]["r2"]}})
    if "workers_ai" in spec.executors and values["secrets"].get("workers_ai"):
        out.append({"secretRef": {"name": values["secrets"]["workers_ai"]}})
    return out


def scratch_volume(values: dict) -> dict:
    claim = {"accessModes": ["ReadWriteOnce"], "resources": {"requests": {"storage": values["scratch"]["size"]}}}
    if values["scratch"].get("storage_class"):
        claim["storageClassName"] = values["scratch"]["storage_class"]
    return {"name": "scratch", "ephemeral": {"volumeClaimTemplate": {
        "metadata": {"labels": {PART_OF: values["cluster"]["owner_label"]}}, "spec": claim}}}


def pod_spec(values: dict, spec, command: list, *, gpu: bool, parallel: bool) -> dict:
    res = values["job"]["resources"]["gpu" if gpu else "cpu"]
    resources = {"requests": dict(res["requests"]), "limits": dict(res["limits"])}
    if gpu:
        resources["limits"][values["gpu"]["resource"]] = int(res.get("gpus", 1))
    container = {
        "name": "job", "image": values["images"]["gpu" if gpu else "cpu"],
        "imagePullPolicy": values["images"].get("pull_policy", "IfNotPresent"),
        "command": command, "resources": resources, "securityContext": security(),
        "env": [{"name": "JOB_WORKERS", "value": str(values["job"]["completions"] if parallel else 1)},
                {"name": "JOBS_STORE", "value": values["job"].get("store", "r2")},
                {"name": "JOBS_LOCAL_STORE", "value": "/scratch/store"},
                {"name": "HF_HOME", "value": "/scratch/hf"}, {"name": "HOME", "value": "/scratch/home"},
                {"name": "TMPDIR", "value": "/tmp"}],
        "envFrom": env_from(values, spec),
        "volumeMounts": [{"name": "scratch", "mountPath": "/scratch"}, {"name": "tmp", "mountPath": "/tmp"}],
    }
    pod = {"restartPolicy": "Never", "automountServiceAccountToken": False,
           "securityContext": {"runAsNonRoot": True, "fsGroup": 10001, "seccompProfile": {"type": "RuntimeDefault"}},
           "containers": [container],
           "volumes": [scratch_volume(values), {"name": "tmp", "emptyDir": {"sizeLimit": "4Gi"}}]}
    if values["images"].get("pull_secret"):
        pod["imagePullSecrets"] = [{"name": values["images"]["pull_secret"]}]
    if gpu:
        selector = dict(values["gpu"].get("node_selector") or {})
        if values["gpu"].get("type"):
            selector[values["gpu"]["type_label"]] = values["gpu"]["type"]
        if selector:
            pod["nodeSelector"] = selector
        if values["gpu"].get("tolerations"):
            pod["tolerations"] = values["gpu"]["tolerations"]
    return pod


def render(values: dict, job_name: str) -> list:
    spec = spec_mod.load(job_name)
    k8s = spec_mod.executor_settings(spec, "k8s")
    gpu = bool(k8s.get("gpu"))
    v = values
    docs = []
    if v["cluster"].get("create_namespace"):
        docs.append({"apiVersion": "v1", "kind": "Namespace",
                     "metadata": {"name": v["cluster"]["namespace"], "labels": {PART_OF: v["cluster"]["owner_label"]},
                                  "annotations": {"archive-argues/contact": v["cluster"]["contact"]}}})
    q = v["quota"]
    docs.append({"apiVersion": "v1", "kind": "ResourceQuota", "metadata": meta(v, "archive-argues-quota", "quota"),
                 "spec": {"hard": {"requests.cpu": q["cpu"], "limits.cpu": q["cpu"], "requests.memory": q["memory"],
                                   "limits.memory": q["memory"], f"requests.{v['gpu']['resource']}": q["gpus"],
                                   "requests.storage": q["storage"]}}})
    name = f"job-{spec.name}"
    run = ["python", "scripts/v2/jobs.py", "run", spec.name, "--executor", "k8s", "--store", v["job"].get("store", "r2")]
    docs.append({"apiVersion": "batch/v1", "kind": "Job", "metadata": meta(v, name, "job"),
                 "spec": {"completionMode": "Indexed", "completions": v["job"]["completions"],
                          "parallelism": v["job"]["parallelism"], "backoffLimitPerIndex": v["job"]["backoff_limit"],
                          "maxFailedIndexes": v["job"]["completions"],
                          "ttlSecondsAfterFinished": v["job"]["ttl_seconds_after_finished"],
                          "template": {"metadata": {"labels": {PART_OF: v["cluster"]["owner_label"], NAME: name}},
                                       "spec": pod_spec(v, spec, run, gpu=gpu, parallel=True)}}})
    if v.get("judge_server", {}).get("enabled") and spec.kind == "judge":
        docs += judge_server(v)
    return docs


def finish_job(values: dict, job_name: str) -> dict:
    spec = spec_mod.load(job_name)
    name = f"finish-{spec.name}"
    store = values["job"].get("store", "r2")
    cmd = ["sh", "-c", f"python scripts/v2/jobs.py finish {spec.name} --store {store} && "
                       f"python scripts/v2/jobs.py verify {spec.name} --store {store}"]
    return {"apiVersion": "batch/v1", "kind": "Job", "metadata": meta(values, name, "finish"),
            "spec": {"backoffLimit": 2, "ttlSecondsAfterFinished": values["job"]["ttl_seconds_after_finished"],
                     "template": {"metadata": {"labels": {PART_OF: values["cluster"]["owner_label"], NAME: name}},
                                  "spec": pod_spec(values, spec, cmd, gpu=False, parallel=False)}}}


def judge_server(v: dict) -> list:
    js = v["judge_server"]
    name = "judge-server"
    container = {"name": "vllm", "image": js["image"],
                 "args": ["--model", js["model"], "--max-model-len", str(js["max_model_len"]), "--port", "8000"],
                 "ports": [{"containerPort": 8000}],
                 "env": [{"name": "HF_HOME", "value": "/scratch/hf"}, {"name": "HOME", "value": "/scratch/home"}],
                 "resources": {"limits": {v["gpu"]["resource"]: js["gpus"]}},
                 "securityContext": security(read_only=False),
                 "volumeMounts": [{"name": "scratch", "mountPath": "/scratch"}, {"name": "shm", "mountPath": "/dev/shm"}],
                 "readinessProbe": {"httpGet": {"path": "/health", "port": 8000}, "periodSeconds": 10}}
    pod = {"automountServiceAccountToken": False, "securityContext": {"runAsNonRoot": True, "fsGroup": 10001},
           "containers": [container],
           "volumes": [scratch_volume(v), {"name": "shm", "emptyDir": {"medium": "Memory", "sizeLimit": "8Gi"}}]}
    if v["gpu"].get("type"):
        pod["nodeSelector"] = {v["gpu"]["type_label"]: v["gpu"]["type"], **(v["gpu"].get("node_selector") or {})}
    if v["gpu"].get("tolerations"):
        pod["tolerations"] = v["gpu"]["tolerations"]
    labels = {PART_OF: v["cluster"]["owner_label"], NAME: name}
    return [{"apiVersion": "apps/v1", "kind": "Deployment", "metadata": meta(v, name, "judge-server"),
             "spec": {"replicas": 1, "selector": {"matchLabels": labels},
                      "template": {"metadata": {"labels": labels}, "spec": pod}}},
            {"apiVersion": "v1", "kind": "Service", "metadata": meta(v, name, "judge-server"),
             "spec": {"selector": labels, "ports": [{"port": 8000, "targetPort": 8000}]}}]


def write(docs: list, folder: Path) -> Path:
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / "manifests.yaml"
    path.write_text(yaml.safe_dump_all(docs, sort_keys=False), encoding="utf-8")
    return path


def kubectl(*args: str) -> int:
    print("kubectl " + " ".join(args))
    return subprocess.run(["kubectl", *args]).returncode


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("command", choices=["render", "up", "finish", "status", "down"])
    ap.add_argument("--values", type=Path, default=REPO / "k8s" / "values.toml")
    ap.add_argument("--job", default=None)
    ap.add_argument("--context", default=None, help="a kubectl context; default: the current one")
    args = ap.parse_args(argv)
    values = load_values(args.values)
    ns = values["cluster"]["namespace"]
    ctx = ["--context", args.context] if args.context else []
    label = f"{PART_OF}={values['cluster']['owner_label']}"
    if args.command in ("render", "up"):
        if not args.job:
            ap.error("--job is required")
        path = write(render(values, args.job), REPO / "k8s" / "out" / args.job)
        print(f"wrote {path}")
        return kubectl(*ctx, "apply", "-f", str(path)) if args.command == "up" else 0
    if args.command == "finish":
        path = write([finish_job(values, args.job)], REPO / "k8s" / "out" / f"{args.job}-finish")
        return kubectl(*ctx, "apply", "-f", str(path))
    if args.command == "status":
        return kubectl(*ctx, "get", "jobs,pods,pvc,deployments,services", "-n", ns, "-l", label, "-o", "wide")
    code = kubectl(*ctx, "delete", "jobs,deployments,services,pods,pvc,resourcequota,configmaps", "-n", ns, "-l", label,
                   "--ignore-not-found", "--wait=true")
    if values["cluster"].get("create_namespace"):
        code = kubectl(*ctx, "delete", "namespace", ns, "--ignore-not-found", "--wait=true") or code
    return code


if __name__ == "__main__":
    sys.exit(main())
