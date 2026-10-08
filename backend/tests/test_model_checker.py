from copy import deepcopy

import pytest
from pydantic import ValidationError

from model_checker import (
    ModelValidationError,
    compile_expression,
    generate_tla,
    validate_model,
)


def test_acceptance_fixtures_validate(buggy_model, fixed_model):
    for data in (buggy_model, fixed_model):
        model = validate_model(data)
        assert len(model.transitions) == 3
        assert len(model.properties) == 1


def test_buggy_model_generation_preserves_approved(buggy_model):
    result = generate_tla(buggy_model)
    cancel = result.tla.split("Step_Cancel ==\n", 1)[1].split("\n\n", 1)[0]
    assert 'v_status\' = "Cancelled"' in cancel
    assert "v_cancelled' = TRUE" in cancel
    assert "UNCHANGED <<v_approved>>" in cancel
    assert "v_approved'" not in cancel
    assert 'Property_NoExecutedAfterCancel == ~(((v_status = "Executed") /\\ (v_cancelled = TRUE)))' in result.tla
    assert "INVARIANT Property_NoExecutedAfterCancel" in result.cfg
    assert "SPECIFICATION Spec" in result.cfg


def test_fixed_model_generation_resets_approved(fixed_model):
    result = generate_tla(fixed_model)
    cancel = result.tla.split("Step_Cancel ==\n", 1)[1].split("\n\n", 1)[0]
    assert "v_approved' = FALSE" in cancel
    assert "UNCHANGED" not in cancel


@pytest.mark.parametrize(
    ("expression", "expected"),
    [
        ({"var": "approved"}, "v_approved"),
        ({"eq": [{"var": "status"}, "Created"]}, '(v_status = "Created")'),
        ({"in": [{"var": "status"}, ["Created", "Approved"]]}, '(v_status \\in {"Created", "Approved"})'),
        ({"and": [True, {"not": False}]}, "(TRUE /\\ ~(FALSE))"),
        ({"or": [False, True]}, "(FALSE \\/ TRUE)"),
    ],
)
def test_expression_compiler(expression, expected):
    assert compile_expression(expression) == expected


@pytest.mark.parametrize(
    ("change", "message"),
    [
        (lambda m: m["variables"].append(deepcopy(m["variables"][0])), "duplicate name"),
        (lambda m: m["transitions"].append(deepcopy(m["transitions"][0])), "duplicate transition"),
        (lambda m: m["initial"].pop("approved"), "missing values"),
        (lambda m: m["initial"].update(ghost=False), "unknown variables"),
        (lambda m: m["initial"].update(approved=1), "outside the variable domain"),
        (lambda m: m["initial"].update(status="Unknown"), "outside the variable domain"),
        (lambda m: m["variables"][0].update(values=["Created", "Created"]), "enum values must be unique"),
        (lambda m: m["variables"][0].update(values=["Created", "New\nLine"]), "printable ASCII"),
        (lambda m: m["variables"][0].update(values=[]), "too_short"),
        (lambda m: m["transitions"][0].update(guard={"eq": [{"var": "missing"}, "Created"]}), "unknown variable"),
        (lambda m: m["transitions"][0].update(guard={"eq": [{"var": "approved"}, "Created"]}), "different types"),
        (lambda m: m["transitions"][0].update(guard={"in": [{"var": "status"}, []]}), "nonempty list"),
        (lambda m: m["transitions"][0].update(guard={"not": {"var": "status"}}), "must be boolean"),
        (lambda m: m["transitions"][0]["effects"].append({"set": ["status", "Cancelled"]}), "assigned twice"),
        (lambda m: m["transitions"][0]["effects"].append({"set": ["ghost", True]}), "unknown variable"),
        (lambda m: m["transitions"][0]["effects"].append({"set": ["cancelled", "Created"]}), "wrong type"),
        (lambda m: m["transitions"][0]["effects"].append({"set": ["cancelled", 1]}), "wrong type"),
        (lambda m: m["transitions"][0]["effects"].append({"set": ["cancelled", {"var": "status"}]}), "wrong type"),
        (lambda m: m["transitions"][0]["effects"].append({"set": ["cancelled", {"var": "missing"}]}), "unknown variable",),
        (lambda m: m["transitions"][0]["effects"][0]["set"].__setitem__(1, "Unknown"), "outside target domain"),
        (lambda m: m["properties"][0].update(expression={"var": "ghost"}), "unknown variable"),
        (lambda m: m["properties"][0].update(expression={"xor": [True, False]}), "unsupported operator"),
        (lambda m: m["properties"][0].update(type="reachable"), "literal_error"),
    ],
)
def test_invalid_models(buggy_model, change, message):
    change(buggy_model)
    with pytest.raises((ModelValidationError, ValidationError), match=message):
        validate_model(buggy_model)


