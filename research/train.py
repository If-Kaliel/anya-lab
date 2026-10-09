"""Train a real optional classifier offline from explicitly labeled temporal features.

Input: schema_version=1.0, samples=[{match_id, split, timestamp,
features:[ally_risk, enemy_risk, visibility], label}].
All feature values must be derived from observations at or before timestamp.
Future-label isolation during feature generation is the dataset author's responsibility.
"""
import argparse
import json
from pathlib import Path

from backend.contracts import CLASSES


def validate_samples(dataset):
    import numpy as np
    if dataset.get("schema_version") != "1.0":
        raise ValueError("Expected dataset schema 1.0")
    matches = {}
    samples = dataset["samples"]
    for row in samples:
        if row["split"] not in {"train", "validation", "test"}:
            raise ValueError("Unknown dataset split")
        if row["match_id"] in matches and matches[row["match_id"]] != row["split"]:
            raise ValueError("Match appears in multiple dataset splits")
        matches[row["match_id"]] = row["split"]
        features = np.asarray(row["features"], dtype=float)
        if features.shape != (3,) or not np.isfinite(features).all() or (features < 0).any() or (features > 1).any():
            raise ValueError("Expected three finite features in [0,1]")
        if row["label"] not in CLASSES or not np.isfinite(row["timestamp"]) or row["timestamp"] < 0:
            raise ValueError("Invalid label or timestamp")
    return samples


def train(dataset, output: Path):
    import joblib
    import sklearn
    from sklearn.linear_model import LogisticRegression
    from sklearn.metrics import accuracy_score, log_loss
    from sklearn.pipeline import make_pipeline
    from sklearn.preprocessing import StandardScaler

    samples = validate_samples(dataset)
    training = [r for r in samples if r["split"] == "train"]
    validation = [r for r in samples if r["split"] == "validation"]
    if len(training) < 30 or set(r["label"] for r in training) != set(CLASSES) or not validation:
        raise ValueError("At least 30 training samples, all three classes and an independent validation match are required")
    model = make_pipeline(StandardScaler(), LogisticRegression(random_state=42, max_iter=500))
    model.fit([r["features"] for r in training], [r["label"] for r in training])
    x, y = [r["features"] for r in validation], [r["label"] for r in validation]
    probabilities = model.predict_proba(x)
    metadata = {"schema_version": "1.0", "model": "logistic-regression-v1", "seed": 42,
                "sklearn_version": sklearn.__version__, "class_order": model.classes_.tolist(),
                "feature_order": ["ally_risk", "enemy_risk", "visibility"],
                "training_matches": sorted({r["match_id"] for r in training}),
                "validation_matches": sorted({r["match_id"] for r in validation}),
                "training_count": len(training), "validation_count": len(validation),
                "validation_accuracy": accuracy_score(y, model.predict(x)),
                "validation_log_loss": log_loss(y, probabilities, labels=model.classes_),
                "status": "trained_not_independently_validated"}
    output.mkdir(parents=True, exist_ok=True)
    joblib.dump(model, output / "model.joblib")
    (output / "metadata.json").write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    return metadata


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("dataset", type=Path)
    parser.add_argument("--output", type=Path, default=Path("data/models/supervised-v1"))
    args = parser.parse_args()
    print(json.dumps(train(json.loads(args.dataset.read_text(encoding="utf-8")), args.output), indent=2))
