"""Content identities and same-filesystem, atomic directory publication."""

import json
import os
import shutil
from collections.abc import Iterator
from contextlib import contextmanager
from hashlib import file_digest, sha256
from importlib.metadata import version
from pathlib import Path
from tempfile import mkdtemp

from . import __version__


def digest(path: Path) -> str:
    with path.open("rb") as handle:
        return file_digest(handle, "sha256").hexdigest()


def identity(value: object) -> str:
    return sha256(json.dumps(value, sort_keys=True, allow_nan=False).encode()).hexdigest()


def versions() -> dict[str, str]:
    return {
        "osp": __version__,
        **{name: version(name) for name in ("numpy", "scipy", "astropy", "pydantic", "PyYAML")},
    }


def write_json(path: Path, value: object) -> None:
    path.write_text(
        json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n", encoding="utf-8"
    )


def read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def object_id(value: str) -> str:
    if len(value) != 64 or any(c not in "0123456789abcdef" for c in value):
        raise ValueError("expected a SHA-256 identifier")
    return value


@contextmanager
def publish_directory(target: Path) -> Iterator[Path]:
    """Stage privately and publish without replacing an existing committed directory."""
    target.parent.mkdir(parents=True, exist_ok=True)
    temp = Path(mkdtemp(prefix=".osp-", dir=target.parent))
    try:
        yield temp
        for path in temp.rglob("*"):
            if path.is_file():
                with path.open("r+b") as handle:
                    os.fsync(handle.fileno())
        try:
            temp.rename(target)
        except OSError:
            if not target.is_dir():
                raise
    finally:
        shutil.rmtree(temp, ignore_errors=True)
