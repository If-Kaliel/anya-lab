import math

import pytest
from pydantic import ValidationError

from backend.contracts import Probabilities
from backend.evaluation import metrics, resolve
from backend.export import srt_time
from research.train import validate_samples


@pytest.mark.parametrize("p", [dict(ally_first=0.8, enemy_first=0.8, none=0), dict(ally_first=-1, enemy_first=1, none=1), dict(ally_first=float('nan'), enemy_first=0, none=1)])
def test_invalid_probabilities_rejected(p):
    with pytest.raises(ValidationError):
        Probabilities(**p)


def test_known_metrics_and_empty_report():
    result = metrics([{"label": "ally_first", "probabilities": {"ally_first": .7, "enemy_first": .2, "none": .1}, "latency_ms": 10, "unknown_rate": .5}])
    assert result["accuracy"] == 1
    assert result["brier_score"] == pytest.approx(.14)
    assert result["log_loss"] == pytest.approx(-math.log(.7))
    assert result["confusion_matrix"] == [[1, 0, 0], [0, 0, 0], [0, 0, 0]]
    assert metrics([])["accuracy"] is None
    assert result["calibration"] is None


def test_outcome_boundaries_simultaneity_and_ambiguity():
    reviews = [{"start": 0, "end": 30, "reliable": True}]
    def e(t, team="ally", reliable=True):
        return {"timestamp": t, "team": team, "reliable": reliable}
    assert resolve([e(0)], reviews, 0)[0] == "none"
    assert resolve([e(15)], reviews, 0)[0] == "ally_first"
    assert resolve([e(15.01)], reviews, 0)[0] == "none"
    assert resolve([e(8), e(8.05, "enemy")], reviews, 0)[0] is None
    assert resolve([e(8, "unknown")], reviews, 0)[0] is None
    assert resolve([e(8, reliable=False)], reviews, 0)[0] is None
    assert resolve([], [], 0)[0] is None


def test_calibration_counts():
    row = {"label": "none", "probabilities": {"ally_first": .1, "enemy_first": .1, "none": .8}, "latency_ms": 3, "unknown_rate": 1}
    result = metrics([row.copy() for _ in range(30)])
    assert result["calibration"][0]["count"] == 30
    assert result["calibration"][0]["confidence"] == pytest.approx(.8)


def test_dataset_match_split_validation():
    sample = {"match_id": "m1", "split": "train", "timestamp": 0, "features": [.1, .2, .3], "label": "ally_first"}
    assert len(validate_samples({"schema_version": "1.0", "samples": [sample]})) == 1
    with pytest.raises(ValueError, match="multiple"):
        validate_samples({"schema_version": "1.0", "samples": [sample, {**sample, "split": "test"}]})
    assert srt_time(3661.125) == "01:01:01,125"


def test_real_offline_training_with_synthetic_data_only(tmp_path):
    from research.train import train
    classes = ["ally_first", "enemy_first", "none"]
    samples = []
    for split, repetitions in [("train", 10), ("validation", 2)]:
        for j, label in enumerate(classes):
            for i in range(repetitions):
                samples.append({"match_id": f"synthetic-{split}", "split": split, "timestamp": i * 5,
                                "features": [float(j == k) for k in range(3)], "label": label})
    metadata = train({"schema_version": "1.0", "samples": samples}, tmp_path / "model")
    assert metadata["training_count"] == 30
    assert metadata["validation_accuracy"] == 1
    assert (tmp_path / "model" / "model.joblib").is_file()
    assert metadata["status"] == "trained_not_independently_validated"
