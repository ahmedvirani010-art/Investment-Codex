"""Local Git is the publication boundary; a journal makes file replacement recoverable."""

import fcntl
import hashlib
import json
import os
import shutil
import subprocess
from contextlib import contextmanager
from pathlib import Path


class PublicationError(RuntimeError):
    pass


class LockBusy(RuntimeError):
    pass


def dumps(value) -> bytes:
    return (json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False, allow_nan=False) + "\n").encode()


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def atomic_write(path: Path, data: bytes):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    with tmp.open("wb") as handle:
        handle.write(data)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(tmp, path)


def git(root: Path, *args: str, check=True) -> subprocess.CompletedProcess:
    return subprocess.run(["git", "-C", str(root), *args], capture_output=True, check=check)


def committed(root: Path, path: str) -> bytes | None:
    result = git(root, "show", f"HEAD:{path}", check=False)
    return result.stdout if result.returncode == 0 else None


def read_json(root: Path, path: str, default=None):
    raw = committed(root, path)
    return json.loads(raw) if raw is not None else default


def head(root: Path) -> str | None:
    result = git(root, "rev-parse", "--verify", "HEAD", check=False)
    return result.stdout.decode().strip() if result.returncode == 0 else None


def safe_path(root: Path, relative: str) -> Path:
    path = root / relative
    if Path(relative).is_absolute() or ".." in Path(relative).parts or not path.resolve().is_relative_to(root.resolve()):
        raise PublicationError(f"unsafe publication path: {relative}")
    if path.is_symlink():
        raise PublicationError(f"publication target is a symlink: {relative}")
    return path


@contextmanager
def writer_lock(root: Path):
    runtime = root / ".runtime"
    runtime.mkdir(parents=True, exist_ok=True)
    with (runtime / "writer.lock").open("a+") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise LockBusy("another workspace writer is active") from exc
        try:
            yield
        finally:
            fcntl.flock(lock, fcntl.LOCK_UN)


def require_clean(root: Path):
    # User imports belong in ignored inputs/private; never silently overwrite edits.
    result = git(root, "status", "--porcelain=v1", "--untracked-files=normal")
    if result.stdout:
        raise PublicationError("working tree must be clean; commit or preserve your edits before running")


def prepare_repository(root: Path):
    root.mkdir(parents=True, exist_ok=True)
    created_ignore = False
    if not (root / ".git").exists():
        git(root, "init", "-q")
        if not (root / ".gitignore").exists():
            atomic_write(root / ".gitignore", b".runtime/\ninputs/private/\n.env\n")
            created_ignore = True
    if head(root) is None:
        # Do not include pre-existing files or user changes in an initial commit.
        if git(root, "diff", "--cached", "--name-only").stdout:
            raise PublicationError("pre-existing staged changes must be preserved before init")
        if created_ignore:
            git(root, "add", "--", ".gitignore")
        git(root, "-c", "user.name=Investment Workspace", "-c", "user.email=workspace@localhost", "commit", "--allow-empty", "-m", "workspace: initialize local publication history")


def rollback_pending(root: Path) -> dict | None:
    journal_path = root / ".runtime/pending.json"
    if not journal_path.exists():
        return None
    journal = json.loads(journal_path.read_bytes())
    stage = safe_path(root, journal["stage"])
    manifest_path = f"runs/{journal['run_id']}/manifest.json"
    expected = (stage / manifest_path).read_bytes()
    published = committed(root, manifest_path) == expected
    if not published and head(root) != journal["base_commit"]:
        raise PublicationError("HEAD changed during interrupted publication; preserve journal and inspect before recovery")
    for relative in journal["paths"]:
        path = safe_path(root, relative)
        candidate = (stage / relative).read_bytes()
        backup = stage / "_backup" / relative
        old = backup.read_bytes() if backup.exists() else None
        present = path.read_bytes() if path.exists() else None
        wanted = candidate if published else old
        if present not in (candidate, old, wanted):
            raise PublicationError(f"manual edit after interrupted publication: {relative}; recovery will not overwrite it")
        if wanted is None:
            path.unlink(missing_ok=True)
        elif present != wanted:
            atomic_write(path, wanted)
    if not published:
        git(root, "reset", "-q", "HEAD", "--", *journal["paths"])
    journal_path.unlink()
    return {**journal, "committed": published}


def publish(root: Path, stage: Path, paths: list[str], run_id: str, status: str) -> str:
    if (root / ".runtime/pending.json").exists():
        raise PublicationError("recover pending publication first")
    require_clean(root)
    base = head(root)
    for relative in paths:
        target = safe_path(root, relative)
        candidate = stage / relative
        if not candidate.is_file():
            raise PublicationError(f"missing staged output: {relative}")
        if target.exists():
            backup = stage / "_backup" / relative
            backup.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(target, backup)
    journal = {"run_id": run_id, "stage": str(stage.relative_to(root)), "paths": paths, "base_commit": base}
    atomic_write(root / ".runtime/pending.json", dumps(journal))
    try:
        for relative in paths:
            atomic_write(safe_path(root, relative), (stage / relative).read_bytes())
        if head(root) != base:
            raise PublicationError("HEAD changed before publication commit")
        git(root, "add", "--", *paths)
        git(root, "-c", "user.name=Investment Workspace", "-c", "user.email=workspace@localhost", "commit", "-q", "-m", f"research: portfolio {run_id} [{status}]")
        sha = head(root)
        atomic_write(root / ".runtime/publications" / f"{run_id}.json", dumps({"run_id": run_id, "commit": sha, "publication_status": "LOCAL_ONLY"}))
        (root / ".runtime/pending.json").unlink()
        return sha
    except Exception as exc:
        # Kernel lock survives only this invocation; disk journal survives interruption.
        raise PublicationError(f"publication interrupted; candidate retained at {stage}; run recover: {exc}") from exc
