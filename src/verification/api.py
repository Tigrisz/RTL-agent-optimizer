"""Public task-B verification API."""

from datetime import datetime, timezone
import json
from pathlib import Path
import re
import time
import uuid
from typing import Any, Dict, Mapping, Optional, Union

from .config import VerificationConfig, probe_tool_version, resolve_command
from .regression import run_regression
from .result import VerificationResult
from .yosys_engine import run_yosys_formal, summarize_yosys_error


_TOP_RE = re.compile(r"(?m)^\s*module\s+([A-Za-z_][A-Za-z0-9_$]*)\b")
_MODES = ("formal", "simulation", "both")


def _run_dir(config: VerificationConfig) -> Path:
    if config.run_dir is not None:
        result = Path(config.run_dir)
    else:
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        result = Path.cwd() / "runs" / "verification" / (stamp + "-" + uuid.uuid4().hex[:8])
    result.mkdir(parents=True, exist_ok=True)
    return result.resolve()


def _detect_top(path: Path) -> Optional[str]:
    text = path.read_text(encoding="utf-8", errors="replace")
    # Comments can contain examples such as ``module fake``.  Remove them
    # before looking for a declaration at the beginning of a line.
    text = re.sub(r"//[^\n]*|/\*.*?\*/", "", text, flags=re.DOTALL)
    match = _TOP_RE.search(text)
    return match.group(1) if match else None


def _write_json(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, default=str) + "\n", encoding="utf-8")


def _collect_tool_versions(config: VerificationConfig) -> Dict[str, Optional[str]]:
    if config.is_mock:
        return {}
    versions: Dict[str, Optional[str]] = {}
    if config.mode in ("formal", "both"):
        yosys_cmd = resolve_command(config.yosys_bin, "YOSYS_BIN", "yosys")
        versions["yosys"] = probe_tool_version(yosys_cmd)
    if config.mode in ("simulation", "both"):
        iverilog_cmd = resolve_command(config.iverilog_bin, "IVERILOG_BIN", "iverilog")
        versions["iverilog"] = probe_tool_version(iverilog_cmd)
    return versions


def _write_metadata(run_dir: Path, golden: Path, candidate: Path, config: VerificationConfig) -> None:
    _write_json(
        run_dir / "run_metadata.json",
        {
            "golden_rtl": str(golden),
            "candidate_rtl": str(candidate),
            "mode": config.mode,
            "top": config.top,
            "extra_sources": [str(path) for path in config.extra_sources],
            "include_dirs": [str(path) for path in config.include_dirs],
            "defines": list(config.defines),
            "timeout_seconds": config.timeout_seconds,
            "sequential": config.sequential,
            "clock": config.clock,
            "reset": config.reset,
            "reset_active_low": config.reset_active_low,
            "induction_steps": config.induction_steps,
            "seed": config.seed,
            "is_mock": config.is_mock,
            "tool_versions": _collect_tool_versions(config),
            "testbench": str(config.testbench) if config.testbench else None,
            "observed_outputs": list(config.observed_outputs),
        },
    )


def _finish(run_dir: Path, result: VerificationResult, started: float) -> Dict[str, Any]:
    result.elapsed_seconds = round(time.monotonic() - started, 4)
    result.write_json(run_dir / "verify_result.json")
    return result.to_dict()


def _input_error(
    run_dir: Path,
    golden: Path,
    candidate: Path,
    config: VerificationConfig,
    error_type: str,
    detail: str,
    started: float,
) -> Dict[str, Any]:
    _write_metadata(run_dir, golden, candidate, config)
    log_path = run_dir / "verify.log"
    log_path.write_text(detail + "\n", encoding="utf-8")
    return _finish(
        run_dir,
        VerificationResult.error(
            error_type=error_type,
            error_log=detail,
            log_path=str(log_path),
            is_mock=config.is_mock,
        ),
        started,
    )


