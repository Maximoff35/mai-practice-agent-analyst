"""Явный адаптер формата исходной постановки; старый JSON не изменяется."""

from typing import Any

from pydantic import ValidationError

from .result import PropertyResult, VerificationResult, VerificationStatus
from .runner import TLCConfig, verify
from .schemas import BehavioralModel
from .validator import ModelValidationError, validate_model


def case_result(result: VerificationResult, model: BehavioralModel | None = None) -> dict[str, Any]:
    """Перевести трассы и статистику, не меняя семантику результата TLC."""
    def convert(item: VerificationResult | PropertyResult, identifier: str | None) -> dict[str, Any]:
        data = item.model_dump(mode="json", exclude={"stdout", "stderr", "property_results", "property_name"})
        data.update(property_id=identifier, engine="TLC")
        for field in ("counterexample", "witness", "deadlock_path"):
            data[field] = {"steps": [
                {**state.model_dump(mode="json", exclude={"values", "number"}),
                 "number": index, "state": state.values.copy()}
                for index, state in enumerate(getattr(item, field))
            ]}
        data["statistics"] = {
            {"generated_states": "states_generated", "graph_depth": "depth"}.get(key, key): value
            for key, value in data["statistics"].items()
        }
        return data

    identifier = result.violated_property
    if model and len(model.properties) == 1:
        identifier = model.properties[0].name
    data = convert(result, identifier)
    data["property_results"] = [convert(item, item.property_name) for item in result.property_results]
    if model and len(model.properties) == 1 and not data["property_results"]:
        data["property_results"] = [{**convert(result, identifier), "property_type": model.properties[0].type}]
    return data


def check_behavior(model: BehavioralModel | dict[str, Any], config: TLCConfig | None = None) -> dict[str, Any]:
    """Публичный Model Checker Tool с JSON-выводом по исходному Word."""
    try:
        parsed = validate_model(model)
    except (ValidationError, ModelValidationError, ValueError) as error:
        return case_result(VerificationResult(status=VerificationStatus.MODEL_INVALID, message=str(error)))
    return case_result(verify(parsed, config), parsed)
