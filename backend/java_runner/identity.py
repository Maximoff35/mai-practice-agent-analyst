"""Отпечатки точной модели и набора исходников без зависимости от LLM."""

from hashlib import sha256
import json

from model_checker import BehavioralModel
from .schemas import JavaArtifact


def fingerprint_model(model: BehavioralModel) -> str:
    return sha256(json.dumps(model.model_dump(mode="json"), ensure_ascii=False,
                             sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()


def fingerprint_artifact(artifact: JavaArtifact) -> str:
    data = {"main_class": artifact.main_class,
            "files": [source.model_dump(mode="json") for source in sorted(artifact.files, key=lambda item: item.path)]}
    return sha256(json.dumps(data, ensure_ascii=False, sort_keys=True,
                             separators=(",", ":")).encode("utf-8")).hexdigest()
