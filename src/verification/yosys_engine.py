"""Yosys formal-equivalence backend.

The backend keeps the two designs in separate Yosys design stashes before
constructing the equivalence/miter module.  That allows the common course
pattern where both files define the same top-module name without rewriting
source files or touching the golden RTL.
"""

from pathlib import Path
import re
import time
from typing import Iterable, List, Optional, Tuple

from .config import VerificationConfig, resolve_command
from .process import CommandResult, run_command


_PROVEN_ZERO_UNPROVEN_RE = re.compile(
    r"of those cells\s+\d+\s+are proven and\s+0\s+are unproven",
    re.IGNORECASE,
)
_PROVEN_NONZERO_UNPROVEN_RE = re.compile(
    r"of those cells\s+\d+\s+are proven and\s+([1-9]\d*)\s+are unproven",
    re.IGNORECASE,
)
_ASSERT_UNPROVEN_RE = re.compile(
    r"error:\s*found\s+(?:([1-9]\d*)\s+)?unproven\s+\$equiv\s+cells",
    re.IGNORECASE,
)
_MISSING_TOP_RE = re.compile(r"module\s+[`'\"]?[^`'\"]+[`'\"]?\s+not found", re.IGNORECASE)
_COUNTEREXAMPLE_ROW_RE = re.compile(r"^\s*(?:(\d+)\s+)?\\(\S+)\s+(\S+)\s+(\S+)\s+(\S+)\s*$")


def _quote_yosys(value: str) -> str:
    """Quote a path or argument using Yosys double-quote syntax."""
    normalized = str(value).replace("\\", "/")
    escaped = normalized.replace('"', '\\"')
    return '"' + escaped + '"'


def _read_command(
    sources: Iterable[Path], include_dirs: Iterable[Path], defines: Iterable[str]
) -> str:
    flags = ["read_verilog", "-formal", "-sv"]
    for include_dir in include_dirs:
        flags.extend(["-I", _quote_yosys(str(include_dir))])
    for define in defines:
        flags.extend(["-D", _quote_yosys(str(define))])
    flags.extend(_quote_yosys(str(source)) for source in sources)
    return " ".join(flags)


def _stash_design_lines(
    sources: Iterable[Path],
    top: str,
    stash_name: str,
    *,
    include_dirs: Iterable[Path],
    defines: Iterable[str],
    sequential: bool,
) -> List[str]:
    prep_steps = "proc; flatten; async2sync; opt_clean" if sequential else "proc; flatten; opt_clean"
    return [
        _read_command(sources, include_dirs, defines),
        "hierarchy -check -top %s" % top,
        prep_steps,
        "design -stash %s" % stash_name,
        "design -reset",
    ]


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
    """Build a deterministic Yosys formal-equivalence script.

    - Combinational Stage 1 uses ``equiv_make`` + ``equiv_struct -icells`` +
      ``equiv_simple -undef`` + ``equiv_status -assert`` so large circuits with
      shared sub-cones (such as 16-bit combinational dividers) prove in
      sub-second time.  If unproven cells remain, :func:`run_yosys_formal`
      automatically runs Stage 2 (:func:`build_combinational_miter_script`)
      using full ``miter -equiv`` + ``sat -verify`` to handle structurally
      distinct rewrites and emit concrete SAT counterexamples.
    - Sequential designs run ``async2sync`` before ``equiv_make`` +
      ``equiv_struct -icells`` + ``equiv_simple`` + ``equiv_induct`` +
      ``equiv_status -assert`` so designs with asynchronous resets (``$adff``)
      are handled cleanly.
    """
    extra = tuple(extra_sources)
    gold_sources = (Path(golden),) + extra
    gate_sources = (Path(candidate),) + extra
    lines: List[str] = []
    lines.extend(
        _stash_design_lines(
            gold_sources,
            top,
            "gold",
            include_dirs=include_dirs,
            defines=defines,
            sequential=sequential,
        )
    )
    lines.extend(
        _stash_design_lines(
            gate_sources,
            top,
            "gate",
            include_dirs=include_dirs,
            defines=defines,
            sequential=sequential,
        )
    )
    lines.extend(
        [
            "design -copy-from gold -as gold %s" % top,
            "design -copy-from gate -as gate %s" % top,
            "equiv_make gold gate equiv",
            "prep -top equiv",
            "equiv_struct -icells",
        ]
    )
    if sequential:
        steps = max(1, int(induction_steps))
        lines.extend(
            [
                "equiv_simple -undef -seq %d" % steps,
                "equiv_induct -undef -seq %d" % steps,
                "equiv_status -assert",
            ]
        )
    else:
        lines.extend(
            [
                "equiv_simple -undef",
                "equiv_status -assert",
            ]
        )
    return "\n".join(lines) + "\n"


