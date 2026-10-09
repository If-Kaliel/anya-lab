"""Feature extraction accepts only a frozen, time-bounded Context."""
from backend.temporal import Context

FEATURE_ORDER = ("ally_risk", "enemy_risk", "visibility")


def temporal_features(context: Context):
    features, observed = [], []
    for kind in FEATURE_ORDER:
        recent = [o for o in context.observations if o.kind == kind and o.confidence > 0
                  and context.cutoff - o.timestamp <= 10]
        latest = max(recent, key=lambda o: o.timestamp) if recent else None
        features.append(latest.value * latest.confidence if latest else 0.0)
        observed.append(latest is not None)
    return features, observed
