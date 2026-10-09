from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


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
