import json
import sqlite3
from concurrent.futures import ThreadPoolExecutor

import pytest

from backend.storage import AnnotationConflict, Store
from tests.test_blind_replay import experiment


def add(client, video_id, kind, payload):
    response = client.post(f"/api/videos/{video_id}/{kind}", json=payload)
    assert response.status_code == 201, response.text
    return response.json()


def command(client, video_id, kind, annotation_id, operation, **body):
    return client.post(f"/api/videos/{video_id}/annotations/{kind}/{annotation_id}/{operation}", json={
        "expected_revision": 0, "reason": "Conferência da evidência", **body})


def test_correct_outcome_preserves_predictions_and_previous_reports(client, imported):
    video_id = imported["id"]
    event = add(client, video_id, "events", {"timestamp": 8, "team": "ally"})
    add(client, video_id, "reviews", {"start": 0, "end": 30})
    exp = experiment(client, video_id)
    client.post(f"/api/experiments/{exp}/step", json={"timestamp": 0})
    predictions = client.get(f"/api/experiments/{exp}/predictions").json()
    before = client.post(f"/api/experiments/{exp}/reveal").json()
    assert before["rows"][0]["label"] == "ally_first"
    assert client.get(f"/api/experiments/{exp}/report-status").json()["stale"] is False
    with pytest.raises(sqlite3.IntegrityError, match="append-only"), client.app.state.store.connect() as db:
        db.execute("DELETE FROM evaluations")
    corrected = command(client, video_id, "events", event["id"], "revise", annotation={"timestamp": 8, "team": "enemy", "reliable": True})
    assert corrected.status_code == 201, corrected.text
    assert client.get(f"/api/experiments/{exp}/report-status").json()["annotations_changed"] is True
    assert client.get("/api/comparison").json()[0]["stale"] is True
    assert client.get(f"/api/experiments/{exp}/report").json() == before
    after = client.post(f"/api/experiments/{exp}/reveal").json()
    assert after["rows"][0]["label"] == "enemy_first"
    assert after["annotation_hash"] != before["annotation_hash"]
    assert client.get(f"/api/experiments/{exp}/predictions").json() == predictions
    reports = client.get(f"/api/experiments/{exp}/reports").json()
    assert [r["report"] for r in reports] == [after, before]
    assert client.get(f"/api/experiments/{exp}/integrity").json()["valid"] is True
    assert client.get(f"/api/experiments/{exp}/report-status").json()["stale"] is False


def test_observation_revision_does_not_change_frozen_inference(client, imported):
    video_id = imported["id"]
    observation = add(client, video_id, "observations", {"timestamp": 0, "kind": "ally_risk", "value": 0.1, "confidence": 1})
    frozen = experiment(client, video_id)
    correction = {"timestamp": 0, "kind": "ally_risk", "value": 1, "confidence": 1}
    assert command(client, video_id, "observations", observation["id"], "revise", annotation=correction).status_code == 201
    updated = experiment(client, video_id)
    old_prediction = client.post(f"/api/experiments/{frozen}/step", json={"timestamp": 0}).json()
    new_prediction = client.post(f"/api/experiments/{updated}/step", json={"timestamp": 0}).json()
    assert old_prediction["observations"][0]["value"] == .1
    assert new_prediction["observations"][0]["value"] == 1
    assert old_prediction["probabilities"]["ally_first"] < new_prediction["probabilities"]["ally_first"]


def test_retract_restore_and_export_keep_full_history(client, imported):
    video_id = imported["id"]
    event = add(client, video_id, "events", {"timestamp": 8, "team": "ally"})
    assert command(client, video_id, "events", event["id"], "retract").status_code == 201
    assert client.get(f"/api/videos/{video_id}/annotations").json()["events"] == []
    assert command(client, video_id, "events", event["id"], "restore", expected_revision=1, target_revision=0).status_code == 201
    current = client.get(f"/api/videos/{video_id}/annotations").json()["events"][0]
    assert current["revision"] == 2 and current["team"] == "ally"
    dataset = client.get(f"/api/videos/{video_id}/dataset").json()
    history = dataset["annotation_history"][0]
    assert history["valid"]
    assert [e["retracted"] for e in history["entries"]] == [False, True, False]
    assert len({e["hash"] for e in history["entries"]}) == 3
    store = client.app.state.store
    with pytest.raises(sqlite3.IntegrityError, match="append-only"), store.connect() as db:
        db.execute("UPDATE events SET payload='{}'")
    with pytest.raises(sqlite3.IntegrityError, match="append-only"), store.connect() as db:
        db.execute("DELETE FROM annotation_revisions")


def test_concurrent_revision_has_one_winner_and_one_conflict(client, imported):
    event = add(client, imported["id"], "events", {"timestamp": 8, "team": "ally"})
    store = client.app.state.store

    def revise(team):
        try:
            return store.revise_annotation("events", imported["id"], event["id"], 0, "Revisão concorrente", annotation={"timestamp": 8, "team": team, "reliable": True, "note": ""})
        except AnnotationConflict:
            return "conflict"

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(revise, ["enemy", "unknown"]))
    assert results.count("conflict") == 1
    assert store.annotation_histories(imported["id"])[0]["current_revision"] == 1


def test_invalid_corrections_and_stale_edits_are_rejected(client, imported):
    video_id = imported["id"]
    event = add(client, video_id, "events", {"timestamp": 8, "team": "ally"})
    root = event["id"]
    assert command(client, video_id, "events", root, "revise", annotation={"timestamp": 99, "team": "enemy"}).status_code == 400
    assert command(client, video_id, "events", root, "revise", annotation={"start": 0, "end": 15}).status_code == 400
    assert command(client, video_id, "events", root, "retract", reason="   ").status_code == 422
    assert command(client, "another-video", "events", root, "retract").status_code == 400
    assert command(client, video_id, "events", root + 999, "retract").status_code == 400
    assert command(client, video_id, "events", root, "restore", target_revision=999).status_code == 400
    assert command(client, video_id, "events", root, "revise", annotation={"timestamp": 8, "team": "enemy"}).status_code == 201
    assert command(client, video_id, "events", root, "retract").status_code == 409
    assert client.get(f"/api/videos/{video_id}/annotations").json()["events"][0]["team"] == "enemy"


