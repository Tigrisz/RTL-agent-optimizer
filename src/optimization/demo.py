"""D-only demo: real/mock generation, with explicitly simulated timing feedback.

This is not the project controller and does not verify or evaluate candidates.
"""

import argparse
import json
from pathlib import Path
from uuid import uuid4

from . import optimize


def run_demo(demo_root, output_dir, *, backend="mock", env_file=".env"):
    root = Path(demo_root)
    sources = {
        "popcount3": root / "case/bench/popcount3/popcount3_v1_behavioral.v",
        "addsubz": root / "case/bench/addsubz/addsubz_v1_behavioral.v",
    }
    if any(not p.is_file() for p in sources.values()):
        raise ValueError("Demo source files are missing; set --demo-root to opti_demo.")
    session = Path(output_dir).resolve() / uuid4().hex
    session.mkdir(parents=True, exist_ok=False)
    summary = {
        "session_path": str(session), "backend": backend, "source_kind": "opti_demo_not_course_cases",
        "verification": "not_run", "evaluation": "not_run", "feedback_kind": "simulated",
        "input_policy": "always_original_source_no_unverified_candidate_promotion",
        "calls": [],
    }

    def save():
        (session / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")

    for name, original in sources.items():
        source = session / (name + "_original.v")
        source.write_text(original.read_text(encoding="utf-8"), encoding="utf-8")
        context = {"design_id": "opti_demo/" + name, "top": "TopModule",
                   "circuit_type": "combinational", "parameters": {},
                   "constraints": {"preserve_interface": True, "preserve_cycles": True,
                                   "delay_limit": None, "delay_unit": None}}
        (session / (name + "_context.json")).write_text(json.dumps(context, indent=2), encoding="utf-8")
        first = optimize(source, output_dir=session / "candidates", backend=backend,
                         env_file=env_file, context=context, history_path=session / "history.jsonl")
        summary["calls"].append({"case": name, "round": 1, "result": first})
        save()
        if first["status"] != "success":
            summary["stopped_reason"] = "generation_failed_no_automatic_retry"
            save()
            return summary
        if name == "addsubz":
            feedback = {"is_mock": True, "candidate_id": first["run_id"],
                        "note": "模拟延时违规，只检查策略切换；不是该候选的真实测量或验证结论。",
                        "verify": None, "evaluate": {"status": "success", "timing_met": False},
                        "tried_strategies": [first["strategy"]]}
            (session / "simulated_timing_feedback.json").write_text(
                json.dumps(feedback, ensure_ascii=False, indent=2), encoding="utf-8")
            second = optimize(source, feedback, output_dir=session / "candidates", backend=backend,
                              env_file=env_file, context=context, history_path=session / "history.jsonl")
            summary["calls"].append({"case": name, "round": 2, "result": second})
            save()
    return summary


def main():
    parser = argparse.ArgumentParser(description="D-only generation demo (3 requests maximum, no verification/PPA)")
    parser.add_argument("--demo-root", default="tmp/opti_demo")
    parser.add_argument("--output-dir", default="runs/d_demo")
    parser.add_argument("--backend", choices=("mock", "custom"), default="mock")
    parser.add_argument("--env-file", default=".env")
    args = parser.parse_args()
    try:
        summary = run_demo(args.demo_root, args.output_dir, backend=args.backend, env_file=args.env_file)
    except (OSError, ValueError):
        print(json.dumps({"status": "error", "error_type": "demo_setup_error"}))
        return 1
    print(json.dumps(summary, ensure_ascii=True, indent=2))
    return 0 if len(summary["calls"]) == 3 and all(
        c["result"]["status"] == "success" for c in summary["calls"]) else 1


if __name__ == "__main__":
    raise SystemExit(main())
