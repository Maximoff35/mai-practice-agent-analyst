"""Provider contract and a deterministic demo implementation."""

from __future__ import annotations

from typing import Protocol

from model_checker import BehavioralModel, VerificationResult, VerificationStatus


class LLMProvider(Protocol):
    """A provider supplies a formal model and explains a checker result."""

    def build_model(self, requirements: str) -> BehavioralModel: ...

    def explain_result(
        self,
        requirements: str,
        model: BehavioralModel,
        result: VerificationResult,
    ) -> str: ...


class UnsupportedRequirementsError(ValueError):
    """The demo provider cannot map this text to its fixed example."""


def _application_model() -> dict:
    """Demo model; the corrected variant changes only the Cancel effect."""
    return {
        "variables": [
            {"name": "status", "type": "enum", "values": ["Created", "Approved", "Cancelled", "Executed"]},
            {"name": "approved", "type": "boolean"},
            {"name": "cancelled", "type": "boolean"},
        ],
        "initial": {"status": "Created", "approved": False, "cancelled": False},
        "transitions": [
            {
                "name": "Approve",
                "guard": {"eq": [{"var": "status"}, "Created"]},
                "effects": [{"set": ["status", "Approved"]}, {"set": ["approved", True]}],
            },
            {
                "name": "Cancel",
                "guard": {"in": [{"var": "status"}, ["Created", "Approved"]]},
                "effects": [{"set": ["status", "Cancelled"]}, {"set": ["cancelled", True]}],
            },
            {
                "name": "Execute",
                "guard": {"eq": [{"var": "approved"}, True]},
                "effects": [{"set": ["status", "Executed"]}],
            },
        ],
        "properties": [
            {
                "name": "NoExecutedAfterCancel",
                "type": "forbidden_state",
                "expression": {
                    "and": [
                        {"eq": [{"var": "status"}, "Executed"]},
                        {"eq": [{"var": "cancelled"}, True]},
                    ]
                },
            }
        ],
    }


class FakeLLMProvider:
    """Fixed application workflow for local development; makes no network calls."""

    def build_model(self, requirements: str) -> BehavioralModel:
        text = requirements.casefold()
        if "заявк" not in text or "отмен" not in text:
            raise UnsupportedRequirementsError(
                "FakeLLMProvider поддерживает только демонстрационный сценарий заявки и отмены."
            )
        data = _application_model()
        if "approved=false" in "".join(text.split()):
            data["transitions"][1]["effects"].append({"set": ["approved", False]})
        return BehavioralModel.model_validate(data)

    def explain_result(
        self,
        requirements: str,
        model: BehavioralModel,
        result: VerificationResult,
    ) -> str:
        if result.status == VerificationStatus.PROPERTY_VIOLATED:
            states = result.counterexample
            if [state.transition for state in states] == [None, "Approve", "Cancel", "Execute"]:
                return (
                    "Заявка создана и согласована, затем пользователь отменяет её. "
                    "После Cancel признак approved остаётся true, поэтому Execute всё ещё разрешён: "
                    "отменённая заявка оказывается исполненной. Нужно запретить Execute после отмены "
                    "или сбрасывать approved при Cancel."
                )
            return "Проверка нашла нарушение свойства. Последовательность состояний приведена в counterexample."
        if result.status == VerificationStatus.PROPERTY_HOLDS:
            return "В проверенной конечной модели TLC не нашёл исполнения отменённой заявки."
        if result.status in {VerificationStatus.TIMEOUT, VerificationStatus.STATE_LIMIT_REACHED}:
            return "Проверка не завершилась; выполнение свойства пока не подтверждено."
        if result.status == VerificationStatus.MODEL_INVALID:
            return "Формальная модель некорректна; проверьте описание состояний, переходов и свойств."
        return "TLC не смог завершить проверку из-за ошибки запуска или выполнения."
