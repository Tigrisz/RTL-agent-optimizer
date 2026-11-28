"""Test-only temporary directories using the OS temp folder (no repo clutter)."""

from contextlib import contextmanager
from pathlib import Path
import tempfile


@contextmanager
def workspace_tempdir():
    with tempfile.TemporaryDirectory(prefix="rtl-verify-test-") as tmp:
        yield Path(tmp)
