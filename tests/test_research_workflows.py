import json

import pytest

from backend.storage import canonical
from research.export_dataset import build_dataset
from research.train import validate_samples
from tests.test_blind_replay import experiment


def run(client, video_id, start=0):
    exp = experiment(client, video_id, start=start)
    for timestamp in range(start, 16, 5):
        assert client.post(f"/api/experiments/{exp}/step", json={"timestamp": timestamp}).status_code == 201
    return exp


def test_report_history_and_exports_retain_exact_chosen_revision(client, imported):
    video_id = imported["id"]
    exp = run(client, video_id)
    first = client.post(f"/api/experiments/{exp}/reveal").json()
    client.post(f"/api/videos/{video_id}/reviews", json={"start": 0, "end": 30})
    second = client.post(f"/api/experiments/{exp}/reveal").json()
    assert first["metrics"]["evaluated"] == 0 and second["metrics"]["evaluated"] == 4
    history = client.get(f"/api/experiments/{exp}/reports").json()
    assert [h["report"] for h in history] == [second, first]
    assert client.get(f"/api/experiments/{exp}/export/json?report_id={first['report_id']}").json() == first
    assert client.get(f"/api/experiments/{exp}/reports/{first['report_id']}").json() == first
    other = experiment(client, video_id)
    assert client.get(f"/api/experiments/{other}/export/json?report_id={first['report_id']}").status_code == 400


def test_paired_comparison_uses_common_windows_and_rejects_stale_reports(client, imported):
    video_id = imported["id"]
    client.post(f"/api/videos/{video_id}/reviews", json={"start": 0, "end": 30})
    first, second = run(client, video_id), run(client, video_id, start=5)
    for exp in (first, second):
        client.post(f"/api/experiments/{exp}/reveal")
    response = client.post("/api/comparison/paired", json={"experiment_ids": [first, second]})
    assert response.status_code == 200, response.text
    comparison = response.json()
    assert comparison["timestamps"] == [5, 10, 15]
    assert comparison["common_windows"] == 3
    assert all(r["metrics"]["evaluated"] == 3 for r in comparison["results"])
    client.post(f"/api/videos/{video_id}/events", json={"timestamp": 8, "team": "ally"})
    assert client.post("/api/comparison/paired", json={"experiment_ids": [first, second]}).status_code == 400
    assert client.post("/api/comparison/paired", json={"experiment_ids": [first, first]}).status_code == 422


def test_paired_comparison_requires_same_recording_and_revelation(client, imported):
    first = run(client, imported["id"])
    second = experiment(client, imported["id"])
    assert client.post("/api/comparison/paired", json={"experiment_ids": [first, second]}).status_code == 400
    # Reports with a different source recording must never be paired just by timestamp.
    with client.app.state.store.connect() as db:
        video = {**client.app.state.store.video(imported["id"]), "id": "other"}
        db.execute("INSERT INTO videos VALUES(?,?)", ("other", canonical(video)))
    other = run(client, "other")
    for exp in (first, other):
        client.post(f"/api/experiments/{exp}/reveal")
    assert client.post("/api/comparison/paired", json={"experiment_ids": [first, other]}).status_code == 400


def test_export_features_are_past_only_labels_are_separate_and_synthetic_opt_in(client, imported):
    video_id = imported["id"]
    client.post(f"/api/videos/{video_id}/reviews", json={"start": 0, "end": 30})
    client.post(f"/api/videos/{video_id}/events", json={"timestamp": 8, "team": "enemy"})
    for timestamp, kind, value, confidence in [(0, "ally_risk", .8, .5), (7, "enemy_risk", 1, 1)]:
        client.post(f"/api/videos/{video_id}/observations", json={"timestamp": timestamp, "kind": kind, "value": value, "confidence": confidence, "note": "Future labels must not enter features"})
    assert not client.get("/api/research/dataset").json()["samples"]
    data = client.get("/api/research/dataset?synthetic=true").json()
    assert data["data_mode"] == "technical_demo"
    assert data["samples"][0]["features"] == [.4, 0, 0]
    assert data["samples"][0]["label"] == "enemy_first"
    assert data["samples"][2]["features"] == [.4, 1, 0]
    assert data["samples"][3]["features"] == [0, 1, 0]
    assert "Future labels" not in json.dumps(data)
    assert validate_samples(data) == data["samples"]


def test_offline_training_checks_source_groups_instead_of_clip_ids():
    data = {"schema_version": "1.0", "samples": [
        {"match_id": "clip-a", "source_match_id": "one-match", "split": "train", "timestamp": 0, "features": [0, 0, 0], "label": "none"},
        {"match_id": "clip-b", "source_match_id": "one-match", "split": "validation", "timestamp": 30, "features": [0, 0, 0], "label": "none"}]}
    with pytest.raises(ValueError, match="multiple dataset splits"):
        validate_samples(data)


def test_paired_comparison_refuses_report_predictions_modified_outside_normal_controls(client, imported):
    video_id = imported["id"]
    client.post(f"/api/videos/{video_id}/reviews", json={"start": 0, "end": 30})
    first, second = run(client, video_id), run(client, video_id)
    for exp in (first, second):
        client.post(f"/api/experiments/{exp}/reveal")
    with client.app.state.store.connect() as db:
        db.execute("DROP TRIGGER evaluations_no_update")
        report_id, payload = db.execute("SELECT id,payload FROM evaluations WHERE experiment_id=?", (first,)).fetchone()
        report = json.loads(payload)
        report["rows"][0]["probabilities"] = {"ally_first": .01, "enemy_first": .01, "none": .98}
        db.execute("UPDATE evaluations SET payload=? WHERE id=?", (canonical(report), report_id))
    assert client.app.state.store.verify(first)["valid"]
    response = client.post("/api/comparison/paired", json={"experiment_ids": [first, second]})
    assert response.status_code == 400 and "cadeia" in response.json()["detail"]
