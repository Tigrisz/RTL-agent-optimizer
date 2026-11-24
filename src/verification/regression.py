"""Optional Icarus/VVP regression backend for bounded functional checks."""

from pathlib import Path
import re
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

from .config import VerificationConfig, resolve_command
from .process import run_command
from .result import VerificationResult


_SLICE_SUFFIX_RE = re.compile(r"\[[^\]]+\]$")


def _render_testbench(source: Path, vcd_path: Path, seed: int = 42) -> str:
    text = source.read_text(encoding="utf-8")
    vcd = str(vcd_path).replace("\\", "/").replace('"', '\\"')
    return (
        text.replace("__VCD__", vcd)
        .replace("`VCD_PATH", '"%s"' % vcd)
        .replace("__SEED__", str(seed))
    )


def _normalize_vcd_vector(raw_bits: str, width: int) -> str:
    """Normalize a VCD vector literal using IEEE 1364 left-extension rules."""
    bits = raw_bits.lower()
    if width <= 0:
        return bits
    if len(bits) >= width:
        return bits[-width:]
    pad_char = "0" if bits[0] in ("0", "1") else bits[0]
    return pad_char * (width - len(bits)) + bits


def _parse_vcd(path: Path) -> Dict[str, List[Tuple[int, str]]]:
    declarations: Dict[str, List[Tuple[str, int]]] = {}
    events: Dict[str, List[Tuple[int, str]]] = {}
    scope: List[str] = []
    timestamp = 0
    in_definitions = True

    for raw in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = raw.strip()
        if not line:
            continue
        if in_definitions:
            if line.startswith("$scope"):
                parts = line.split()
                if len(parts) >= 3:
                    scope.append(parts[2])
            elif line.startswith("$upscope"):
                if scope:
                    scope.pop()
            elif line.startswith("$var"):
                parts = line.split()
                if len(parts) >= 5:
                    try:
                        width = int(parts[2])
                    except ValueError:
                        width = 1
                    code = parts[3]
                    name = _SLICE_SUFFIX_RE.sub("", parts[4])
                    full_name = ".".join(tuple(scope) + (name,))
                    declarations.setdefault(code, []).append((full_name, width))
            elif line.startswith("$enddefinitions"):
                in_definitions = False
            continue

        if line.startswith("$"):
            continue
        if line.startswith("#"):
            try:
                timestamp = int(line[1:])
            except ValueError:
                continue
        elif line.startswith(("b", "B")):
            parts = line[1:].split()
            if len(parts) == 2:
                events.setdefault(parts[1], []).append((timestamp, parts[0].lower()))
        elif line[0] in "01xXzZ" and len(line) >= 2:
            events.setdefault(line[1:].strip(), []).append((timestamp, line[0].lower()))

    output: Dict[str, List[Tuple[int, str]]] = {}
    for code, targets in declarations.items():
        raw_events = events.get(code)
        if not raw_events:
            continue
        for full_name, width in targets:
            normalized_events = [
                (ts, _normalize_vcd_vector(val, width) if width > 1 else val)
                for ts, val in raw_events
            ]
            output[full_name] = _canonicalize_events(normalized_events)
    return output


def _canonicalize_events(events: List[Tuple[int, str]]) -> List[Tuple[int, str]]:
    """Collapse same-timestamp delta-cycle glitches and redundant no-op updates."""
    settled_by_ts: Dict[int, str] = {}
    for ts, val in events:
        settled_by_ts[ts] = val
    canonical: List[Tuple[int, str]] = []
    for ts in sorted(settled_by_ts):
        val = settled_by_ts[ts]
        if not canonical or canonical[-1][1] != val:
            canonical.append((ts, val))
    return canonical


def _select_signal_names(
    signals: Dict[str, List[Tuple[int, str]]], outputs: Sequence[str]
) -> Tuple[Optional[List[str]], Optional[str]]:
    if not signals:
        return None, "VCD contains no value-change events"
    if outputs:
        selected: List[str] = []
        for requested in outputs:
            matches = [name for name in signals if name == requested or name.endswith("." + requested)]
            if len(matches) == 0:
                return None, "observed signal is missing: %s" % requested
            if len(matches) > 1:
                return None, "observed signal is ambiguous: %s (matches: %s)" % (
                    requested,
                    ", ".join(sorted(matches)),
                )
            selected.append(matches[0])
        return selected, None
    return sorted(signals), None


def _has_known_value(events: Iterable[Tuple[int, str]]) -> bool:
    return any(char in "01" for _time, value in events for char in value)