def test_duplicate_property_names_are_rejected(buggy_model):
    buggy_model["properties"].append(deepcopy(buggy_model["properties"][0]))

    with pytest.raises(ModelValidationError, match="duplicate property name"):
        validate_model(buggy_model)


@pytest.mark.parametrize(
    ("change", "message"),
    [
        (lambda m: m["transitions"][0].update(guard="not a predicate"), "expected one expression operator"),
        (lambda m: m["transitions"][0].update(guard={"eq": [True]}), "eq requires two operands"),
        (lambda m: m["properties"][0].update(expression={"and": [True]}), "and requires at least two predicates"),
        (lambda m: m["properties"][0].update(expression={"not": {"var": "status"}}), "must be boolean"),
    ],
)
def test_transitions_and_properties_require_boolean_expressions(buggy_model, change, message):
    change(buggy_model)

    with pytest.raises(ModelValidationError, match=message):
        validate_model(buggy_model)


def test_transition_effects_must_not_be_empty(buggy_model):
    buggy_model["transitions"][0]["effects"] = []

    with pytest.raises(ValidationError, match="too_short"):
        validate_model(buggy_model)


def test_transitions_must_not_be_empty(buggy_model):
    buggy_model["transitions"] = []

    with pytest.raises(ValidationError, match="too_short"):
        validate_model(buggy_model)


def test_bounded_integer_domain_and_effect(buggy_model):
    buggy_model["variables"].append({"name": "count", "type": "integer", "min": 0, "max": 2})
    buggy_model["initial"]["count"] = 0
    buggy_model["transitions"][0]["effects"].append({"set": ["count", 2]})
    result = generate_tla(buggy_model)
    assert "v_count \\in (0..2)" in result.tla
    assert "v_count' = 2" in result.tla
    assert "UNCHANGED <<v_approved, v_count>>" in result.tla


def test_integer_initial_and_effect_bounds(buggy_model):
    buggy_model["variables"].append({"name": "count", "type": "integer", "min": 0, "max": 2})
    buggy_model["initial"]["count"] = 3
    with pytest.raises(ModelValidationError, match="initial.count"):
        validate_model(buggy_model)
    buggy_model["initial"]["count"] = 0
    buggy_model["transitions"][0]["effects"].append({"set": ["count", 3]})
    with pytest.raises(ModelValidationError, match="outside target domain"):
        validate_model(buggy_model)


def test_variable_source_must_fit_target_domain(buggy_model):
    buggy_model["variables"].append({"name": "limited", "type": "enum", "values": ["Created"]})
    buggy_model["initial"]["limited"] = "Created"
    buggy_model["transitions"][0]["effects"].append({"set": ["limited", {"var": "status"}]})
    with pytest.raises(ModelValidationError, match="source enum domain exceeds"):
        validate_model(buggy_model)


@pytest.mark.parametrize(
    ("variable", "message"),
    [
        ({"name": "count", "type": "integer", "min": 3, "max": 2}, "min must be <= max"),
        ({"name": "count", "type": "integer", "min": 0}, "Field required"),
        ({"name": "count", "type": "float"}, "union_tag_invalid"),
    ],
)
def test_invalid_variable_domains_and_types(buggy_model, variable, message):
    buggy_model["variables"].append(variable)
    buggy_model["initial"]["count"] = 0
    with pytest.raises((ModelValidationError, ValidationError), match=message):
        validate_model(buggy_model)


def test_invariant_and_negation(buggy_model):
    buggy_model["properties"] = [
        {"name": "Safe", "type": "invariant", "expression": {"not": {"var": "cancelled"}}}
    ]
    result = generate_tla(buggy_model)
    assert "Property_Safe == ~(v_cancelled)" in result.tla
    assert "INVARIANT Property_Safe" in result.cfg


def test_generated_names_do_not_shadow_model_names(buggy_model):
    buggy_model["variables"][1]["name"] = "Init"
    buggy_model["initial"]["Init"] = buggy_model["initial"].pop("approved")
    buggy_model["transitions"][0]["effects"][1]["set"][0] = "Init"
    buggy_model["transitions"][2]["guard"]["eq"][0]["var"] = "Init"
    result = generate_tla(buggy_model)
    assert "VARIABLES v_status, v_Init, v_cancelled" in result.tla
