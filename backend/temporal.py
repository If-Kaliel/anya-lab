from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Observation:
    timestamp: float
    kind: str
    value: float
    confidence: float
    source: str


@dataclass(frozen=True, slots=True)
class Context:
    cutoff: float
    observations: tuple[Observation, ...]

    def __post_init__(self):
        if any(o.timestamp > self.cutoff for o in self.observations):
            raise ValueError("Future observation denied")

    def at(self, timestamp: float):
        if timestamp > self.cutoff:
            raise ValueError("Future memory denied")
        return tuple(o for o in self.observations if o.timestamp <= timestamp)


def snapshot(raw, cutoff, memory_seconds=None):
    # Notes and outcome annotations deliberately never reach models.
    return Context(cutoff, tuple(Observation(
        timestamp=o["timestamp"], kind=o["kind"], value=o["value"],
        confidence=o["confidence"], source=o.get("source", "manual")
    ) for o in raw if o["timestamp"] <= cutoff and (memory_seconds is None or o["timestamp"] >= cutoff - memory_seconds)))
