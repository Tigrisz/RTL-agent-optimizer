"""Yosys formal-equivalence backend.

The backend keeps the two designs in separate Yosys design stashes before
constructing the equivalence module.  That allows the common course pattern
where both files define the same top-module name without rewriting source
files or touching the golden RTL.
"""

from pathlib import Path
import re
from typing import Iterable, Optional, Tuple

from .config import VerificationConfig, resolve_command
from .process import CommandResult, run_command


def _quote_yosys(value: str) -> str:
    normalized = str(value).replace("\\", "/")
    return "'" + normalized.replace("'", "\\'") + "'"


def _read_command(
    sources: Iterable[Path], include_dirs: Iterable[Path], defines: Iterable[str]
) -> str:
    flags = ["read_verilog", "-formal", "-sv"]
    for include_dir in include_dirs:
        flags.extend(["-I", _quote_yosys(str(include_dir))])
    for define in defines:
        flags.extend(["-D", _quote_yosys(str(define))])
    flags.extend(_quote_yosys(str(source)) for source in sources)
    return " ".join(flags) + ";"


def build_equivalence_script(
    golden: str,
    candidate: str,
    top: str,
    *,
    extra_sources: Iterable[Path] = (),
    include_dirs: Iterable[Path] = (),
    defines: Iterable[str] = (),
    sequential: bool = False,
    induction_steps: int = 4,
) -> str:
    """Build a deterministic Yosys equivalence script."""
    extra = tuple(extra_sources)
    gold_sources = (Path(golden),) + extra
    gate_sources = (Path(candidate),) + extra
    lines = [
        _read_command(gold_sources, include_dirs, defines),
        "hierarchy -top %s;" % top,
        "proc; flatten; opt_clean; design -stash gold;",
        "design -reset;",
        _read_command(gate_sources, include_dirs, defines),
        "hierarchy -top %s;" % top,
        "proc; flatten; opt_clean; design -stash gate;",
        "design -reset;",
        "design -copy-from gold -as gold %s;" % top,
        "design -copy-from gate -as gate %s;" % top,
        "equiv_make gold gate equiv;",
        "prep -top equiv;",
    ]
    if sequential:
        lines.append("equiv_simple -undef -seq %d;" % max(1, induction_steps))
        lines.append("equiv_induct -undef -seq %d;" % max(1, induction_steps))
    else:
        lines.append("equiv_simple -undef;")
    lines.append("equiv_status -assert;")
    return "\n".join(lines) + "\n"


def classify_yosys_result(
    returncode: Optional[int], output: str, timed_out: bool = False
) -> Tuple[str, Optional[bool], Optional[str]]:
    """Map Yosys output to the project status contract.

    A non-zero exit is not automatically a functional mismatch.  Unknown,
    unsupported, and unproven results remain ``equivalent=None``.
    """
    if timed_out:
        return ("timeout", None, "timeout")
    text = (output or "").lower()
    if returncode is None:
        return ("error", None, "tool_error")
    if any(token in text for token in ("counterexample", "mismatch", "not equivalent", "equivalence failed")):
        return ("failed", False, "not_equivalent")
    if returncode == 0:
        if "unsupported" in text:
            return ("error", None, "unsupported")
        if "unproven" in text or "unknown" in text:
            return ("error", None, "unproven")
        proven_markers = (
            "equivalence successfully proven",
            "no unproven $equiv cells",
            "all gold and gate signals have been proven equivalent",
        )
        if any(marker in text for marker in proven_markers):
            return ("success", True, None)
        return ("error", None, "missing_proof")
    if "unproven" in text or "unknown" in text:
        return ("error", None, "unproven")
    if "unsupported" in text:
        return ("error", None, "unsupported")
    return ("error", None, "tool_error")


def run_yosys_formal(
    golden: Path,
    candidate: Path,
    config: VerificationConfig,
    run_dir: Path,
) -> Tuple[Tuple[str, Optional[bool], Optional[str]], CommandResult, str]:
    """Execute the Yosys script and return classification, process result and script."""
    script = build_equivalence_script(
        str(golden),
        str(candidate),
        config.top or "top",
        extra_sources=config.extra_sources,
        include_dirs=config.include_dirs,
        defines=config.defines,
        sequential=config.sequential,
        induction_steps=config.induction_steps,
    )
    script_path = run_dir / "equivalence.ys"
    script_path.write_text(script, encoding="utf-8")
    log_path = run_dir / "yosys.log"
    command = resolve_command(config.yosys_bin, "YOSYS_BIN", "yosys")
    if isinstance(command, str):
        command = [command]
    command = list(command) + ["-p", script]
    process_result = run_command(
        command,
        timeout_seconds=config.timeout_seconds,
        log_path=log_path,
        cwd=run_dir,
    )
    classification = classify_yosys_result(
        process_result.returncode, process_result.output, process_result.timed_out
    )
    return classification, process_result, script
