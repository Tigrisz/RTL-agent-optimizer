"""Public task-B verification API."""

from datetime import datetime, timezone
import json
from pathlib import Path
import re
import uuid
from typing import Any, Dict, Optional, Tuple

from .config import VerificationConfig
from .regression import run_regression
from .result import VerificationResult
from .yosys_engine import run_yosys_formal


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


def _short_error(text: str) -> str:
    compact = " ".join((text or "").split())
    return compact[-1000:] if compact else "verification failed without a diagnostic"


def _write_json(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, default=str) + "\n", encoding="utf-8")


def _finish(run_dir: Path, result: VerificationResult) -> Dict[str, Any]:
    result.write_json(run_dir / "verify_result.json")
    return result.to_dict()


def _input_error(run_dir: Path, error_type: str, detail: str) -> Dict[str, Any]:
    log_path = run_dir / "verify.log"
    log_path.write_text(detail + "\n", encoding="utf-8")
    return _finish(
        run_dir,
        VerificationResult.error(
            error_type=error_type,
            error_log=detail,
            log_path=str(log_path),
        ),
    )


def verify(
    golden_rtl: Path,
    candidate_rtl: Path,
    config: Optional[VerificationConfig] = None,
) -> Dict[str, Any]:
    """Verify one candidate against the immutable original RTL.

    The function is intentionally synchronous so A can use it as one atomic
    step in its iteration state machine.  It returns only JSON-compatible
    values and writes the complete run artifacts before returning.
    """
    config = config or VerificationConfig()
    run_dir = _run_dir(config)
    golden = Path(golden_rtl).expanduser().resolve()
    candidate = Path(candidate_rtl).expanduser().resolve()

    if config.mode not in _MODES:
        return _input_error(run_dir, "invalid_input", "unsupported verification mode: %s" % config.mode)
    if config.timeout_seconds <= 0:
        return _input_error(run_dir, "invalid_input", "timeout_seconds must be positive")
    if not golden.is_file():
        return _input_error(run_dir, "missing_file", "golden RTL does not exist: %s" % golden)
    if not candidate.is_file():
        return _input_error(run_dir, "missing_file", "candidate RTL does not exist: %s" % candidate)
    missing_sources = [path for path in config.extra_sources if not path.expanduser().is_file()]
    if missing_sources:
        return _input_error(run_dir, "missing_file", "missing extra source: %s" % missing_sources[0])
    if config.mode in ("simulation", "both") and config.testbench is None:
        return _input_error(run_dir, "missing_testbench", "simulation mode requires a testbench")
    if config.mode in ("simulation", "both") and config.testbench is not None and not config.testbench.is_file():
        return _input_error(run_dir, "missing_testbench", "testbench does not exist: %s" % config.testbench)
    if config.mode in ("simulation", "both") and not config.observed_outputs:
        return _input_error(
            run_dir,
            "invalid_input",
            "simulation mode requires explicit observed_outputs",
        )

    if not config.top:
        config.top = _detect_top(golden)
    if not config.top:
        return _input_error(run_dir, "invalid_input", "unable to detect top module from golden RTL")
    if config.sequential and not config.clock:
        return _input_error(run_dir, "invalid_input", "sequential verification requires an explicit clock")

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
            "testbench": str(config.testbench) if config.testbench else None,
            "observed_outputs": list(config.observed_outputs),
        },
    )

    if config.mode == "simulation":
        return _finish(run_dir, run_regression(golden, candidate, config, run_dir))

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
                proof_level="formal",
            ),
        )

    status, equivalent, error_type = classification
    formal_result = VerificationResult(
        status=status,
        equivalent=equivalent,
        error_type=error_type,
        error_log=_short_error(process_result.output) if status != "success" else None,
        log_path=str(run_dir / "yosys.log"),
        verification_method="yosys-formal",
        proof_level=("bounded-formal" if config.sequential else "formal") if status == "success" else None,
    )
    if config.mode == "formal":
        return _finish(run_dir, formal_result)
    if formal_result.status != "success":
        return _finish(run_dir, formal_result)

    regression_result = run_regression(golden, candidate, config, run_dir)
    regression_result.write_json(run_dir / "regression_result.json")
    if regression_result.status != "success":
        return _finish(run_dir, regression_result)
    combined = VerificationResult(
        status="success",
        equivalent=True,
        error_type=None,
        error_log=None,
        log_path=str(run_dir / "yosys.log"),
        verification_method="yosys-formal+iverilog-regression",
        proof_level="formal+bounded-simulation",
    )
    return _finish(run_dir, combined)
