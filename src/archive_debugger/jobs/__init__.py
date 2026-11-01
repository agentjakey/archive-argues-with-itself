"""Batch jobs for whatever compute is available (docs/CLUSTER.md, docs/formats/jobs.md).

One job spec, three executors. A job (embed, ocr, judge, compile) is described once in
config/jobs/<name>.toml; the same code runs it on this machine's CPU, through Workers AI where the
model exists there, or as a Kubernetes Indexed Job on GPU nodes. A job is cut into units (a shard of
passages, a list of pages, a batch of judge items). Each unit writes one output file to a store
(local folder or R2) named by the job's build key, so a stopped job resumes where it stopped and a
finished unit is never run twice. When every unit is done, a manifest lists every output with its
sha256 and size, and the job is complete only when the manifest checks."""
