"""Compile a validated BehavioralModel into TLC input texts."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from .schemas import BehavioralModel, BooleanVariable, EnumVariable, Expression, IntegerVariable
from .validator import validate_model


@dataclass(frozen=True)
class TlaFiles:
    tla: str
    cfg: str


def _literal(value: str | bool | int) -> str:
    if type(value) is bool:
        return "TRUE" if value else "FALSE"
    if type(value) is int:
        return str(value)
    if isinstance(value, str):
        return json.dumps(value, ensure_ascii=True)
    raise ValueError(f"unsupported TLA+ literal: {value!r}")


def compile_expression(expression: Expression | Any) -> str:
    """Compile a DSL term or predicate; generate_tla validates it first."""
    node = expression.root if isinstance(expression, Expression) else expression
    if not isinstance(node, dict):
        return _literal(node)
    if len(node) != 1:
        raise ValueError("expression must contain one operator")
    operator, args = next(iter(node.items()))
    if operator == "var":
        return f"v_{args}"
    if operator == "eq":
        return f"({compile_expression(args[0])} = {compile_expression(args[1])})"
    if operator == "in":
        elements = ", ".join(compile_expression(item) for item in args[1])
        return f"({compile_expression(args[0])} \\in {{{elements}}})"
    if operator in {"and", "or"}:
        joiner = " /\\ " if operator == "and" else " \\/ "
        return "(" + joiner.join(compile_expression(item) for item in args) + ")"
    if operator == "not":
        return f"~({compile_expression(args)})"
    raise ValueError(f"unsupported expression operator: {operator}")


def _domain(variable: EnumVariable | BooleanVariable | IntegerVariable) -> str:
    if isinstance(variable, EnumVariable):
        return "{" + ", ".join(_literal(value) for value in variable.values) + "}"
    if isinstance(variable, BooleanVariable):
        return "BOOLEAN"
    return f"({variable.min}..{variable.max})"


def _definition(name: str, clauses: list[str]) -> str:
    return f"{name} ==\n" + "\n".join(f"  /\\ {clause}" for clause in clauses)


def generate_tla(model: BehavioralModel | dict[str, Any], module_name: str = "Model") -> TlaFiles:
    """Return .tla and .cfg contents for a fully validated finite model."""
    model = validate_model(model)
    if not module_name.isascii() or not module_name or not module_name[0].isalpha() or not all(
        char.isalnum() or char == "_" for char in module_name
    ):
        raise ValueError("module_name must be an ASCII identifier")

    names = [variable.name for variable in model.variables]
    tuple_expr = "<<" + ", ".join(f"v_{name}" for name in names) + ">>"
    lines = [
        f"---- MODULE {module_name} ----",
        "EXTENDS Integers",
        "",
        "VARIABLES " + ", ".join(f"v_{name}" for name in names),
        f"vars == {tuple_expr}",
        "",
        _definition("TypeOK", [f"v_{variable.name} \\in {_domain(variable)}" for variable in model.variables]),
        "",
        _definition("Init", [f"v_{name} = {_literal(model.initial[name])}" for name in names]),
    ]

    for transition in model.transitions:
        assigned = {effect.set[0]: effect.set[1] for effect in transition.effects}
        clauses = [compile_expression(transition.guard)]
        clauses.extend(
            f"v_{name}' = {compile_expression(assigned[name])}"
            for name in names
            if name in assigned
        )
        unchanged = [f"v_{name}" for name in names if name not in assigned]
        if unchanged:
            clauses.append("UNCHANGED <<" + ", ".join(unchanged) + ">>")
        lines.extend(["", _definition(f"Step_{transition.name}", clauses)])

    # An explicit stutter action keeps the transition relation total. This lets
    # TLC check state properties even for terminal states without a deadlock error.
    choices = [f"Step_{transition.name}" for transition in model.transitions]
    choices.append("UNCHANGED vars")
    lines.extend(
        [
            "",
            "Next ==\n" + "\n".join(f"  \\/ {choice}" for choice in choices),
            "",
            "Spec == Init /\\ [][Next]_vars",
        ]
    )
    for prop in model.properties:
        expression = compile_expression(prop.expression)
        if prop.type == "forbidden_state":
            expression = f"~({expression})"
        lines.extend(["", f"Property_{prop.name} == {expression}"])
    lines.extend(["", "====", ""])

    cfg_lines = ["SPECIFICATION Spec", "INVARIANT TypeOK"]
    cfg_lines.extend(f"INVARIANT Property_{prop.name}" for prop in model.properties)
    return TlaFiles("\n".join(lines), "\n".join(cfg_lines) + "\n")
