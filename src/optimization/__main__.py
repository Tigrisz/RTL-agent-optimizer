import argparse
import json
from pathlib import Path

from . import optimize


def main():
    parser = argparse.ArgumentParser(description="Generate one unverified RTL candidate")
    parser.add_argument("current_rtl")
    parser.add_argument("--feedback", help="JSON feedback file")
    parser.add_argument("--output-dir", default="runs/optimization")
    parser.add_argument("--env-file", default=".env")
    parser.add_argument("--backend", choices=("custom", "mock"))
    parser.add_argument("--context", help="JSON design context: design_id, top, parameters, constraints")
    parser.add_argument("--history", help="Append-only JSONL history for one serial development session")
    args = parser.parse_args()
    try:
        feedback = json.loads(Path(args.feedback).read_text(encoding="utf-8-sig")) if args.feedback else None
        context = json.loads(Path(args.context).read_text(encoding="utf-8-sig")) if args.context else None
    except (OSError, ValueError):
        result = dict(status="error", candidate_path=None, strategy=None,
                      error_type="input_error", error_log="Cannot read feedback JSON.",
                      is_mock=args.backend == "mock")
    else:
        result = optimize(args.current_rtl, feedback, output_dir=args.output_dir,
                          env_file=args.env_file, backend=args.backend,
                          context=context, history_path=args.history)
    print(json.dumps(result, ensure_ascii=True, indent=2))
    return 0 if result["status"] == "success" else 1


if __name__ == "__main__":
    raise SystemExit(main())