def verify(
    golden_rtl: Union[str, Path],
    candidate_rtl: Union[str, Path],
    config: Optional[Union[VerificationConfig, Mapping[str, Any]]] = None,
) -> Dict[str, Any]:
    """Verify one candidate against the immutable original RTL.

    The function is intentionally synchronous so A can use it as one atomic
    step in its iteration state machine.  It returns only JSON-compatible
    values and writes the complete run artifacts before returning.  ``config``
    may be omitted, a :class:`VerificationConfig`, or a plain ``dict``.
    """
    started = time.monotonic()
    golden = Path(golden_rtl).expanduser().resolve()
    candidate = Path(candidate_rtl).expanduser().resolve()

    if config is None:
        resolved_config = VerificationConfig()
    elif isinstance(config, VerificationConfig):
        resolved_config = config
    elif isinstance(config, Mapping):
        try:
            resolved_config = VerificationConfig.from_mapping(config)
        except (TypeError, ValueError) as exc:
            fallback = VerificationConfig()
            run_dir = _run_dir(fallback)
            return _input_error(run_dir, golden, candidate, fallback, "invalid_input", "invalid config mapping: %s" % exc, started)
    else:
        fallback = VerificationConfig()
        run_dir = _run_dir(fallback)
        return _input_error(
            run_dir,
            golden,
            candidate,
            fallback,
            "invalid_input",
            "config must be VerificationConfig, dict, or None",
            started,
        )

    config = resolved_config
    run_dir = _run_dir(config)

    if config.mode not in _MODES:
        return _input_error(run_dir, golden, candidate, config, "invalid_input", "unsupported verification mode: %s" % config.mode, started)
    if config.timeout_seconds <= 0:
        return _input_error(run_dir, golden, candidate, config, "invalid_input", "timeout_seconds must be positive", started)
    if not golden.is_file():
        return _input_error(run_dir, golden, candidate, config, "missing_file", "golden RTL does not exist: %s" % golden, started)
    if not candidate.is_file():
        return _input_error(run_dir, golden, candidate, config, "missing_file", "candidate RTL does not exist: %s" % candidate, started)
    missing_sources = [path for path in config.extra_sources if not path.expanduser().is_file()]
    if missing_sources:
        return _input_error(run_dir, golden, candidate, config, "missing_file", "missing extra source: %s" % missing_sources[0], started)
    if config.mode in ("simulation", "both") and config.testbench is None:
        return _input_error(run_dir, golden, candidate, config, "missing_testbench", "simulation mode requires a testbench", started)
    if config.mode in ("simulation", "both") and config.testbench is not None and not config.testbench.is_file():
        return _input_error(run_dir, golden, candidate, config, "missing_testbench", "testbench does not exist: %s" % config.testbench, started)
    if config.mode in ("simulation", "both") and not config.observed_outputs:
        return _input_error(
            run_dir,
            golden,
            candidate,
            config,
            "invalid_input",
            "simulation mode requires explicit observed_outputs",
            started,
        )

    if not config.top:
        config.top = _detect_top(golden)
    if not config.top:
        return _input_error(run_dir, golden, candidate, config, "invalid_input", "unable to detect top module from golden RTL", started)
    if config.sequential and not config.clock:
        return _input_error(run_dir, golden, candidate, config, "invalid_input", "sequential verification requires an explicit clock", started)

    _write_metadata(run_dir, golden, candidate, config)

    if config.mode == "simulation":
        return _finish(run_dir, run_regression(golden, candidate, config, run_dir), started)

    try:
        classification, process_result, _script = run_yosys_formal(golden, candidate, config, run_dir)
    except (OSError, ValueError, RuntimeError) as exc:
        return _finish(
            run_dir,
            VerificationResult.error(
                error_type="tool_error",
                error_log=str(exc),
                log_path=str(run_dir / "yosys.log"),
                verification_method="yosys-formal",
                proof_level=None,
                is_mock=config.is_mock,
            ),
            started,
        )

    status, equivalent, error_type = classification
    formal_proof_level = ("bounded-formal" if config.sequential else "formal") if status == "success" else None
    formal_result = VerificationResult(
        status=status,
        equivalent=equivalent,
        error_type=error_type,
        error_log=summarize_yosys_error(process_result.output, error_type) if status != "success" else None,
        log_path=str(run_dir / "yosys.log"),
        verification_method="yosys-formal",
        proof_level=formal_proof_level,
        is_mock=config.is_mock,
    )
    if config.mode == "formal":
        return _finish(run_dir, formal_result, started)
    if formal_result.status != "success":
        # When formal proof is merely inconclusive (unproven) in `both` mode,
        # still run bounded simulation so multi-cycle bugs beyond induction_steps
        # are surfaced as concrete `not_equivalent` feedback rather than `unproven`.
        if formal_result.status == "error" and formal_result.error_type == "unproven":
            regression_result = run_regression(golden, candidate, config, run_dir)
            regression_result.write_json(run_dir / "regression_result.json")
            if regression_result.status == "failed":
                return _finish(run_dir, regression_result, started)
            if regression_result.status == "success":
                formal_result.error_log = (
                    (formal_result.error_log or "formal proof unproven")
                    + " (bounded simulation passed, but formal proof remains unproven)"
                )
        return _finish(run_dir, formal_result, started)

    regression_result = run_regression(golden, candidate, config, run_dir)
    regression_result.write_json(run_dir / "regression_result.json")
    if regression_result.status != "success":
        return _finish(run_dir, regression_result, started)

    combined_proof = (
        "bounded-formal+bounded-simulation" if config.sequential else "formal+bounded-simulation"
    )
    combined = VerificationResult(
        status="success",
        equivalent=True,
        error_type=None,
        error_log=None,
        log_path=str(run_dir / "yosys.log"),
        verification_method="yosys-formal+iverilog-regression",
        proof_level=combined_proof,
        is_mock=config.is_mock,
    )
    return _finish(run_dir, combined, started)
