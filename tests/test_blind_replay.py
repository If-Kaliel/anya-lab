from dataclasses import FrozenInstanceError
import json
import sqlite3

import pytest

from backend.temporal import Context, Observation, snapshot


def experiment(client, video_id, **extra):
    response = client.post("/api/experiments", json={"video_id": video_id, **extra})
    assert response.status_code == 201, response.text
    return response.json()["id"]


def test_temporal_capability_rejects_future_and_is_immutable():
    future = Observation(6, "ally_risk", 1, 1, "manual")
    with pytest.raises(ValueError, match="Future"):
        Context(5, (future,))
    context = snapshot([{"timestamp": 6, "kind": "ally_risk", "value": 1, "confidence": 1}], 5)
    assert context.observations == ()
    with pytest.raises(ValueError, match="Future"):
        context.at(6)
    with pytest.raises(FrozenInstanceError):
        context.cutoff = 999
    assert not hasattr(context, "video_path")
    assert not hasattr(context, "events")
    assert not hasattr(context, "store")


def test_future_labels_notes_and_observations_never_reach_model(client, imported, monkeypatch):
    video_id = imported["id"]
    client.post(f"/api/videos/{video_id}/observations", json={"timestamp": 0, "kind": "ally_risk", "value": 0.4, "confidence": 1, "note": "future enemy elimination at 8"})
    client.post(f"/api/videos/{video_id}/observations", json={"timestamp": 10, "kind": "enemy_risk", "value": 1, "confidence": 1})
    client.post(f"/api/videos/{video_id}/events", json={"timestamp": 8, "team": "enemy"})
    exp = experiment(client, video_id)
    seen = []
    from backend.models import Heuristic
    original = Heuristic.predict

    def inspect(self, context):
        seen.append(context)
        return original(self, context)

    monkeypatch.setattr(Heuristic, "predict", inspect)
    prediction = client.post(f"/api/experiments/{exp}/step", json={"timestamp": 0}).json()
    assert seen and all(o.timestamp <= 0 for o in seen[0].observations)
    assert all(not hasattr(o, "note") for o in seen[0].observations)
    assert "enemy elimination" not in json.dumps(prediction)
    assert prediction["probabilities"]["ally_first"] > prediction["probabilities"]["enemy_first"]
    assert client.get(f"/api/experiments/{exp}/frame?timestamp=1").status_code == 400
    assert client.get(f"/api/experiments/{exp}/frame?timestamp=0").headers["x-frame-timestamp"] == "0.0"


def test_observations_are_frozen_and_step_order_is_enforced(client, imported):
    video_id = imported["id"]
    exp = experiment(client, video_id)
    client.post(f"/api/videos/{video_id}/observations", json={"timestamp": 0, "kind": "ally_risk", "value": 1, "confidence": 1})
    assert client.post(f"/api/experiments/{exp}/step", json={"timestamp": 5}).status_code == 400
    p = client.post(f"/api/experiments/{exp}/step", json={"timestamp": 0}).json()
    assert p["probabilities"] == {"ally_first": 0.25, "enemy_first": 0.25, "none": 0.5}
    assert client.post(f"/api/experiments/{exp}/step", json={"timestamp": 0}).status_code == 400
    second = client.post(f"/api/experiments/{exp}/step", json={"timestamp": 5}).json()
    assert len(second["observations"]) == 4
    assert all(o["timestamp"] <= 5 for o in second["observations"])


def test_predictions_append_only_chain_and_persistence(client, imported):
    exp = experiment(client, imported["id"])
    client.post(f"/api/experiments/{exp}/step", json={"timestamp": 0})
    store = client.app.state.store
    with pytest.raises(sqlite3.IntegrityError, match="append-only"), store.connect() as db:
        db.execute("UPDATE predictions SET payload='{}'")
    with pytest.raises(sqlite3.IntegrityError, match="append-only"), store.connect() as db:
        db.execute("DELETE FROM predictions")
    assert store.verify(exp)["valid"]
    from backend.storage import Store
    assert Store(store.root).predictions(exp) == store.predictions(exp)
    # An offline attacker who drops a trigger still causes a verification failure.
    with store.connect() as db:
        db.execute("DROP TRIGGER predictions_no_update")
        db.execute("UPDATE predictions SET payload='{}'")
    assert not store.verify(exp)["valid"]
    assert client.post(f"/api/experiments/{exp}/reveal").status_code == 400


def test_historical_training_rejects_same_match_and_test_split(client, imported):
    rejected = client.post("/api/experiments", json={"video_id": imported["id"], "model_id": "historical-v1", "training_match_ids": [imported["id"]]})
    assert rejected.status_code == 400
    assert "Vazamento" in rejected.json()["detail"]
