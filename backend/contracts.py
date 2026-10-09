from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class Label(StrEnum):
    ALLY = "ally_first"
    ENEMY = "enemy_first"
    NONE = "none"


CLASSES = tuple(label.value for label in Label)


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)


class ObservationInput(StrictModel):
    timestamp: float = Field(ge=0)
    kind: Literal["ally_risk", "enemy_risk", "visibility"]
    value: float = Field(ge=0, le=1)
    confidence: float = Field(ge=0, le=1)
    note: str = Field(default="", max_length=500)


class EventInput(StrictModel):
    timestamp: float = Field(ge=0)
    team: Literal["ally", "enemy", "unknown"]
    reliable: bool = True
    note: str = Field(default="", max_length=500)


class ReviewInput(StrictModel):
    start: float = Field(ge=0)
    end: float = Field(gt=0)
    reliable: bool = True
    note: str = Field(default="", max_length=500)

    @model_validator(mode="after")
    def ordered(self):
        if self.end <= self.start:
            raise ValueError("Review end must follow start")
        return self


class ExperimentInput(StrictModel):
    video_id: str
    model_id: Literal["heuristic-v1", "historical-v1"] = "heuristic-v1"
    training_match_ids: list[str] = Field(default_factory=list)
    start: float = Field(default=0, ge=0)
    step: float = Field(default=5, ge=1, le=60)
    horizon: Literal[15] = 15
    seed: int = 42
    memory_seconds: float = Field(default=60, ge=10, le=600)


class RevisionCommand(StrictModel):
    expected_revision: int = Field(ge=0)
    reason: str = Field(min_length=1, max_length=500)

    @field_validator("reason")
    @classmethod
    def meaningful_reason(cls, value):
        if not value.strip():
            raise ValueError("Informe o motivo da revisão")
        return value.strip()


class PairedComparisonInput(StrictModel):
    experiment_ids: list[str] = Field(min_length=2, max_length=2)

    @field_validator("experiment_ids")
    @classmethod
    def distinct_experiments(cls, value):
        if value[0] == value[1]:
            raise ValueError("Selecione dois experimentos diferentes")
        return value


class AnnotationRevision(RevisionCommand):
    annotation: ObservationInput | EventInput | ReviewInput


class AnnotationRestore(RevisionCommand):
    target_revision: int = Field(ge=0)


class StepInput(StrictModel):
    timestamp: float = Field(ge=0)


class Probabilities(StrictModel):
    ally_first: float = Field(ge=0, le=1)
    enemy_first: float = Field(ge=0, le=1)
    none: float = Field(ge=0, le=1)

    @model_validator(mode="after")
    def sum_to_one(self):
        if abs(sum(self.model_dump().values()) - 1) > 1e-6:
            raise ValueError("Probabilities must sum to one")
        return self
