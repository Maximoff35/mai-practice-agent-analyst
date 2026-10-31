"""JSON-facing data structures for the first Model Checker milestone."""

from __future__ import annotations

from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, RootModel, StringConstraints, model_validator


Identifier = Annotated[str, StringConstraints(pattern=r"^[A-Za-z][A-Za-z0-9_]*$")]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class SourceReference(StrictModel):
    """A verified link to an explicitly marked requirement fragment."""

    id: str = Field(min_length=1, pattern=r"^[A-Za-z][A-Za-z0-9_-]*$")
    fragment: str = Field(min_length=1)


class EnumVariable(StrictModel):
    name: Identifier
    type: Literal["enum"]
    values: list[str] = Field(min_length=1)


class BooleanVariable(StrictModel):
    name: Identifier
    type: Literal["boolean"]


class IntegerVariable(StrictModel):
    name: Identifier
    type: Literal["integer"]
    min: int
    max: int


Variable = Annotated[
    EnumVariable | BooleanVariable | IntegerVariable, Field(discriminator="type")
]


class Expression(RootModel[Any]):
    """The small JSON expression language, checked semantically by validate_model."""


class SetEffect(StrictModel):
    # JSON represents the fixed pair as an array, which Pydantic may parse to
    # a tuple while preserving strict validation of the two elements.
    set: tuple[Identifier, Expression] = Field(strict=False)


class Transition(StrictModel):
    name: Identifier
    guard: Expression
    effects: list[SetEffect] = Field(min_length=1)
    source_reference: SourceReference | None = Field(
        default=None, exclude_if=lambda value: value is None
    )


class Property(StrictModel):
    name: Identifier
    type: Literal["invariant", "forbidden_state", "reachable", "deadlock_free"]
    expression: Expression | None = Field(default=None, exclude_if=lambda value: value is None)
    terminal_states: Expression | None = Field(default=None, exclude_if=lambda value: value is None)
    source_reference: SourceReference | None = Field(
        default=None, exclude_if=lambda value: value is None
    )

    @model_validator(mode="after")
    def require_type_specific_fields(self) -> "Property":
        if self.type == "deadlock_free":
            if self.expression is not None:
                raise ValueError("deadlock_free не допускает expression; допустимое завершение задайте в terminal_states")
        elif self.expression is None or self.terminal_states is not None:
            raise ValueError("Для этого типа обязательна expression, terminal_states разрешено только для deadlock_free")
        return self


class BehavioralModel(StrictModel):
    variables: list[Variable] = Field(min_length=1)
    initial: dict[Identifier, Any]
    transitions: list[Transition] = Field(min_length=1)
    properties: list[Property] = Field(min_length=1)
