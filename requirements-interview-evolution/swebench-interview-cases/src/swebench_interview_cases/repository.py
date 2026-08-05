"""Immutable base-commit repository checkouts stored only in sealed cache."""

from __future__ import annotations

import hashlib
import json
import subprocess
import threading
from pathlib import Path
from typing import Any


class RepositoryError(RuntimeError):
    pass


_checkout_locks: dict[Path, threading.Lock] = {}
_checkout_locks_guard = threading.Lock()


def _run(command: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(command, cwd=cwd, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)


def prepare_checkout(*, repository: str, base_commit: str, alias: str, root: Path) -> dict[str, Any]:
    if "/" not in repository or not base_commit:
        raise RepositoryError("repository identity and base commit are required")
    checkout = root / alias
    with _checkout_locks_guard:
        lock = _checkout_locks.setdefault(checkout.resolve(), threading.Lock())
    with lock:
        return _prepare_checkout_locked(
            repository=repository, base_commit=base_commit, alias=alias,
            root=root, checkout=checkout,
        )


def _prepare_checkout_locked(
    *, repository: str, base_commit: str, alias: str, root: Path, checkout: Path,
) -> dict[str, Any]:
    if not (checkout / ".git").is_dir():
        checkout.mkdir(parents=True, exist_ok=False)
        initialized = _run(["git", "init"], checkout)
        if initialized.returncode != 0:
            raise RepositoryError(initialized.stderr[-2000:])
        remote = _run(["git", "remote", "add", "origin", f"https://github.com/{repository}.git"], checkout)
        if remote.returncode != 0:
            raise RepositoryError(remote.stderr[-2000:])
    head = _run(["git", "rev-parse", "HEAD"], checkout)
    if head.returncode != 0 or head.stdout.strip() != base_commit:
        fetched = _run(["git", "fetch", "--depth", "1", "--filter=blob:none", "origin", base_commit], checkout)
        if fetched.returncode != 0:
            raise RepositoryError(fetched.stderr[-2000:])
        switched = _run(["git", "switch", "--detach", base_commit], checkout)
        if switched.returncode != 0:
            raise RepositoryError(switched.stderr[-2000:])
    verified = _run(["git", "rev-parse", "HEAD"], checkout)
    status = _run(["git", "status", "--porcelain"], checkout)
    if verified.stdout.strip() != base_commit or status.returncode != 0 or status.stdout:
        raise RepositoryError("checkout is not clean at the required base commit")
    return {
        "alias": alias, "repository": repository, "base_commit": base_commit,
        "checkout_key": f"repositories/{alias}",
        "identity_sha256": hashlib.sha256(f"{repository}\0{base_commit}".encode()).hexdigest(),
    }


def prepare_pilot_checkouts(sealed_selection: dict[str, Any], root: Path) -> dict[str, Any]:
    entries = [
        prepare_checkout(
            repository=case["repository_family"], base_commit=case["public_source"]["base_commit"],
            alias=case["alias"], root=root,
        )
        for case in sealed_selection["cases"]
    ]
    return {"schema": "SWEbenchBaseCheckouts.v1", "entries": entries}
