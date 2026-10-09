from typing import Protocol

from backend.contracts import CLASSES, Probabilities
from backend.temporal import Context


class PredictionModel(Protocol):
    def predict(self, context: Context) -> tuple[Probabilities, list[str]]: ...


class Heuristic:
    def predict(self, context: Context):
        evidence = []
        risks = {}
        for kind in ("ally_risk", "enemy_risk"):
            values = [o for o in context.observations if o.kind == kind
                      and context.cutoff - o.timestamp <= 10 and o.confidence > 0]
            if values:
                latest = max(values, key=lambda o: o.timestamp)
                risks[kind] = latest.value * latest.confidence
                evidence.append(f"{kind}={latest.value:.2f}, confidence={latest.confidence:.2f}, t={latest.timestamp:.3f}s")
            else:
                risks[kind] = 0.0
                evidence.append(f"{kind}: unknown or stale (>10s)")
        # Explicit unvalidated rule. Positive floor prevents false certainty.
        weights = [1 + 3 * risks["ally_risk"], 1 + 3 * risks["enemy_risk"], 2]
        total = sum(weights)
        return Probabilities(**dict(zip(CLASSES, [w / total for w in weights]))), evidence


class Historical:
    def __init__(self, counts):
        self.counts = counts

    def predict(self, context):
        total = sum(self.counts.values()) + 3
        return Probabilities(**{k: (self.counts[k] + 1) / total for k in CLASSES}), [
            f"Training-only class counts: {self.counts}; Laplace smoothing alpha=1"]


REGISTRY = [
    {"id": "heuristic-v1", "name": "Baseline B · Heurístico", "version": "1.0.0",
     "status": "functional_unvalidated", "description": "Regra explícita sobre risco manual recente; sem reconhecimento de heróis."},
    {"id": "historical-v1", "name": "Baseline A · Histórico", "version": "1.0.0",
     "status": "requires_training_matches", "description": "Frequências de janelas revisadas de 15s em partidas de treinamento; suavização de Laplace."},
    {"id": "supervised", "name": "Modelo C · Supervisionado", "version": None,
     "status": "training_interface_only", "description": "Treinamento offline opcional. Sem pesos ou validação disponíveis."},
]
