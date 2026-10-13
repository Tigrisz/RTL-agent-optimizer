"""Safe external-process execution with complete logs and timeout handling."""

from dataclasses import dataclass
import os
from pathlib import Path
import shlex
import subprocess
from typing import Mapping, Optional, Sequence, Tuple, Union


Command = Union[str, Sequence[str]]


@dataclass
class CommandResult:
    command: Tuple[str, ...]
    returncode: Optional[int]
    output: str
    timed_out: bool = False


def _normalize_command(command: Command) -> Tuple[str, ...]:
    if isinstance(command, str):
        return (command,)
    return tuple(str(part) for part in command)


def _display_command(command: Sequence[str]) -> str:
    if os.name == "nt":
        return subprocess.list2cmdline(list(command))
    return shlex.join(list(command))


def _text(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return str(value)


def run_command(
    command: Command,
    *,
    timeout_seconds: float,
    log_path: Path,
    cwd: Optional[Path] = None,
    env: Optional[Mapping[str, str]] = None,
) -> CommandResult:
    """Run a tool, always writing command, stdout and stderr to ``log_path``."""
    normalized = _normalize_command(command)
    log_path.parent.mkdir(parents=True, exist_ok=True)
    header = "$ " + _display_command(normalized) + "\n"
    try:
        completed = subprocess.run(
            list(normalized),
            cwd=str(cwd) if cwd else None,
            env=dict(env) if env is not None else None,
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
            check=False,
        )
        output = _text(completed.stdout) + _text(completed.stderr)
        log_path.write_text(header + output, encoding="utf-8")
        return CommandResult(normalized, completed.returncode, output, False)
    except subprocess.TimeoutExpired as exc:
        output = _text(exc.stdout) + _text(exc.stderr)
        log_path.write_text(header + "[timeout]\n" + output, encoding="utf-8")
        return CommandResult(normalized, None, output, True)
    except (FileNotFoundError, PermissionError, OSError) as exc:
        output = "%s: %s" % (type(exc).__name__, exc)
        log_path.write_text(header + output + "\n", encoding="utf-8")
        return CommandResult(normalized, None, output, False)