def _first_mismatch_detail(
    name: str,
    gold_events: List[Tuple[int, str]],
    gate_events: List[Tuple[int, str]],
) -> str:
    """Find the earliest timestamp where golden and candidate waveforms diverge."""
    gold_map: Dict[int, str] = {}
    for ts, val in gold_events:
        gold_map[ts] = val
    gate_map: Dict[int, str] = {}
    for ts, val in gate_events:
        gate_map[ts] = val

    timestamps = sorted(set(gold_map) | set(gate_map))
    gold_val = "<unset>"
    gate_val = "<unset>"
    for ts in timestamps:
        if ts in gold_map:
            gold_val = gold_map[ts]
        if ts in gate_map:
            gate_val = gate_map[ts]
        if gold_val != gate_val:
            return "waveform mismatch on %s at t=%d: golden=%s vs candidate=%s" % (
                name,
                ts,
                gold_val,
                gate_val,
            )
    return "waveform mismatch on %s" % name


def _compare_vcd(golden: Path, candidate: Path, outputs: Sequence[str]) -> Tuple[str, str]:
    gold = _parse_vcd(golden)
    gate = _parse_vcd(candidate)
    gold_names, gold_error = _select_signal_names(gold, outputs)
    gate_names, gate_error = _select_signal_names(gate, outputs)
    if gold_error or gate_error:
        return "error", gold_error or gate_error or "no observed signals"
    names = tuple(gold_names or ())
    if tuple(gate_names or ()) != names:
        return "error", "golden and candidate observed signal sets differ"
    for name in names:
        if not _has_known_value(gold[name]) or not _has_known_value(gate[name]):
            return "error", "observed signal contains no known 0/1 value: %s" % name
        if gold[name] != gate[name]:
            return "failed", _first_mismatch_detail(name, gold[name], gate[name])
    return "success", "matched %d observed signal(s)" % len(names)


def _compact_tool_error(output: str, fallback: str, max_chars: int = 800) -> str:
    lines = [line.strip() for line in (output or "").splitlines() if line.strip()]
    if not lines:
        return fallback
    err_lines = [line for line in lines if "error" in line.lower() or "syntax" in line.lower()]
    if err_lines:
        return " | ".join(err_lines[:6])[:max_chars]
    return " ".join(lines)[-max_chars:]


