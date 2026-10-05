"""Semantic validation of finite models and the expression language."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from .schemas import (
    BehavioralModel,
    BooleanVariable,
    EnumVariable,
    Expression,
    IntegerVariable,
    Variable,
)


class ModelValidationError(ValueError):
    """A model is well-formed JSON but cannot be checked as specified."""


@dataclass(frozen=True)
class TermType:
    kind: str
    variable: Variable | None = None


def _fail(path: str, message: str) -> None:
    raise ModelValidationError(f"{path}: {message}")


def _value_in_domain(value: Any, variable: Variable) -> bool:
    if isinstance(variable, EnumVariable):
        return isinstance(value, str) and value in variable.values
    if isinstance(variable, BooleanVariable):
        return type(value) is bool
    return type(value) is int and variable.min <= value <= variable.max


def _term(node: Any, variables: dict[str, Variable], path: str) -> TermType:
    if isinstance(node, dict):
        if set(node) != {"var"} or not isinstance(node["var"], str):
            _fail(path, "term must be a literal or {'var': name}")
        name = node["var"]
        if name not in variables:
            _fail(path, f"unknown variable {name!r}")
        return TermType(variables[name].type, variables[name])
    if type(node) is bool:
        return TermType("boolean")
    if type(node) is int:
        return TermType("integer")
    if isinstance(node, str):
        return TermType("enum")
    _fail(path, "unsupported literal")


def _compatible(
    left_node: Any,
    left: TermType,
    right_node: Any,
    right: TermType,
    path: str,
) -> None:
    if left.kind != right.kind:
        _fail(path, "operands have different types")
    if left.variable and right.variable:
        # The values of both variables may overlap; equality remains meaningful.
        return
    if left.variable and not _value_in_domain(right_node, left.variable):
        _fail(path, "literal is outside the variable domain")
    if right.variable and not _value_in_domain(left_node, right.variable):
        _fail(path, "literal is outside the variable domain")


def _predicate(node: Any, variables: dict[str, Variable], path: str) -> None:
    if type(node) is bool:
        return
    if not isinstance(node, dict) or len(node) != 1:
        _fail(path, "expected one expression operator")
    operator, args = next(iter(node.items()))
    if operator == "var":
        if _term(node, variables, path).kind != "boolean":
            _fail(path, "bare variable predicate must be boolean")
    elif operator == "eq":
        if not isinstance(args, list) or len(args) != 2:
            _fail(path, "eq requires two operands")
        left = _term(args[0], variables, f"{path}.eq[0]")
        right = _term(args[1], variables, f"{path}.eq[1]")
        _compatible(args[0], left, args[1], right, path)
    elif operator == "in":
        if not isinstance(args, list) or len(args) != 2 or not isinstance(args[1], list) or not args[1]:
            _fail(path, "in requires a term and a nonempty list of literals")
        left = _term(args[0], variables, f"{path}.in[0]")
        for index, item in enumerate(args[1]):
            right = _term(item, variables, f"{path}.in[1][{index}]")
            if right.variable:
                _fail(path, "in set elements must be literals")
            _compatible(args[0], left, item, right, path)
    elif operator in {"and", "or"}:
        if not isinstance(args, list) or len(args) < 2:
            _fail(path, f"{operator} requires at least two predicates")
        for index, item in enumerate(args):
            _predicate(item, variables, f"{path}.{operator}[{index}]")
    elif operator == "not":
        _predicate(args, variables, f"{path}.not")
    else:
        _fail(path, f"unsupported operator {operator!r}")


def validate_model(model: BehavioralModel | Mapping[str, Any]) -> BehavioralModel:
    """Return the parsed model, or raise on an invalid finite-state model."""
    if not isinstance(model, BehavioralModel):
        model = BehavioralModel.model_validate(model)

    variables: dict[str, Variable] = {}
    for variable in model.variables:
        if variable.name in variables:
            _fail("variables", f"duplicate name {variable.name!r}")
        if isinstance(variable, EnumVariable):
            if any(not value for value in variable.values):
                _fail(f"variables.{variable.name}", "enum values must be nonempty strings")
            if any(not value.isascii() or not value.isprintable() for value in variable.values):
                _fail(f"variables.{variable.name}", "enum values must be printable ASCII strings")
            if len(set(variable.values)) != len(variable.values):
                _fail(f"variables.{variable.name}", "enum values must be unique")
        elif isinstance(variable, IntegerVariable) and variable.min > variable.max:
            _fail(f"variables.{variable.name}", "integer min must be <= max")
        variables[variable.name] = variable

    missing = variables.keys() - model.initial.keys()
    extra = model.initial.keys() - variables.keys()
    if missing:
        _fail("initial", f"missing values for {sorted(missing)}")
    if extra:
        _fail("initial", f"unknown variables {sorted(extra)}")
    for name, value in model.initial.items():
        if not _value_in_domain(value, variables[name]):
            _fail(f"initial.{name}", "value is outside the variable domain")

    transition_names: set[str] = set()
    for index, transition in enumerate(model.transitions):
        path = f"transitions[{index}]"
        if transition.name in transition_names:
            _fail(path, f"duplicate transition name {transition.name!r}")
        transition_names.add(transition.name)
        _predicate(transition.guard.root, variables, f"{path}.guard")
        assigned: set[str] = set()
        for effect_index, effect in enumerate(transition.effects):
            name, source = effect.set
            effect_path = f"{path}.effects[{effect_index}]"
            if name not in variables:
                _fail(effect_path, f"unknown variable {name!r}")
            if name in assigned:
                _fail(effect_path, f"variable {name!r} assigned twice")
            assigned.add(name)
            source_type = _term(source.root, variables, effect_path)
            target = variables[name]
            if source_type.kind != target.type:
                _fail(effect_path, "effect value has wrong type")
            if source_type.variable:
                other = source_type.variable
                if isinstance(target, EnumVariable) and not set(other.values).issubset(target.values):
                    _fail(effect_path, "source enum domain exceeds target domain")
                if isinstance(target, IntegerVariable) and not (target.min <= other.min and other.max <= target.max):
                    _fail(effect_path, "source integer domain exceeds target domain")
            elif not _value_in_domain(source.root, target):
                _fail(effect_path, "effect value is outside target domain")

    property_names: set[str] = set()
    for index, prop in enumerate(model.properties):
        path = f"properties[{index}]"
        if prop.name in property_names:
            _fail(path, f"duplicate property name {prop.name!r}")
        property_names.add(prop.name)
        _predicate(prop.expression.root, variables, f"{path}.expression")
    return model
