"""Deterministic BehavioralModel validation and TLA+ generation."""

from .schemas import BehavioralModel
from .schemas import SourceReference
from .references import (
    SourceReferenceValidationError,
    attach_result_references,
    validate_source_references,
)
from .tla import TlaFiles, compile_expression, generate_tla
from .validator import ModelValidationError, validate_model
from .result import PropertyResult, TraceState, TLCStatistics, VerificationResult, VerificationStatus
from .runner import TLCConfig, verify

__all__ = [
    "BehavioralModel",
    "PropertyResult",
    "SourceReference",
    "SourceReferenceValidationError",
    "attach_result_references",
    "ModelValidationError",
    "TLCConfig",
    "TLCStatistics",
    "TlaFiles",
    "TraceState",
    "VerificationResult",
    "VerificationStatus",
    "compile_expression",
    "generate_tla",
    "validate_model",
    "validate_source_references",
    "verify",
]
