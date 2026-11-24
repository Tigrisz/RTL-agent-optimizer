"""Command-line entry point for standalone verification runs."""

import argparse
import json
import sys
from typing import Optional, Sequence

from .api import verify
from .config import VerificationConfig


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m src.verification",
        description="Verify candidate RTL equivalence against golden RTL.",
    )
    parser.add_argument("golden_rtl", help="Path to immutable golden RTL file.")
    parser.add_argument("candidate_rtl", help="Path to candidate RTL file.")
    parser.add_argument("--top", default=None, help="Top module name.")
    parser.add_argument(
        "--mode",
        choices=("formal", "simulation", "both"),
        default="formal",
        help="Verification mode (default: formal).",
    )
    parser.add_argument("--extra-source", action="append", default=[], help="Extra RTL source file.")
    parser.add_argument("--include-dir", action="append", default=[], help="Include directory.")
    parser.add_argument("--define", action="append", default=[], help="Preprocessor define.")
    parser.add_argument("--timeout", type=float, default=120.0, help="Timeout in seconds.")
    parser.add_argument("--run-dir", default=None, help="Output directory for logs and JSON artifacts.")
    parser.add_argument("--testbench", default=None, help="Testbench path for simulation/both modes.")
    parser.add_argument(
        "--observe",
        action="append",
        default=[],
        help="Observed output signal name (repeatable) for simulation/both modes.",
    )
    parser.add_argument("--sequential", action="store_true", help="Enable sequential verification flow.")
    parser.add_argument("--clock", default=None, help="Clock signal name (required with --sequential).")
    parser.add_argument("--reset", default=None, help="Reset signal name.")
    parser.add_argument("--reset-active-low", action="store_true", help="Treat reset as active-low.")
    parser.add_argument("--induction-steps", type=int, default=4, help="Sequential induction/BMC steps.")
    parser.add_argument("--seed", type=int, default=42, help="Simulation stimulus seed.")
    args = parser.parse_args(argv)

    config = VerificationConfig(
        top=args.top,
        extra_sources=tuple(args.extra_source),
        include_dirs=tuple(args.include_dir),
        defines=tuple(args.define),
        timeout_seconds=args.timeout,
        run_dir=args.run_dir,
        mode=args.mode,
        testbench=args.testbench,
        observed_outputs=tuple(args.observe),
        sequential=args.sequential,
        clock=args.clock,
        reset=args.reset,
        reset_active_low=args.reset_active_low,
        induction_steps=args.induction_steps,
        seed=args.seed,
    )
    result = verify(args.golden_rtl, args.candidate_rtl, config=config)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["status"] == "success" else 1


if __name__ == "__main__":
    sys.exit(main())
