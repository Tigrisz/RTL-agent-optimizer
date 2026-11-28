"""Find local rewrite opportunities, without assuming a benchmark name or HDL semantics."""

import re


_NAME = r"[a-zA-Z_$][\w$]*"
_OPERAND = rf"{_NAME}(?:\s*\[[^\[\];\n]{{1,80}}\])?"
_BINARY = re.compile(rf"(?<![\w$])(?P<left>{_OPERAND})\s*(?P<op>[+-])\s*(?P<right>{_OPERAND})")
_COPY = re.compile(rf"\b({_NAME})\s*<=\s*({_NAME})\s*;")
_SUM = re.compile(rf"\b({_NAME})\s*\+\s*({_NAME})\s*\+\s*({_NAME})\b")
_IGNORED = re.compile(r'//[^\n]*|/\*[\s\S]*?\*/|"(?:\\.|[^"\\])*"')


def module_headers(source):
    clean = _IGNORED.sub(" ", source)
    return {m[1]: m[0] for m in re.finditer(rf"\bmodule\s+(?:(?:automatic|static)\s+)?({_NAME})[^;]*;", clean)}


def opportunities(source):
    """Return evidence for the prompt; matching a pattern alone never authorizes a rewrite."""
    clean = _IGNORED.sub(" ", source)
    plans = {}
    copies = dict(_COPY.findall(clean))

    def copy_chain(signal):
        seen = {signal}
        while signal in copies and copies[signal] not in seen:
            signal = copies[signal]
            seen.add(signal)
        return len(seen) - 1

    sums = []
    if re.search(r"\b(?:pos|neg)edge\b", clean):
        for a, b, carry in _SUM.findall(clean):
            stages = min(copy_chain(a), copy_chain(b))
            if stages:
                sums.append((stages, a, b, carry))
    if sums:
        stages, a, b, carry = max(sums)
        target = {"operands": [a, b], "late_operand": carry, "copy_stages": stages}
        plans["pipeline_partial_sum"] = target
        plans["pipeline_block_carry"] = target

    operators = {}
    if re.search(r"\b(if|case)\b|\?", clean):
        for match in _BINARY.finditer(clean):
            pair = tuple(sorted(re.sub(r"\s+", "", match[key]) for key in ("left", "right")))
            operators.setdefault(pair, set()).add(match["op"])
        for pair, ops in operators.items():
            if ops == {"+", "-"}:
                plans["shared_add_sub"] = {"operands": list(pair)}
                plans["parallel_sign_control"] = {"operands": list(pair)}
                break
    return plans