def build_combinational_miter_script(
    golden: str,
    candidate: str,
    top: str,
    *,
    extra_sources: Iterable[Path] = (),
    include_dirs: Iterable[Path] = (),
    defines: Iterable[str] = (),
) -> str:
    """Build a full combinational miter-SAT script for proof or counterexample."""
    extra = tuple(extra_sources)
    gold_sources = (Path(golden),) + extra
    gate_sources = (Path(candidate),) + extra
    lines: List[str] = []
    lines.extend(
        _stash_design_lines(
            gold_sources,
            top,
            "gold",
            include_dirs=include_dirs,
            defines=defines,
            sequential=False,
        )
    )
    lines.extend(
        _stash_design_lines(
            gate_sources,
            top,
            "gate",
            include_dirs=include_dirs,
            defines=defines,
            sequential=False,
        )
    )
    lines.extend(
        [
            "design -copy-from gold -as gold %s" % top,
            "design -copy-from gate -as gate %s" % top,
            "miter -equiv -flatten -make_outputs gold gate miter",
            "hierarchy -top miter",
            "opt_clean",
            "sat -verify -prove trigger 0 -show-inputs -show-outputs -set-def-inputs miter",
        ]
    )
    return "\n".join(lines) + "\n"


def build_sequential_bmc_script(
    golden: str,
    candidate: str,
    top: str,
    *,
    extra_sources: Iterable[Path] = (),
    include_dirs: Iterable[Path] = (),
    defines: Iterable[str] = (),
    steps: int = 4,
    reset: Optional[str] = None,
    reset_active_low: bool = False,
) -> str:
    """Build a bounded miter-SAT script to search for sequential counterexamples."""
    extra = tuple(extra_sources)
    gold_sources = (Path(golden),) + extra
    gate_sources = (Path(candidate),) + extra
    lines: List[str] = []
    lines.extend(
        _stash_design_lines(
            gold_sources,
            top,
            "gold",
            include_dirs=include_dirs,
            defines=defines,
            sequential=True,
        )
    )
    lines.extend(
        _stash_design_lines(
            gate_sources,
            top,
            "gate",
            include_dirs=include_dirs,
            defines=defines,
            sequential=True,
        )
    )
    lines.extend(
        [
            "design -copy-from gold -as gold %s" % top,
            "design -copy-from gate -as gate %s" % top,
            "miter -equiv -flatten -make_outputs gold gate miter",
            "hierarchy -top miter",
            "opt_clean",
        ]
    )
    sat_parts = [
        "sat",
        "-seq %d" % max(1, int(steps)),
        "-verify",
        "-prove trigger 0",
        "-set-init-zero",
        "-set-def-inputs",
    ]
    if reset:
        active = "0" if reset_active_low else "1"
        inactive = "1" if reset_active_low else "0"
        sat_parts.append("-set-at 1 in_%s %s" % (reset, active))
        if steps >= 2:
            sat_parts.append("-set-at 2 in_%s %s" % (reset, inactive))
    sat_parts.extend(["-show-inputs", "-show-outputs", "miter"])
    lines.append(" ".join(sat_parts))
    return "\n".join(lines) + "\n"


def classify_yosys_result(
    returncode: Optional[int], output: str, timed_out: bool = False
) -> Tuple[str, Optional[bool], Optional[str]]:
    """Map Yosys output to the project status contract.

    A non-zero exit is not automatically a functional mismatch.  Unknown,
    unsupported, syntax, interface, and unproven results remain
    ``equivalent=None``.
    """
    if timed_out:
        return ("timeout", None, "timeout")
    if returncode is None:
        return ("error", None, "tool_error")

    text = (output or "").lower()

    # 1. Explicit functional inequivalence / SAT counterexample.
    non_equiv_markers = (
        "sat proof finished - model found: fail",
        "called with -verify and proof did fail",
        "counterexample",
        "outputs mismatch",
        "not equivalent",
        "equivalence failed",
    )
    if any(marker in text for marker in non_equiv_markers):
        return ("failed", False, "not_equivalent")

    # 2. Clean zero exit: require positive proof markers and zero unproven cells.
    if returncode == 0:
        if "unsupported" in text or "no sat model available" in text:
            return ("error", None, "unsupported")
        if _PROVEN_NONZERO_UNPROVEN_RE.search(text) or _ASSERT_UNPROVEN_RE.search(text):
            return ("error", None, "unproven")

        proven_markers = (
            "sat proof finished - no model found: success",
            "equivalence successfully proven",
            "no unproven $equiv cells",
            "all gold and gate signals have been proven equivalent",
        )
        if any(marker in text for marker in proven_markers) or _PROVEN_ZERO_UNPROVEN_RE.search(text):
            return ("success", True, None)
        if "unproven" in text or "unknown" in text:
            return ("error", None, "unproven")
        return ("error", None, "missing_proof")

    # 3. Non-zero exit without a counterexample: classify failure precisely.
    interface_markers = (
        "no matching port in gate module",
        "no matching port in gold module",
        "can't match gate port",
        "can't match gold port",
        "port width mismatch",
        "different port",
        "incompatible port",
        "cannot match port",
    )
    if any(marker in text for marker in interface_markers):
        return ("error", None, "interface_mismatch")

    if _MISSING_TOP_RE.search(text):
        return ("error", None, "missing_top")

    syntax_markers = (
        "syntax error",
        "parser error",
        "unexpected token",
        "can't open input file",
    )
    if any(marker in text for marker in syntax_markers):
        return ("error", None, "syntax_error")

    if "unsupported" in text or "no sat model available" in text:
        return ("error", None, "unsupported")

    if _ASSERT_UNPROVEN_RE.search(text) or _PROVEN_NONZERO_UNPROVEN_RE.search(text) or "unproven" in text or "unknown" in text:
        return ("error", None, "unproven")

    return ("error", None, "tool_error")


