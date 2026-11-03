# Running the batch jobs on donated compute

This page is for whoever lends this project a cluster. It covers what runs, how to start, stop and
resume it, roughly how much it uses, and how to remove all of it. Nothing here has run on a GPU
cluster yet. Every job has run on a CPU against a small slice, and the manifests have been applied
to a local test cluster (see "What has been tested").

## What runs

There are four batch jobs. Each is described once in `config/jobs/<name>.toml` and runs unchanged on
a laptop's CPU, through Workers AI (where the model is offered there), or as a Kubernetes Job.
Formats: [formats/jobs.md](formats/jobs.md).

| Job | What it does | Model and licence | GPU |
|---|---|---|---|
| `embed` | turns passages into dense vectors in the index format named by `config/jobs/index_spec.toml` | paraphrase-multilingual-MiniLM-L12-v2, Apache-2.0 | yes (fast); runs on CPU too |
| `ocr` | reads the worst-scanned pages again, keeping the old text beside the new | chosen by measurement from Tesseract, docTR and PaddleOCR, all Apache-2.0 | docTR and PaddleOCR on GPU; Tesseract on CPU |
| `judge` | scores audit items with an open-weight judge behind an OpenAI-compatible server | Qwen2.5-7B-Instruct, Apache-2.0, served by vLLM | yes |
| `compile` | cuts the fetched OCR text into the corpus's pages and passages | none: the corpus builder's own code | no |

Every job is cut into units. Each unit writes one output file, with its checksum, to the project's
private Cloudflare R2 bucket, under a folder named by the job's build key. A finished unit is never
run again. A stopped job resumes where it stopped. A manifest lists every output once all are done.

## What the cluster needs to provide

- A namespace (or permission to create one), and a quota we stay under. The quota values file sets
  CPU, memory, GPUs and storage, and a ResourceQuota enforces them.
- GPU nodes with the NVIDIA device plugin, and the node label that names the GPU model.
- A default StorageClass, used for a per-pod scratch volume (model downloads and staging).
- Two Secrets, created by the cluster's owner or by Jake, referenced by name only:
  - `archive-argues-r2`, holding `R2_ENDPOINT`, `R2_BUCKET`, `R2_ACCESS_KEY_ID` and
    `R2_SECRET_ACCESS_KEY`;
  - optionally `archive-argues-workers-ai`.

  Their values never appear in this repository, in manifests or in logs.
- Pull access to the job images. They are built from `docker/jobs/Dockerfile`, targets `cpu` and
  `gpu`.

Pods run as a non-root user. They have no privilege escalation, every capability dropped, a
read-only root filesystem, the default seccomp profile and no service account token. Every object
carries the label `app.kubernetes.io/part-of=archive-argues` and a contact annotation
(hello@archiveargues.org).

## Start, stop, resume, remove

1. Copy `k8s/values.example.toml` to `k8s/values.toml` and fill in the namespace, the images, the
   GPU type and the quota.
2. Prepare a job's input once, from any machine with the R2 credentials:
   `python scripts/v2/jobs.py prepare embed-sample --store r2 ...`
3. Start it:
   `python scripts/v2/cluster.py up --values k8s/values.toml --job embed-sample`
   This applies the namespace (if we may create it), the quota and an Indexed Job.
4. Watch it with `python scripts/v2/cluster.py status --values k8s/values.toml`.
5. Finish it with `python scripts/v2/cluster.py finish --values k8s/values.toml --job embed-sample`,
   which writes and verifies the manifest.

**Stopping** is `kubectl delete job job-embed-sample -n <namespace>`, or `down` below. Finished
units stay finished.

**Resuming** is `up` again. Pods skip every unit that is already done.

**Removing everything** is `python scripts/v2/cluster.py down --values k8s/values.toml`. It deletes
every job, pod, volume claim, deployment, service, quota and config map carrying our label, and the
namespace if we created it. The outputs stay in our R2 bucket, outside the cluster.

## How much it uses (estimates)

Whole-collection sizes come from a sizing sample (200 items, 95% intervals): 16 to 24 million
scanned pages, and 25 to 50 million passages. The shard plan estimates 36 million.

- **embed.** Measured on this laptop's CPU at 17.7 passages a second, that is 388 to 789 CPU-hours.
  On a GPU it is passages divided by the GPU's measured rate. We have not measured a GPU rate. For
  planning only, 1,000 to 5,000 passages a second per GPU gives 2 to 14 GPU-hours. The first GPU
  run measures it (`jobs.py run --max-units 1`) before anything is scheduled at scale.
- **ocr.** Only the worst pages are re-read: the pages whose OCR confidence is lowest, a share chosen
  after the engine comparison. The time per page is measured on our own sample (see the comparison
  report); GPU-hours are pages times that.
- **judge.** About 2,000 output tokens per item at temperature 0. The GPU-hours depend on the items
  chosen. Benchmark-sized runs are hundreds to a few thousand items.
