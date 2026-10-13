"""Configuration for the standalone verification worker."""

from dataclasses import dataclass, field
import os
from pathlib import Path
from typing import Dict, Iterable, Optional, Sequence, Tuple, Union


Command = Union[str, Sequence[str]]


def _as_path_tuple(values: Iterable[Union[str, Path]]) -> Tuple[Path, ...]:
    return tuple(Path(value) for value in values)


@dataclass
class VerificationConfig:
    """Inputs needed to reproduce one verification run.

    The first two arguments of ``verify`` remain the public minimum.  This
    object carries the context that cannot be safely guessed for sequential or
    multi-file designs.
    """

    top: Optional[str] = None
    extra_sources: Tuple[Path, ...] = field(default_factory=tuple)
    include_dirs: Tuple[Path, ...] = field(default_factory=tuple)
    defines: Tuple[str, ...] = field(default_factory=tuple)
    timeout_seconds: float = 120.0
    run_dir: Optional[Path] = None
    yosys_bin: Optional[Command] = None
    iverilog_bin: Optional[Command] = None
    vvp_bin: Optional[Command] = None
    mode: str = "formal"
    testbench: Optional[Path] = None
    observed_outputs: Tuple[str, ...] = field(default_factory=tuple)
    sequential: bool = False
    clock: Optional[str] = None
    reset: Optional[str] = None
    reset_active_low: bool = False
    induction_steps: int = 4

    def __post_init__(self) -> None:
        self.extra_sources = tuple(path.expanduser().resolve() for path in _as_path_tuple(self.extra_sources))
        self.include_dirs = tuple(path.expanduser().resolve() for path in _as_path_tuple(self.include_dirs))
        if self.run_dir is not None:
            self.run_dir = Path(self.run_dir).expanduser().resolve()
        if self.testbench is not None:
            self.testbench = Path(self.testbench).expanduser().resolve()
        self.observed_outputs = tuple(str(name) for name in self.observed_outputs)


def parse_env_file(path: Path) -> Dict[str, str]:
    """Parse the simple KEY=VALUE format used by ``tools.env``."""
    values: Dict[str, str] = {}
    if not path.is_file():
        return values
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip().strip("\"'")
    return values


def find_tools_env(start: Optional[Path] = None) -> Dict[str, str]:
    """Load ``tools.env`` from an explicit env path or nearby working tree."""
    explicit = os.environ.get("RTL_TOOLS_ENV")
    candidates = []
    if explicit:
        candidates.append(Path(explicit))
    if start is not None:
        candidates.append(Path(start) / "tools.env")
    candidates.append(Path.cwd() / "tools.env")
    for candidate in candidates:
        values = parse_env_file(candidate)
        if values:
            return values
    return {}


def resolve_command(config_value: Optional[Command], key: str, default: str) -> Command:
    """Resolve config > environment > tools.env > PATH default."""
    if config_value:
        return config_value
    env_value = os.environ.get(key)
    if env_value:
        return env_value
    tools_value = find_tools_env().get(key)
    return tools_value or default
