"""Parse the plain text emitted by the TLC command line runner."""

from __future__ import annotations

import json
import re
from typing import Any

from .result import TLCStatistics, TraceState, VerificationResult, VerificationStatus
from .schemas import BehavioralModel


_STATE_HEADER = re.compile(r"^State\s+(\d+):\s*<([^>]*)>", re.MULTILINE)
_STATE_FIELD = re.compile(r"^\s*/\\\s+v_([A-Za-z][A-Za-z0-9_]*)\s*=\s*(.+?)\s*$")
_SUMMARY = re.compile(
    r"(\d+) states generated,\s*(\d+) distinct states found,\s*(\d+) states left on queue",
    re.IGNORECASE,
)
_DEPTH = re.compile(r"The depth of the complete state graph search is\s+(\d+)", re.IGNORECASE)
_VIOLATION = re.compile(r"Error:\s+Invariant\s+Property_([A-Za-z][A-Za-z0-9_]*)\s+is violated", re.IGNORECASE)
_ANY_INVARIANT = re.compile(r"Error:\s+Invariant\s+\S+\s+is violated", re.IGNORECASE)
_SUCCESS = re.compile(r"Model checking completed\.\s+No error has been found", re.IGNORECASE)
_STATE_LIMIT = re.compile(r"(?:state limit|max(?:imum)? number of states)\s+(?:has been )?reached|too many states", re.IGNORECASE)
_MODEL_ERROR = re.compile(
    r"(?:Semantic error|Syntax error|Lexical error|Parse error|Parsing error|Could not parse|Error in model configuration)",
    re.IGNORECASE,
)
_TLC_ERROR = re.compile(r"^Error:", re.IGNORECASE | re.MULTILINE)
_INTEGER = re.compile(r"-?\d+\Z")


def _value(text: str) -> str | bool | int:
    if text == "TRUE":
        return True
    if text == "FALSE":
        return False
    if _INTEGER.fullmatch(text):
        return int(text)
    if text.startswith('"') and text.endswith('"'):
        try:
            value = json.loads(text)
            if isinstance(value, str):
                return value
        except json.JSONDecodeError:
            pass
    return text


def _states(output: str) -> list[TraceState]:
    headers = list(_STATE_HEADER.finditer(output))
    states: list[TraceState] = []
    for index, header in enumerate(headers):
        end = headers[index + 1].start() if index + 1 < len(headers) else len(output)
        values: dict[str, str | bool | int] = {}
        for line in output[header.end():end].splitlines():
            field = _STATE_FIELD.match(line)
            if field:
                values[field.group(1)] = _value(field.group(2))
        label = header.group(2)
        direct = re.search(r"\bStep_([A-Za-z][A-Za-z0-9_]*)\b", label)
        states.append(
            TraceState(
                number=int(header.group(1)),
                values=values,
                transition=direct.group(1) if direct else None,
                tlc_label=label,
            )
        )
    return states


def _evaluate(node: Any, state: dict[str, str | bool | int]) -> Any:
    if not isinstance(node, dict):
        return node
    operator, args = next(iter(node.items()))
    if operator == "var":
        return state[args]
    if operator == "eq":
        return _evaluate(args[0], state) == _evaluate(args[1], state)
    if operator == "in":
        return _evaluate(args[0], state) in args[1]
    if operator == "and":
        return all(_evaluate(item, state) for item in args)
    if operator == "or":
        return any(_evaluate(item, state) for item in args)
    if operator == "not":
        return not _evaluate(args, state)
    raise ValueError(f"unknown operator {operator}")


def _label_transitions(states: list[TraceState], model: BehavioralModel) -> None:
    """Infer labels from the displayed trace only; this does not explore states."""
    names = {variable.name for variable in model.variables}
    for before, after in zip(states, states[1:]):
        if after.transition or set(before.values) != names or set(after.values) != names:
            continue
        if before.values == after.values:
            continue  # Explicit stuttering cannot be attributed uniquely.
        matching: list[str] = []
        for transition in model.transitions:
            if not _evaluate(transition.guard.root, before.values):
                continue
            expected = before.values.copy()
            for effect in transition.effects:
                target, value = effect.set
                expected[target] = _evaluate(value.root, before.values)
            if expected == after.values:
                matching.append(transition.name)
        if len(matching) == 1:
            after.transition = matching[0]


def parse_tlc_output(
    stdout: str,
    stderr: str,
    exit_code: int | None,
    *,
    model: BehavioralModel | None = None,
    timed_out: bool = False,
) -> VerificationResult:
    """Classify TLC output; success requires an explicit completed marker and exit 0."""
    output = stdout + "\n" + stderr
    summary = list(_SUMMARY.finditer(output))
    depth = list(_DEPTH.finditer(output))
    statistics = TLCStatistics()
    if summary:
        generated, distinct, queued = summary[-1].groups()
        statistics = TLCStatistics(
            generated_states=int(generated),
            distinct_states=int(distinct),
            queued_states=int(queued),
            graph_depth=int(depth[-1].group(1)) if depth else None,
        )
    elif depth:
        statistics.graph_depth = int(depth[-1].group(1))

    common = {"stdout": stdout, "stderr": stderr, "exit_code": exit_code, "statistics": statistics}
    if timed_out:
        return VerificationResult(status=VerificationStatus.TIMEOUT, message="TLC timed out", **common)
    if _STATE_LIMIT.search(output):
        return VerificationResult(status=VerificationStatus.STATE_LIMIT_REACHED, message="TLC state limit reached", **common)
    violation = _VIOLATION.search(output)
    if violation:
        states = _states(output)
        if model:
            _label_transitions(states, model)
        return VerificationResult(
            status=VerificationStatus.PROPERTY_VIOLATED,
            violated_property=violation.group(1),
            counterexample=states,
            **common,
        )
    if _ANY_INVARIANT.search(output):
        return VerificationResult(status=VerificationStatus.ENGINE_ERROR, message="Unrecognized TLC invariant violation", **common)
    if _MODEL_ERROR.search(output):
        return VerificationResult(status=VerificationStatus.MODEL_INVALID, message="TLC rejected the model", **common)
    if _TLC_ERROR.search(output):
        return VerificationResult(status=VerificationStatus.ENGINE_ERROR, message="TLC reported an error", **common)
    if exit_code == 0 and _SUCCESS.search(output):
        return VerificationResult(status=VerificationStatus.PROPERTY_HOLDS, **common)
    return VerificationResult(status=VerificationStatus.ENGINE_ERROR, message="TLC did not complete successfully", **common)
