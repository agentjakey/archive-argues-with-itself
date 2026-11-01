"""Where jobs read inputs and write outputs: a local folder or the private R2 bucket. Both expose the
same five calls. R2 credentials come only from the environment (R2_ENDPOINT, R2_BUCKET,
R2_ACCESS_KEY_ID, R2_SECRET_ACCESS_KEY; a Kubernetes Secret referenced by name sets them in a pod),
and nothing about them is ever printed. Every write records the object's sha256 as metadata, so a
manifest can be checked without downloading anything twice."""
from __future__ import annotations

import hashlib
import io
import os
from pathlib import Path
from typing import Iterator, Optional

R2_ENV = ("R2_ENDPOINT", "R2_BUCKET", "R2_ACCESS_KEY_ID", "R2_SECRET_ACCESS_KEY")


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


class Store:
    def put(self, key: str, data: bytes) -> dict:
        raise NotImplementedError

    def get(self, key: str) -> bytes:
        raise NotImplementedError

    def head(self, key: str) -> Optional[dict]:
        """{"bytes", "sha256"} for an object, or None when it is absent."""
        raise NotImplementedError

    def list(self, prefix: str) -> Iterator[str]:
        raise NotImplementedError

    def describe(self) -> str:
        raise NotImplementedError


class LocalStore(Store):
    def __init__(self, root: Path):
        self.root = Path(root)

    def _path(self, key: str) -> Path:
        if ".." in Path(key).parts or key.startswith("/"):
            raise ValueError(f"unsafe key {key!r}")
        return self.root / key

    def put(self, key: str, data: bytes) -> dict:
        path = self._path(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_name(path.name + ".part")
        tmp.write_bytes(data)
        os.replace(tmp, path)
        meta = {"bytes": len(data), "sha256": sha256_bytes(data)}
        path.with_name(path.name + ".sha256").write_text(meta["sha256"] + "\n", encoding="ascii")
        return meta

    def get(self, key: str) -> bytes:
        return self._path(key).read_bytes()

    def head(self, key: str) -> Optional[dict]:
        path = self._path(key)
        if not path.exists():
            return None
        side = path.with_name(path.name + ".sha256")
        digest = side.read_text(encoding="ascii").strip() if side.exists() else sha256_bytes(path.read_bytes())
        return {"bytes": path.stat().st_size, "sha256": digest}

    def list(self, prefix: str) -> Iterator[str]:
        base = self._path(prefix) if prefix else self.root
        if not base.exists():
            return iter(())
        return (p.relative_to(self.root).as_posix() for p in sorted(base.rglob("*"))
                if p.is_file() and not p.name.endswith((".sha256", ".part")))

    def describe(self) -> str:
        return f"local:{self.root}"


class R2Store(Store):
    """The private bucket through its S3 API (boto3, imported only when used)."""

    def __init__(self, client=None, bucket: Optional[str] = None):
        missing = [v for v in R2_ENV if not os.environ.get(v)] if client is None else []
        if missing:
            raise RuntimeError(f"R2 store needs {', '.join(missing)} in the environment")
        if client is None:
            import boto3
            from botocore.config import Config
            client = boto3.client("s3", endpoint_url=os.environ["R2_ENDPOINT"],
                                  aws_access_key_id=os.environ["R2_ACCESS_KEY_ID"],
                                  aws_secret_access_key=os.environ["R2_SECRET_ACCESS_KEY"],
                                  region_name="auto", config=Config(retries={"max_attempts": 6, "mode": "standard"}))
        self.client = client
        self.bucket = bucket or os.environ["R2_BUCKET"]

    def put(self, key: str, data: bytes) -> dict:
        digest = sha256_bytes(data)
        self.client.put_object(Bucket=self.bucket, Key=key, Body=io.BytesIO(data), Metadata={"sha256": digest})
        return {"bytes": len(data), "sha256": digest}

    def get(self, key: str) -> bytes:
        return self.client.get_object(Bucket=self.bucket, Key=key)["Body"].read()

    def head(self, key: str) -> Optional[dict]:
        try:
            r = self.client.head_object(Bucket=self.bucket, Key=key)
        except Exception as exc:     # botocore ClientError with a 404 code, without importing botocore here
            code = str(getattr(exc, "response", {}).get("Error", {}).get("Code", ""))
            if code in ("404", "NoSuchKey", "NotFound"):
                return None
            raise
        return {"bytes": int(r["ContentLength"]), "sha256": (r.get("Metadata") or {}).get("sha256")}

    def list(self, prefix: str) -> Iterator[str]:
        token = None
        while True:
            kwargs = {"Bucket": self.bucket, "Prefix": prefix}
            if token:
                kwargs["ContinuationToken"] = token
            page = self.client.list_objects_v2(**kwargs)
            for obj in page.get("Contents") or []:
                yield obj["Key"]
            if not page.get("IsTruncated"):
                return
            token = page.get("NextContinuationToken")

    def describe(self) -> str:
        return f"r2:{self.bucket}"


def open_store(kind: str, local_root: Optional[Path] = None) -> Store:
    if kind == "local":
        return LocalStore(local_root or Path(os.environ.get("JOBS_LOCAL_STORE", "build/jobs-store")))
    if kind == "r2":
        return R2Store()
    raise ValueError(f"unknown store {kind!r}: local or r2")