- **compile.** CPU only, minutes per thousand items. It is dominated by reading the text from R2.

The owner's cost is the GPU-hours times their own rate. Storage is in our R2 bucket and costs the
owner nothing. Network is the pods reading inputs from and writing outputs to R2.

## Serving a model from the cluster

An open-weight writer or judge can also be served from the cluster for as long as it is lent. The
server is a Deployment with an OpenAI-compatible API. The model comes from a preset in the values
file:

| Preset | Model and hardware |
|---|---|
| `mistral-small-4-nvfp4-96gb` | Mistral Small 4, NVFP4, one 96 GB GPU |
| `mistral-small-4-tp2-80gb` | Mistral Small 4, two 80 GB GPUs |
| `gpt-oss-120b` | gpt-oss-120b, one 80 GB GPU |
| `ministral-3-14b` | Ministral 3 14B, one 24 GB GPU |
| `ollama-cpu` | a CPU check of the same API with a small model |

Each preset uses the vLLM flags from its model card. Our changes only shorten the context and cap
concurrent requests.

The server has startup, readiness and liveness probes. It is reachable only through an outbound-only
Cloudflare Tunnel:

- no Ingress, LoadBalancer or NodePort;
- a NetworkPolicy that admits only the tunnel's pods;
- no public port opened on anyone's cluster.

```
python scripts/v2/cluster.py render --values k8s/values.toml --job serve    # look first
python scripts/v2/cluster.py up --values k8s/values.toml --job serve
python scripts/v2/cluster.py down --values k8s/values.toml                  # removes it with everything else
```

Jake's steps (the token and DNS are his):

1. In Cloudflare Zero Trust, create a tunnel (for example `archive-argues-model`). Copy its token.
2. Give the tunnel a public hostname, for example `model.archiveargues.org`, pointing to
   `http://model-server:8000` (`http://model-server:11434` for the CPU preset).
3. Create an Access application for that hostname with a Service Auth policy that admits only one
   service token, `archive-argues-engine`. Copy the token's client id and secret.
4. In the cluster's namespace, create the tunnel Secret:
   `kubectl -n <namespace> create secret generic archive-argues-tunnel --from-literal=token=<tunnel token>`.
   The values file names it in `[secrets] tunnel`.
5. Give the engine Worker the service token as secrets (`wrangler secret put CF_ACCESS_CLIENT_ID` and
   `CF_ACCESS_CLIENT_SECRET`). Set its `openai_compat` provider's base URL to
   `https://model.archiveargues.org/v1`. Every request then carries the two `CF-Access-Client-*` headers.
6. When the loan ends: `cluster.py down`, then delete the tunnel, the Access application and the
   service token.

## Credit

When a cluster is lent, the site's About page and the release notes say: "Batch processing for the
whole collection ran on compute donated by <owner>." We use the owner's wording, and only with their
agreement.

## Choosing the OCR engine

Measured on 24 of our own pages: microlog pages with poor but readable text (passage quality score
0.35 or more, which skips charts and blank scans). Every engine read the same archive.org scans.
The proxy is the share of each page's words, three letters or longer, that a lexicon built from the
collection's cleanest passages knows. It is not an error rate. A person-checked sample is still
needed before the choice is final.

| Text | Lexicon proxy (mean) | Seconds per page on a laptop CPU |
|---|---:|---:|
| the existing OCR | 0.68 | n/a |
| Tesseract 5.3 | 0.69 | 2.7 |
| docTR 0.10 (pretrained) | 0.81 | 16.0 |

docTR scored higher than Tesseract on 14 pages and lower on 6. The mean difference is +0.06, with a
95% bootstrap interval of -0.01 to +0.13 over 21 pages: probably better, not yet shown. docTR is the
provisional choice for GPU runs, where its speed matters less. PaddleOCR has not been measured yet.

## What has been tested

Tested on 2026-11-01:

- **Every job on CPU, in the jobs image:**
  - `embed`: 600 microlog passages in 3 units, about 30 passages a second.
  - `ocr`: Tesseract on 12 worst pages, and both engines on 24 evaluation pages (above).
  - `judge`: 6 audit items through a local Ollama server running Qwen2.5-7B-Instruct. Every reply
    was readable, at about 25 seconds an item on this laptop.

  Each job finished, wrote its manifest and verified it.
- **`compile` through the job runner on this machine**, on R2: 214 items of the bc_govpubs
  sub-collection in 11 units. On two pilot items, its pages were checked page by page against the
  corpus: every page matched.
- **A local kind cluster** (Kubernetes 1.31, no GPU):
  - the CPU image ran `embed` as an Indexed Job with two pods, each with a scratch volume, reading
    and writing R2 through a Secret referenced by name;
  - the finish Job wrote and verified the manifest;
  - `down` removed every object and the namespace.

Not tested: GPU scheduling, the GPU image, vLLM, multi-node runs, and quotas under contention.
