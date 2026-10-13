"""Optional Icarus/VVP regression backend for bounded functional checks."""

from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

from .config import VerificationConfig, resolve_command
from .process import CommandResult, run_command
from .result import VerificationResult


def _render_testbench(source: Path, vcd_path: Path) -> str:
    text = source.read_text(encoding="utf-8")
    vcd = str(vcd_path).replace("\\", "/").replace('"', '\\"')
    return text.replace("__VCD__", vcd).replace("`VCD_PATH", '"%s"' % vcd)


def _parse_vcd(path: Path) -> Dict[str, List[Tuple[int, str]]]:
    declarations: Dict[str, Tuple[str, Tuple[str, ...]]] = {}
    events: Dict[str, List[Tuple[int, str]]] = {}
    scope: List[str] = []
    timestamp = 0
    for raw in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = raw.strip()
        if not line:
            continue
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
                declarations[parts[3]] = (parts[4], tuple(scope))
        elif line.startswith("#"):
            try:
                timestamp = int(line[1:])
            except ValueError:
                continue
        elif line.startswith("b") or line.startswith("B"):
            parts = line[1:].split()
            if len(parts) == 2:
                events.setdefault(parts[1], []).append((timestamp, parts[0].lower().lstrip("0") or "0"))
        elif line[0] in "01xXzZ":
            events.setdefault(line[1:].strip(), []).append((timestamp, line[0].lower()))
    output: Dict[str, List[Tuple[int, str]]] = {}
    for code, (name, signal_scope) in declarations.items():
        if code in events:
            full_name = ".".join(signal_scope + (name,))
            output[full_name] = events[code]
    return output


def _select_signal_names(signals: Dict[str, List[Tuple[int, str]]], outputs: Sequence[str]) -> Tuple[Optional[List[str]], Optional[str]]:
    if not signals:
        return None, "VCD contains no value-change events"
    if outputs:
        selected: List[str] = []
        for requested in outputs:
            matches = [name for name in signals if name == requested or name.endswith("." + requested)]
            if len(matches) != 1:
                return None, "observed signal is missing or ambiguous: %s" % requested
            selected.append(matches[0])
        return selected, None
    return sorted(signals), None


def _has_known_value(events: Iterable[Tuple[int, str]]) -> bool:
    return any(char in "01" for _time, value in events for char in value)


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
        if gold[name] != gate[name]:
            return "failed", "waveform mismatch on %s" % name
        if not _has_known_value(gold[name]) or not _has_known_value(gate[name]):
            return "error", "observed signal contains no known 0/1 value: %s" % name
    return "success", "matched %d observed signal(s)" % len(names)


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
            proof_level="bounded-simulation",
        )
    if config.testbench is None or not config.testbench.is_file():
        return VerificationResult.error(
            error_type="missing_testbench",
            error_log="a testbench is required for simulation mode",
            log_path=str(run_dir / "regression.log"),
            verification_method="iverilog-regression",
            proof_level="bounded-simulation",
        )

    tb_path = run_dir / "generated_tb.v"
    gold_vcd = run_dir / "golden.vcd"
    gate_vcd = run_dir / "candidate.vcd"
    tb_path.write_text(_render_testbench(config.testbench, gold_vcd), encoding="utf-8")
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
        list(iverilog) + compile_flags + ["-o", str(gold_vvp), str(tb_path), str(golden)] + [str(s) for s in config.extra_sources],
        timeout_seconds=config.timeout_seconds,
        log_path=gold_out,
        cwd=run_dir,
    )
    if gold_compile.timed_out:
        return VerificationResult.error(error_type="timeout", error_log=gold_compile.output[-1000:], log_path=str(gold_out), status="timeout", verification_method="iverilog-regression", proof_level="bounded-simulation")
    if gold_compile.returncode != 0:
        return VerificationResult.error(error_type="tool_error", error_log=gold_compile.output[-1000:], log_path=str(gold_out), verification_method="iverilog-regression", proof_level="bounded-simulation")
    gate_tb = run_dir / "generated_candidate_tb.v"
    gate_tb.write_text(_render_testbench(config.testbench, gate_vcd), encoding="utf-8")
    gate_compile = run_command(
        list(iverilog) + compile_flags + ["-o", str(gate_vvp), str(gate_tb), str(candidate)] + [str(s) for s in config.extra_sources],
        timeout_seconds=config.timeout_seconds,
        log_path=gate_out,
        cwd=run_dir,
    )
    if gate_compile.timed_out:
        return VerificationResult.error(error_type="timeout", error_log=gate_compile.output[-1000:], log_path=str(gate_out), status="timeout", verification_method="iverilog-regression", proof_level="bounded-simulation")
    if gate_compile.returncode != 0:
        return VerificationResult.error(error_type="tool_error", error_log=gate_compile.output[-1000:], log_path=str(gate_out), verification_method="iverilog-regression", proof_level="bounded-simulation")

    gold_run = run_command([*vvp, str(gold_vvp)], timeout_seconds=config.timeout_seconds, log_path=run_dir / "golden_run.log", cwd=run_dir)
    gate_run = run_command([*vvp, str(gate_vvp)], timeout_seconds=config.timeout_seconds, log_path=run_dir / "candidate_run.log", cwd=run_dir)
    if gold_run.timed_out or gate_run.timed_out:
        return VerificationResult.error(error_type="timeout", error_log="simulation timeout", log_path=str(run_dir / "candidate_run.log"), status="timeout", verification_method="iverilog-regression", proof_level="bounded-simulation")
    if gold_run.returncode != 0 or gate_run.returncode != 0:
        return VerificationResult.error(error_type="tool_error", error_log=(gold_run.output + gate_run.output)[-1000:], log_path=str(run_dir / "candidate_run.log"), verification_method="iverilog-regression", proof_level="bounded-simulation")
    if not gold_vcd.is_file() or not gate_vcd.is_file():
        return VerificationResult.error(error_type="missing_waveform", error_log="testbench did not produce both VCD files", log_path=str(run_dir / "candidate_run.log"), verification_method="iverilog-regression", proof_level="bounded-simulation")
    comparison_status, detail = _compare_vcd(gold_vcd, gate_vcd, config.observed_outputs)
    if comparison_status == "success":
        return VerificationResult("success", True, None, None, str(run_dir / "candidate_run.log"), "iverilog-regression", "bounded-simulation")
    if comparison_status == "failed":
        return VerificationResult("failed", False, "not_equivalent", detail, str(run_dir / "candidate_run.log"), "iverilog-regression", "bounded-simulation")
    return VerificationResult.error(error_type="missing_observation", error_log=detail, log_path=str(run_dir / "candidate_run.log"), verification_method="iverilog-regression", proof_level="bounded-simulation")
