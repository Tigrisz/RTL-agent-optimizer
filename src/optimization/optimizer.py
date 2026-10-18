"""Single-candidate generation; no verification or PPA evaluation."""

import json
import hashlib
import math
import os
import time
from datetime import datetime, timezone
from pathlib import Path
import re
import socket
from urllib import error, parse, request
from uuid import uuid4


STRATEGIES = {
    "area_simplify": "保守简化组合表达式、常量与冗余逻辑，保持位宽及符号语义。",
    "resource_share": "仅在运算互斥且位宽、符号兼容时尝试共享；新增选择器可能恶化关键路径，不增加周期。",
    "timing_restructure": "检查关键路径和运算树结构，在不改变周期行为的前提下改善时序。",
    "repair_equivalence": "优先根据不等价反馈修复位宽、符号、边界和时序语义，暂缓激进优化。",
    "arithmetic_restructure": "检查算术表达式与运算树；仅使用保持溢出、截断、符号和周期语义的变换，收益必须实测。",
    "control_simplify": "检查重复条件、选择器与公共子表达式；保持分支优先级、默认行为且不引入锁存器。",
}


def select_strategy(feedback):
    verify = feedback.get("verify") or {}
    evaluate = feedback.get("evaluate") or {}
    if verify.get("status") == "failed" and verify.get("equivalent") is False:
        return "repair_equivalence"
    if evaluate.get("status") == "success" and evaluate.get("timing_met") is False:
        return "timing_restructure"
    tried = feedback.get("tried_strategies") or []
    return next((s for s in ("area_simplify", "resource_share", "arithmetic_restructure", "control_simplify") if s not in tried),
                "area_simplify")


def load_config(env_file):
    config = {}
    if env_file is not None and Path(env_file).is_file():
        for line in Path(env_file).read_text(encoding="utf-8-sig").splitlines():
            if line.strip() and not line.lstrip().startswith("#") and "=" in line:
                key, value = line.split("=", 1)
                config[key.strip()] = value.strip().strip("\"'")
    for key in ("LLM_BACKEND", "LLM_BASE_URL", "LLM_API_KEY", "LLM_MODEL",
                "LLM_TIMEOUT_SECONDS", "LLM_MAX_TOKENS", "LLM_THINKING"):
        if key in os.environ:
            config[key] = os.environ[key]
    return config


def compact_data(value, depth=0):
    """Bound feedback/history only; never truncate RTL source silently."""
    if depth > 5:
        return "[nested data omitted]"
    if isinstance(value, str):
        return value if len(value) <= 1500 else value[:1500] + "...[truncated]"
    if isinstance(value, list):
        return [compact_data(v, depth + 1) for v in value[-6:]]
    if isinstance(value, dict):
        return {k: compact_data(v, depth + 1) for k, v in list(value.items())[:20]
                if not re.search(r"key|token|secret|password|authorization", k, re.I)}
    return value


def build_prompt(rtl, feedback, strategy, context=None, history=None):
    template = Path(__file__).with_name("prompts").joinpath("rtl_optimize.md").read_text(encoding="utf-8")
    values = {"RTL_SOURCE": rtl, "FEEDBACK": json.dumps(compact_data(feedback), ensure_ascii=False),
              "CONTEXT": json.dumps(context or {}, ensure_ascii=False),
              "HISTORY": json.dumps(compact_data(history or []), ensure_ascii=False),
              "STRATEGY": strategy + ": " + STRATEGIES[strategy]}
    return re.sub(r"\{\{(RTL_SOURCE|FEEDBACK|STRATEGY|CONTEXT|HISTORY)\}\}",
                  lambda match: values[match[1]], template)