def summarize_yosys_error(output: str, error_type: Optional[str], max_chars: int = 800) -> str:
    """Extract a concise, high-signal summary from a Yosys log for A/D feedback."""
    lines = [line.rstrip() for line in (output or "").splitlines() if line.strip()]
    if not lines:
        return "verification failed without a diagnostic"

    if error_type == "not_equivalent":
        seq_steps: List[Tuple[Optional[str], str, str, str]] = []
        for line in lines:
            match = _COUNTEREXAMPLE_ROW_RE.match(line)
            if match:
                step, sig_name, dec_val, hex_val, _bin_val = match.groups()
                seq_steps.append((step, sig_name, dec_val, hex_val))
        if seq_steps:
            # For sequential SAT tables, pick the earliest step where trigger=1
            # (or where a gold_* / gate_* output diverges) instead of the final step.
            has_steps = any(step is not None for step, *_ in seq_steps)
            if has_steps:
                grouped: dict = {}
                step_order: List[str] = []
                for step, sig_name, dec_val, hex_val in seq_steps:
                    key = step if step is not None else "0"
                    if key not in grouped:
                        grouped[key] = []
                        step_order.append(key)
                    grouped[key].append((sig_name, dec_val, hex_val))

                target_step = step_order[-1]
                for key in step_order:
                    rows = grouped[key]
                    trig = [dec for name, dec, _ in rows if name == "trigger"]
                    if any(v not in ("0", "--") for v in trig):
                        target_step = key
                        break
                    gold_vals = {name[5:]: dec for name, dec, _ in rows if name.startswith("gold_")}
                    gate_vals = {name[5:]: dec for name, dec, _ in rows if name.startswith("gate_")}
                    if any(gold_vals.get(k) != gate_vals.get(k) for k in gold_vals if k in gate_vals):
                        target_step = key
                        break
                chosen = [
                    "%s=%s(0x%s)" % (name, dec, hx)
                    for name, dec, hx in grouped[target_step]
                    if name != "trigger"
                ]
                summary = "counterexample found (step %s): %s" % (target_step, ", ".join(chosen[:16]))
                return summary[:max_chars]

            cex_entries = [
                "%s=%s(0x%s)" % (sig_name, dec_val, hex_val)
                for _step, sig_name, dec_val, hex_val in seq_steps
                if sig_name != "trigger"
            ]
            if cex_entries:
                summary = "counterexample found: " + ", ".join(cex_entries[:16])
                return summary[:max_chars]

    if error_type == "unproven":
        picked = [
            line.strip()
            for line in lines
            if "trying to prove $equiv" in line.lower() and "failed" in line.lower()
            or line.strip().lower().startswith("error:")
        ]
        if picked:
            return " | ".join(picked[:8])[:max_chars]

    error_lines = [line.strip() for line in lines if line.strip().lower().startswith("error:")]
    if error_lines:
        return " | ".join(error_lines[-4:])[:max_chars]

    compact = " ".join(lines)
    return compact[-max_chars:]


