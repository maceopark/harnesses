"""Content-addressed storage for non-committed SWE-bench source material."""

from __future__ import annotations

import hashlib
import os
from dataclasses import dataclass
from pathlib import Path


class CacheError(RuntimeError):
    """Raised when cache integrity or capacity requirements are not met."""


def sha256_bytes(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def default_cache_root() -> Path:
    configured = os.environ.get("SWEBENCH_INTERVIEW_CACHE")
    if configured:
        return Path(configured).expanduser()
    if os.name == "nt":
        base = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
    elif sys_platform() == "darwin":
        base = Path.home() / "Library" / "Caches"
    else:
        base = Path(os.environ.get("XDG_CACHE_HOME", Path.home() / ".cache"))
    return base / "swebench-interview-cases"


def sys_platform() -> str:
    # Kept as a function so platform behavior is straightforward to unit test.
    import sys

    return sys.platform


@dataclass(frozen=True)
class CachedObject:
    key: str
    sha256: str
    size_bytes: int


class ContentAddressedCache:
    """Immutable SHA-256 addressed object storage.

    Absolute cache paths are deliberately never returned in serializable metadata.
    """

    def __init__(self, root: Path | str | None = None) -> None:
        self.root = Path(root) if root is not None else default_cache_root()
        self.objects = self.root / "objects" / "sha256"

    @staticmethod
    def key_for(digest: str) -> str:
        if len(digest) != 64 or any(c not in "0123456789abcdef" for c in digest):
            raise CacheError("invalid lowercase SHA-256 digest")
        return f"sha256:{digest}"

    def _path_for_digest(self, digest: str) -> Path:
        self.key_for(digest)
        return self.objects / digest[:2] / digest[2:]

    def put_bytes(self, content: bytes) -> CachedObject:
        digest = sha256_bytes(content)
        path = self._path_for_digest(digest)
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.exists():
            existing = path.read_bytes()
            if sha256_bytes(existing) != digest:
                raise CacheError(f"cache object is corrupt: {self.key_for(digest)}")
        else:
            temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
            temporary.write_bytes(content)
            os.replace(temporary, path)
        return CachedObject(self.key_for(digest), digest, len(content))

    def put_text(self, content: str) -> CachedObject:
        return self.put_bytes(content.encode("utf-8"))

    def get_bytes(self, key: str, expected_digest: str | None = None) -> bytes:
        prefix, separator, digest = key.partition(":")
        if separator != ":" or prefix != "sha256":
            raise CacheError("unsupported cache key")
        if expected_digest is not None and digest != expected_digest:
            raise CacheError("cache key and expected digest differ")
        path = self._path_for_digest(digest)
        try:
            content = path.read_bytes()
        except FileNotFoundError as exc:
            raise CacheError(f"cache miss: {key}") from exc
        if sha256_bytes(content) != digest:
            raise CacheError(f"cache object digest mismatch: {key}")
        return content

    def get_text(self, key: str, expected_digest: str | None = None) -> str:
        return self.get_bytes(key, expected_digest).decode("utf-8")