def run_regression(
    golden: Path,
    candidate: Path,
    config: VerificationConfig,
    run_dir: Path,
) -> VerificationResult:
    if not config.observed_outputs:
        return VerificationResult.error(
            error_type="invalid_input",
            error_log="bounded simulation requires explicit observed_outputs",
            log_path=str(run_dir / "regression.log"),
            verification_method="iverilog-regression",
            proof_level=None,
            is_mock=config.is_mock,
        )
    if config.testbench is None or not config.testbench.is_file():
        return VerificationResult.error(
            error_type="missing_testbench",
            error_log="a testbench is required for simulation mode",
            log_path=str(run_dir / "regression.log"),
            verification_method="iverilog-regression",
            proof_level=None,
            is_mock=config.is_mock,
        )

    tb_path = run_dir / "generated_golden_tb.v"
    gate_tb = run_dir / "generated_candidate_tb.v"
    gold_vcd = run_dir / "golden.vcd"
    gate_vcd = run_dir / "candidate.vcd"
    tb_path.write_text(_render_testbench(config.testbench, gold_vcd, config.seed), encoding="utf-8")
    gate_tb.write_text(_render_testbench(config.testbench, gate_vcd, config.seed), encoding="utf-8")

    iverilog = resolve_command(config.iverilog_bin, "IVERILOG_BIN", "iverilog")
    vvp = resolve_command(config.vvp_bin, "VVP_BIN", "vvp")
    if isinstance(iverilog, str):
        iverilog = [iverilog]
    if isinstance(vvp, str):
        vvp = [vvp]

    compile_flags: List[str] = ["-g2012"]
    for include_dir in config.include_dirs:
        compile_flags.extend(["-I", str(include_dir)])
    for define in config.defines:
        compile_flags.append("-D" + str(define))

    gold_out = run_dir / "golden_compile.log"
    gate_out = run_dir / "candidate_compile.log"
    gold_vvp = run_dir / "golden.vvp"
    gate_vvp = run_dir / "candidate.vvp"

    gold_compile = run_command(
        list(iverilog)
        + compile_flags
        + ["-o", str(gold_vvp), str(tb_path), str(golden)]
        + [str(s) for s in config.extra_sources],
        timeout_seconds=config.timeout_seconds,
        log_path=gold_out,
        cwd=run_dir,
    )
    if gold_compile.timed_out:
        return VerificationResult.error(
            error_type="timeout",
            error_log=_compact_tool_error(gold_compile.output, "golden compile timeout"),
            log_path=str(gold_out),
            status="timeout",
            verification_method="iverilog-regression",
            proof_level=None,
            is_mock=config.is_mock,
        )
    if gold_compile.returncode != 0:
        return VerificationResult.error(
            error_type="tool_error",
            error_log=_compact_tool_error(gold_compile.output, "golden compile failed"),
            log_path=str(gold_out),
            verification_method="iverilog-regression",
            proof_level=None,
            is_mock=config.is_mock,
        )

    gate_compile = run_command(
        list(iverilog)
        + compile_flags
        + ["-o", str(gate_vvp), str(gate_tb), str(candidate)]
        + [str(s) for s in config.extra_sources],
        timeout_seconds=config.timeout_seconds,
        log_path=gate_out,
        cwd=run_dir,
    )
    if gate_compile.timed_out:
        return VerificationResult.error(
            error_type="timeout",
            error_log=_compact_tool_error(gate_compile.output, "candidate compile timeout"),
            log_path=str(gate_out),
            status="timeout",
            verification_method="iverilog-regression",
            proof_level=None,
            is_mock=config.is_mock,
        )
    if gate_compile.returncode != 0:
        err_type = "syntax_error" if "syntax error" in (gate_compile.output or "").lower() else "tool_error"
        return VerificationResult.error(
            error_type=err_type,
            error_log=_compact_tool_error(gate_compile.output, "candidate compile failed"),
            log_path=str(gate_out),
            verification_method="iverilog-regression",
            proof_level=None,
            is_mock=config.is_mock,
        )

    gold_run_log = run_dir / "golden_run.log"
    gate_run_log = run_dir / "candidate_run.log"

    gold_run = run_command(
        [*vvp, str(gold_vvp)],
        timeout_seconds=config.timeout_seconds,
        log_path=gold_run_log,
        cwd=run_dir,
    )
    if gold_run.timed_out:
        return VerificationResult.error(
            error_type="timeout",
            error_log="golden simulation timeout",
            log_path=str(gold_run_log),
            status="timeout",
            verification_method="iverilog-regression",
            proof_level=None,
            is_mock=config.is_mock,
        )
    if gold_run.returncode != 0:
        return VerificationResult.error(
            error_type="tool_error",
            error_log=_compact_tool_error(gold_run.output, "golden simulation failed"),
            log_path=str(gold_run_log),
            verification_method="iverilog-regression",
            proof_level=None,
            is_mock=config.is_mock,
        )

    gate_run = run_command(
        [*vvp, str(gate_vvp)],
        timeout_seconds=config.timeout_seconds,
        log_path=gate_run_log,
        cwd=run_dir,
    )
    if gate_run.timed_out:
        return VerificationResult.error(
            error_type="timeout",
            error_log="candidate simulation timeout",
            log_path=str(gate_run_log),
            status="timeout",
            verification_method="iverilog-regression",
            proof_level=None,
            is_mock=config.is_mock,
        )
    if gate_run.returncode != 0:
        return VerificationResult.error(
            error_type="tool_error",
            error_log=_compact_tool_error(gate_run.output, "candidate simulation failed"),
            log_path=str(gate_run_log),
            verification_method="iverilog-regression",
            proof_level=None,
            is_mock=config.is_mock,
        )

    if not gold_vcd.is_file() or not gate_vcd.is_file():
        return VerificationResult.error(
            error_type="missing_waveform",
            error_log="testbench did not produce both VCD files",
            log_path=str(gate_run_log),
            verification_method="iverilog-regression",
            proof_level=None,
            is_mock=config.is_mock,
        )

    comparison_status, detail = _compare_vcd(gold_vcd, gate_vcd, config.observed_outputs)
    if comparison_status == "success":
        return VerificationResult(
            status="success",
            equivalent=True,
            error_type=None,
            error_log=None,
            log_path=str(gate_run_log),
            verification_method="iverilog-regression",
            proof_level="bounded-simulation",
            is_mock=config.is_mock,
        )
    if comparison_status == "failed":
        return VerificationResult(
            status="failed",
            equivalent=False,
            error_type="not_equivalent",
            error_log=detail,
            log_path=str(gate_run_log),
            verification_method="iverilog-regression",
            proof_level=None,
            is_mock=config.is_mock,
        )
    return VerificationResult.error(
        error_type="missing_observation",
        error_log=detail,
        log_path=str(gate_run_log),
        verification_method="iverilog-regression",
        proof_level=None,
        is_mock=config.is_mock,
    )