def _execute_yosys_script(
    script: str,
    *,
    script_path: Path,
    log_path: Path,
    config: VerificationConfig,
    timeout_seconds: float,
    run_dir: Path,
) -> CommandResult:
    """Write a Yosys script and run it, capturing flushed `-l` output when available."""
    script_path.write_text(script, encoding="utf-8")
    tool_log = run_dir / (script_path.stem + "_yosys_raw.log")
    if tool_log.exists():
        tool_log.unlink()

    command = resolve_command(config.yosys_bin, "YOSYS_BIN", "yosys")
    if isinstance(command, str):
        command = [command]
    full_cmd = list(command) + ["-l", str(tool_log), "-s", str(script_path)]
    process_result = run_command(
        full_cmd,
        timeout_seconds=timeout_seconds,
        log_path=log_path,
        cwd=run_dir,
    )
    if tool_log.is_file():
        raw_text = tool_log.read_text(encoding="utf-8", errors="replace")
        try:
            tool_log.unlink()
        except OSError:
            pass
        if raw_text.strip():
            merged_output = raw_text
            if process_result.output.strip() and process_result.output.strip() not in raw_text:
                stderr_errors = [
                    line
                    for line in process_result.output.splitlines()
                    if line.strip().startswith("ERROR:") and line.strip() not in raw_text
                ]
                if stderr_errors:
                    merged_output = merged_output.rstrip() + "\n" + "\n".join(stderr_errors) + "\n"
            header = log_path.read_text(encoding="utf-8", errors="replace").splitlines()[:1]
            prefix = (header[0] + "\n") if header else ""
            if process_result.timed_out:
                prefix += "[timeout]\n"
            log_path.write_text(prefix + merged_output, encoding="utf-8")
            process_result = CommandResult(
                command=process_result.command,
                returncode=process_result.returncode,
                output=merged_output,
                timed_out=process_result.timed_out,
            )
    return process_result


def run_yosys_formal(
    golden: Path,
    candidate: Path,
    config: VerificationConfig,
    run_dir: Path,
) -> Tuple[Tuple[str, Optional[bool], Optional[str]], CommandResult, str]:
    """Execute the Yosys script and return classification, process result and script."""
    started = time.monotonic()
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
    log_path = run_dir / "yosys.log"
    process_result = _execute_yosys_script(
        script,
        script_path=script_path,
        log_path=log_path,
        config=config,
        timeout_seconds=config.timeout_seconds,
        run_dir=run_dir,
    )
    classification = classify_yosys_result(
        process_result.returncode, process_result.output, process_result.timed_out
    )

    # Stage 2 for combinational designs: when structural equivalence leaves
    # unproven $equiv cells (e.g. structurally rewritten arithmetic or a real
    # bug), run full miter-SAT within the remaining timeout to either prove
    # equivalence or extract a concrete counterexample.
    if not config.sequential and classification == ("error", None, "unproven"):
        remaining = config.timeout_seconds - (time.monotonic() - started)
        if remaining > 1.0:
            miter_script = build_combinational_miter_script(
                str(golden),
                str(candidate),
                config.top or "top",
                extra_sources=config.extra_sources,
                include_dirs=config.include_dirs,
                defines=config.defines,
            )
            miter_result = _execute_yosys_script(
                miter_script,
                script_path=run_dir / "equivalence_miter.ys",
                log_path=run_dir / "yosys_miter.log",
                config=config,
                timeout_seconds=remaining,
                run_dir=run_dir,
            )
            miter_class = classify_yosys_result(
                miter_result.returncode, miter_result.output, miter_result.timed_out
            )
            combined_output = (
                process_result.output.rstrip()
                + "\n\n=== Combinational Miter-SAT Stage 2 ===\n"
                + miter_result.output
            )
            log_path.write_text(combined_output, encoding="utf-8")
            return miter_class, miter_result, script

    # For sequential designs where induction leaves unproven $equiv cells,
    # run a bounded miter-SAT falsification pass within the remaining timeout
    # to catch concrete counterexamples without falsely promoting unproven to pass.
    if config.sequential and classification == ("error", None, "unproven"):
        remaining = config.timeout_seconds - (time.monotonic() - started)
        if remaining > 1.0:
            bmc_script = build_sequential_bmc_script(
                str(golden),
                str(candidate),
                config.top or "top",
                extra_sources=config.extra_sources,
                include_dirs=config.include_dirs,
                defines=config.defines,
                steps=max(1, int(config.induction_steps)),
                reset=config.reset,
                reset_active_low=config.reset_active_low,
            )
            bmc_result = _execute_yosys_script(
                bmc_script,
                script_path=run_dir / "sequential_bmc.ys",
                log_path=run_dir / "yosys_bmc.log",
                config=config,
                timeout_seconds=remaining,
                run_dir=run_dir,
            )
            bmc_class = classify_yosys_result(
                bmc_result.returncode, bmc_result.output, bmc_result.timed_out
            )
            if bmc_class == ("failed", False, "not_equivalent"):
                combined_output = (
                    process_result.output.rstrip()
                    + "\n\n=== Sequential BMC Counterexample Check ===\n"
                    + bmc_result.output
                )
                log_path.write_text(combined_output, encoding="utf-8")
                process_result = CommandResult(
                    command=bmc_result.command,
                    returncode=bmc_result.returncode,
                    output=bmc_result.output,
                    timed_out=False,
                )
                return bmc_class, process_result, script

    return classification, process_result, script