def test_tampered_outcome_history_blocks_evaluation_without_entering_inference(client, imported):
    event = add(client, imported["id"], "events", {"timestamp": 8, "team": "ally"})
    command(client, imported["id"], "events", event["id"], "retract")
    with client.app.state.store.connect() as db:
        db.execute("DROP TRIGGER revisions_no_update")
        db.execute("UPDATE annotation_revisions SET payload='{}'")
    assert client.get(f"/api/videos/{imported['id']}/annotation-history").json()[0]["valid"] is False
    assert client.get(f"/api/videos/{imported['id']}/annotations").status_code == 400
    exp = experiment(client, imported["id"])
    assert client.post(f"/api/experiments/{exp}/step", json={"timestamp": 0}).status_code == 201
    assert client.post(f"/api/experiments/{exp}/reveal").status_code == 400


def test_tampered_observation_history_blocks_new_inference(client, imported):
    observation = add(client, imported["id"], "observations", {"timestamp": 0, "kind": "ally_risk", "value": 1, "confidence": 1})
    command(client, imported["id"], "observations", observation["id"], "retract")
    with client.app.state.store.connect() as db:
        db.execute("DROP TRIGGER revisions_no_update")
        db.execute("UPDATE annotation_revisions SET payload='{}'")
    assert client.post("/api/experiments", json={"video_id": imported["id"]}).status_code == 400


def test_existing_database_annotations_migrate_without_rewriting(tmp_path):
    root = tmp_path / "legacy"
    root.mkdir()
    original = {"timestamp": 8, "team": "ally", "reliable": True, "note": "Legado"}
    with sqlite3.connect(root / "anya.sqlite3") as db:
        db.execute("CREATE TABLE events (id INTEGER PRIMARY KEY, video_id TEXT NOT NULL, payload TEXT NOT NULL)")
        db.execute("INSERT INTO events VALUES(7,'legacy-match',?)", (json.dumps(original),))
    store = Store(root)
    assert store.annotations("events", "legacy-match") == [{"id": 7, "revision": 0, **original}]
    store.revise_annotation("events", "legacy-match", 7, 0, "Correção de legado", retract=True)
    assert store.annotation_histories("legacy-match")[0]["valid"]
    with store.connect() as db:
        assert json.loads(db.execute("SELECT payload FROM events WHERE id=7").fetchone()[0]) == original


def test_unreliable_review_overrides_old_coverage_until_retracted(client, imported):
    video_id = imported["id"]
    add(client, video_id, "reviews", {"start": 0, "end": 30})
    uncertain = add(client, video_id, "reviews", {"start": 5, "end": 10, "reliable": False})
    exp = experiment(client, video_id)
    client.post(f"/api/experiments/{exp}/step", json={"timestamp": 0})
    before = client.post(f"/api/experiments/{exp}/reveal").json()
    assert before["rows"][0]["reason"] == "unreliable_review_overlap"
    command(client, video_id, "reviews", uncertain["id"], "retract")
    assert client.post(f"/api/experiments/{exp}/reveal").json()["rows"][0]["label"] == "none"


def test_legacy_report_hash_does_not_trigger_false_revision_warning(client, imported):
    from backend.storage import canonical, digest
    from backend.experiments import ExperimentEngine
    store = client.app.state.store
    with store.connect() as db:
        for kind, payload in [("events", {"timestamp": 8, "team": "ally", "reliable": True, "note": ""}),
                              ("reviews", {"start": 0, "end": 30, "reliable": True, "note": ""})]:
            db.execute(f"INSERT INTO {kind}(video_id,payload) VALUES(?,?)", (imported["id"], canonical(payload)))
    exp = experiment(client, imported["id"])
    client.post(f"/api/experiments/{exp}/step", json={"timestamp": 0})
    report = client.post(f"/api/experiments/{exp}/reveal").json()
    snapshot = store.annotation_snapshot(imported["id"])
    legacy = {kind: [{k: v for k, v in row.items() if k != "revision"} for row in snapshot[kind]] for kind in ("events", "reviews")}
    report["annotation_hash"] = digest(legacy)
    with store.connect() as db:
        db.execute("INSERT INTO evaluations(experiment_id,payload) VALUES(?,?)", (exp, canonical(report)))
    assert ExperimentEngine(store).report_status(exp)["stale"] is False


def test_reveal_chain_head_matches_snapshot_during_concurrent_step(client, imported, monkeypatch):
    from backend.experiments import ExperimentEngine
    add(client, imported["id"], "reviews", {"start": 0, "end": 30})
    exp = experiment(client, imported["id"])
    first = client.post(f"/api/experiments/{exp}/step", json={"timestamp": 0}).json()
    store = client.app.state.store
    engine = ExperimentEngine(store, client.app.state.frames)
    original = store.annotation_snapshot
    inserted = False

    def concurrent_snapshot(video_id):
        nonlocal inserted
        if not inserted:
            inserted = True
            engine.step(exp, 5)
        return original(video_id)

    monkeypatch.setattr(store, "annotation_snapshot", concurrent_snapshot)
    report = engine.reveal(exp)
    assert len(report["rows"]) == 1
    assert report["prediction_chain_head"] == first["hash"]
    assert engine.report_status(exp)["predictions_changed"] is True