class NoRedirect(request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None  # Do not forward credentials to redirected endpoints.


def call_model(prompt, config, timeout, *, return_metadata=False):
    payload = {"model": config["LLM_MODEL"],
                          "messages": [{"role": "user", "content": prompt}],
                          "max_tokens": int(config.get("LLM_MAX_TOKENS", "2048")),
                          "stream": False}
    if config.get("LLM_THINKING"):
        payload["thinking"] = {"type": config["LLM_THINKING"]}
    payload = json.dumps(payload).encode("utf-8")
    req = request.Request(config["LLM_BASE_URL"].rstrip("/") + "/chat/completions",
                          data=payload, headers={"Content-Type": "application/json",
                          "Authorization": "Bearer " + config["LLM_API_KEY"]})
    with request.build_opener(NoRedirect).open(req, timeout=timeout) as response:
        body = json.load(response)
    content = body["choices"][0]["message"]["content"]
    if content is None:
        content = ""
    if not isinstance(content, str):
        raise ValueError("Unexpected response structure")
    if return_metadata:
        usage = body.get("usage") or {}
        if not isinstance(usage, dict):
            raise ValueError("Unexpected usage structure")
        usage = {k: v for k, v in usage.items() if k in (
            "prompt_tokens", "completion_tokens", "total_tokens",
            "prompt_cache_hit_tokens", "prompt_cache_miss_tokens") and isinstance(v, int)}
        return {"content": content, "usage": usage, "model": body.get("model"),
                "finish_reason": body["choices"][0].get("finish_reason")}
    return content


def extract_rtl(output):
    blocks = re.findall(r"^\s*```(verilog|systemverilog)\s*\n(.*?)^\s*```\s*$",
                        output, re.MULTILINE | re.DOTALL | re.IGNORECASE)
    if len(blocks) != 1:
        return None
    rtl = blocks[0][1].strip()
    # Only a structural extraction guard, deliberately not a Verilog validator.
    clean = re.sub(r'//[^\n]*|/\*.*?\*/|"(?:\\.|[^"\\])*"', "", rtl, flags=re.DOTALL)
    tokens = re.findall(r"\b(module|endmodule)\b", clean)
    if not tokens or len(tokens) % 2 or tokens != ["module", "endmodule"] * (len(tokens) // 2):
        return None
    return rtl + "\n", ".sv" if blocks[0][0].lower() == "systemverilog" else ".v"


def source_hash(source):
    # Text identity only: preserves comments and internal whitespace, not semantic equivalence.
    normalized = "\n".join(line.rstrip() for line in source.splitlines()).strip()
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def rtl_fingerprint(source):
    """Token identity ignoring comments/formatting, not semantic equivalence."""
    pattern = r'//[^\n]*|/\*[\s\S]*?\*/|"(?:\\.|[^"\\])*"|\\[^\s]+|[A-Za-z_$][A-Za-z0-9_$]*|\d+\x27[sS]?[bBoOdDhH][0-9a-fA-FxXzZ?_]+|\x27[01xXzZ]|\d+(?:\.\d+)?|===|!==|>>>|<<<|==|!=|<=|>=|<<|>>|&&|\|\||\*\*|~\^|\^~|~&|~\||\+:|-:|[^\s]'
    tokens = [m.group() for m in re.finditer(pattern, source)
              if not m.group().startswith(("//", "/*"))]
    return hashlib.sha256(json.dumps(tokens).encode("utf-8")).hexdigest()


def optimize(current_rtl, feedback=None, *, output_dir="runs/optimization", env_file=".env",
             backend=None, context=None, history_path=None):
    """Return the agreed JSON-compatible result; keyword options are for standalone use."""
    started = time.monotonic()
    run_dir = None
    history_file = None
    input_info = {}
    result = dict(status="error", candidate_path=None, strategy=None,
                  error_type=None, error_log=None, is_mock=False,
                  feedback_is_mock=False, is_duplicate=False, duplicate_of=None,
                  candidate_hash=None, candidate_fingerprint=None, usage={}, elapsed_seconds=0,
                  run_id=uuid4().hex, record_path=None, prompt_path=None, model=None)

    def finish():
        result["elapsed_seconds"] = round(time.monotonic() - started, 3)
        if run_dir is not None:
            try:
                result["record_path"] = str(run_dir / "record.json")
                record = {**input_info, **result, "created_at": datetime.now(timezone.utc).isoformat(),
                          "verification": "not_run", "evaluation": "not_run"}
                (run_dir / "record.json").write_text(
                    json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")
                if history_file is not None:
                    history_file.parent.mkdir(parents=True, exist_ok=True)
                    with history_file.open("a", encoding="utf-8") as stream:
                        stream.write(json.dumps(record, ensure_ascii=False) + "\n")
            except OSError:
                result.update(status="error", error_type="save_error",
                              error_log="Cannot persist generation record/history.")
        return result

    def fail(kind, message, status="error"):
        result.update(status=status, error_type=kind, error_log=message)
        return finish()

    try:
        config = load_config(env_file)
    except (OSError, UnicodeError):
        return fail("config_error", "Cannot read local model configuration.")
    mode = backend or config.get("LLM_BACKEND", "custom")
    result["is_mock"] = mode == "mock"
    result["model"] = "mock" if mode == "mock" else config.get("LLM_MODEL")
    try:
        feedback = {} if feedback is None else feedback
        if not isinstance(feedback, dict):
            raise ValueError()
        for field in ("verify", "evaluate"):
            if feedback.get(field) is not None and not isinstance(feedback[field], dict):
                raise ValueError()
        if not isinstance(feedback.get("tried_strategies", []), list):
            raise ValueError()
        if any(not isinstance(s, str) for s in feedback.get("tried_strategies", [])):
            raise ValueError()
        context = {} if context is None else context
        if not isinstance(context, dict) or len(json.dumps(context, allow_nan=False)) > 8000:
            raise ValueError()
        # Strictly bound supplied feedback, then compact log/history portions in prompts.
        if len(json.dumps(feedback, allow_nan=False)) > 64000:
            raise ValueError()
        result["feedback_is_mock"] = feedback.get("is_mock") is True
        rtl = Path(current_rtl).read_text(encoding="utf-8-sig")
        if not rtl.strip() or len(rtl) > 64000:
            raise ValueError()
        scope = str(context.get("design_id") or Path(current_rtl).resolve())
        context_hash = hashlib.sha256(json.dumps(context, sort_keys=True).encode()).hexdigest()
        history = []
        if history_path is not None:
            history_file = Path(history_path).resolve()
            if history_file.is_file():
                with history_file.open(encoding="utf-8") as stream:
                    for line in stream:
                        item = json.loads(line)
                        if not isinstance(item, dict):
                            raise ValueError()
                        if item.get("status") == "success" and (
                                item.get("strategy") not in STRATEGIES or
                                not isinstance(item.get("run_id"), str)):
                            raise ValueError()
                        if (item.get("scope") == scope and item.get("context_hash") == context_hash
                                and item.get("is_mock") == result["is_mock"]):
                            history.append(item)
        tried = list(dict.fromkeys(feedback.get("tried_strategies", []) +
                                  [h["strategy"] for h in history if h.get("status") == "success"]))
        combined_feedback = {**feedback, "tried_strategies": tried}
        result["strategy"] = select_strategy(combined_feedback)
        recent = [{k: h.get(k) for k in ("run_id", "strategy", "status", "candidate_hash", "is_duplicate", "feedback_is_mock")}
                  for h in history[-6:]]
        prompt = build_prompt(rtl, combined_feedback, result["strategy"], context, recent)
        input_info = {"scope": scope, "context_hash": context_hash, "source_path": str(Path(current_rtl).resolve()),
                      "source_hash": source_hash(rtl), "context": context,
                      "feedback": compact_data(combined_feedback)}
    except (OSError, UnicodeError, ValueError, TypeError):
        return fail("input_error", "Check RTL (1..64000 characters), context/feedback JSON and history file.")
    try:
        run_dir = Path(output_dir).resolve() / result["run_id"]
        run_dir.mkdir(parents=True, exist_ok=False)
        result["prompt_path"] = str(run_dir / "prompt.md")
        (run_dir / "prompt.md").write_text(prompt, encoding="utf-8")
    except OSError:
        run_dir = None
        return fail("save_error", "Cannot create generation output directory.")
    if mode == "mock":
        language = "systemverilog" if Path(current_rtl).suffix.lower() == ".sv" else "verilog"
        output = f"```{language}\n{rtl}\n```"
    elif mode == "custom":
        try:
            if not all(config.get(k, "").strip() for k in ("LLM_BASE_URL", "LLM_MODEL", "LLM_API_KEY")):
                raise ValueError()
            url = parse.urlsplit(config["LLM_BASE_URL"])
            if url.scheme != "https" or not url.hostname or url.username or url.password or url.query or url.fragment:
                raise ValueError()
            timeout = float(config.get("LLM_TIMEOUT_SECONDS", "60"))
            if not math.isfinite(timeout) or timeout <= 0:
                raise ValueError()
            max_tokens = int(config.get("LLM_MAX_TOKENS", "2048"))
            if not 64 <= max_tokens <= 8192 or config.get("LLM_THINKING", "disabled") not in ("enabled", "disabled"):
                raise ValueError()
        except ValueError:
            return fail("config_error", "Set an HTTPS API base URL, model, API key and positive finite timeout.")
        try:
            response = call_model(prompt, config, timeout, return_metadata=True)
            if isinstance(response, dict):
                output = response["content"]
                result["usage"] = response["usage"]
                result["model_returned"] = response.get("model")
                if response.get("finish_reason") == "length":
                    return fail("output_truncated", "Token limit reached; candidate was not accepted.", "failed")
            else:
                output = response  # Supports a string-returning injected test double.
        except (TimeoutError, socket.timeout):
            return fail("api_timeout", "Model request timed out.", "timeout")
        except error.HTTPError as exc:
            return fail("api_error", f"Model HTTP request failed (status {exc.code}).")
        except error.URLError as exc:
            if isinstance(exc.reason, (TimeoutError, socket.timeout)):
                return fail("api_timeout", "Model request timed out.", "timeout")
            return fail("api_error", "Model connection failed.")
        except (OSError, ValueError, KeyError, IndexError, TypeError):
            return fail("api_error", "Model request failed or response envelope was invalid.")
    else:
        return fail("config_error", "Supported backends: custom, mock.")
    if not output.strip():
        return fail("empty_output", "Model returned empty content.", "failed")
    extracted = extract_rtl(output)
    if extracted is None:
        return fail("extraction_failed", "Expected one labeled RTL block with complete module boundaries.", "failed")
    code, extension = extracted
    try:
        candidate = run_dir / ("candidate" + extension)
        candidate.write_text(code, encoding="utf-8")
    except OSError:
        return fail("save_error", "Cannot save candidate in output directory.")
    result.update(status="success", candidate_path=str(candidate))
    result["candidate_hash"] = source_hash(code)
    result["candidate_fingerprint"] = rtl_fingerprint(code)
    if result["candidate_fingerprint"] == rtl_fingerprint(rtl):
        result.update(is_duplicate=True, duplicate_of="current_input")
    else:
        match = next((h for h in reversed(history) if h.get("candidate_fingerprint") == result["candidate_fingerprint"]), None)
        if match:
            result.update(is_duplicate=True, duplicate_of=match["run_id"])
    return finish()
