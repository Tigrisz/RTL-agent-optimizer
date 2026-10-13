"""Test-only temporary directories under the writable repository workspace."""

from contextlib import contextmanager
import shutil
import tempfile
from pathlib import Path


@contextmanager
def workspace_tempdir():
    root = Path(__file__).resolve().parents[2] / ".test-tmp"
    root.mkdir(parents=True, exist_ok=True)
    path = Path(tempfile.mkdtemp(dir=str(root)))
    try:
        yield path
    finally:
        shutil.rmtree(str(path), ignore_errors=True)
