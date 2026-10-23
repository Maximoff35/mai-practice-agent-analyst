"""Validation and propagation of optional requirement source references."""

from __future__ import annotations

import re

from .result import TraceState, VerificationResult
from .schemas import BehavioralModel, SourceReference


class SourceReferenceValidationError(ValueError):
    """A source reference cannot be confirmed against the input requirements."""


_REQUIREMENT_MARKER = re.compile(r"\[([A-Za-z][A-Za-z0-9_-]*)\]")


def validate_source_references(model: BehavioralModel, requirements: str) -> BehavioralModel:
    """Validate every model reference against its marked requirement fragment."""
    markers = list(_REQUIREMENT_MARKER.finditer(requirements))
    for element in (*model.transitions, *model.properties):
        reference = element.source_reference
        if reference is None:
            continue
        matches = [index for index, marker in enumerate(markers) if marker.group(1) == reference.id]
        if not matches:
            raise SourceReferenceValidationError(
                f"source reference {reference.id!r} is not present in requirements"
            )
        if len(matches) != 1:
            raise SourceReferenceValidationError(f"Маркер требования {reference.id!r} повторяется")
        index = matches[0]
        content_start = markers[index].end()
        content_end = markers[index + 1].start() if index + 1 < len(markers) else len(requirements)
        if not reference.fragment.strip() or reference.fragment not in requirements[content_start:content_end]:
            raise SourceReferenceValidationError(
                f"source reference {reference.id!r} fragment is not present in requirements"
            )
    return model


def _append_unique(references: list[SourceReference], reference: SourceReference | None) -> None:
    if reference is not None and reference not in references:
        references.append(reference)


def attach_result_references(
    result: VerificationResult,
    model: BehavioralModel,
) -> VerificationResult:
    """Attach references to property results and paths after input validation by the caller."""
    transitions = {transition.name: transition for transition in model.transitions}
    properties = {prop.name: prop for prop in model.properties}
    related: list[SourceReference] = []
    property_model = properties.get(result.violated_property or "")
    if property_model is None and len(model.properties) == 1:
        property_model = model.properties[0]
    _append_unique(related, property_model.source_reference if property_model else None)

    def annotate_path(path: list[TraceState], collected: list[SourceReference]) -> list[TraceState]:
        states = []
        for state in path:
            transition = transitions.get(state.transition or "")
            reference = transition.source_reference if transition else None
            state_related = [reference] if reference else []
            states.append(state.model_copy(update={"related_requirements": state_related}))
            _append_unique(collected, reference)
        return states

    counterexample = annotate_path(result.counterexample, related)
    witness = annotate_path(result.witness, related)
    property_results = []
    for item in result.property_results:
        prop = properties.get(item.property_name)
        item_related: list[SourceReference] = []
        _append_unique(item_related, prop.source_reference if prop else None)
        item_counterexample = annotate_path(item.counterexample, item_related)
        item_witness = annotate_path(item.witness, item_related)
        property_results.append(item.model_copy(update={
            "related_requirements": item_related, "counterexample": item_counterexample, "witness": item_witness,
        }))
        for reference in item_related:
            _append_unique(related, reference)
    return result.model_copy(update={
        "counterexample": counterexample, "witness": witness,
        "property_results": property_results, "related_requirements": related,
    })
