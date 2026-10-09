import json

import pytest

from backend.experiments import ExperimentEngine
from backend.storage import Store
from scripts.backup import create_backup, publish_directory, restore_backup
from tests.test_blind_replay import experiment


def test_online_backup_restores_videos_revisions_reports_and_chain(client, imported, tmp_path):
    video_id = imported["id"]
    event = client.post(f"/api/videos/{video_id}/events", json={"timestamp": 8, "team": "ally"}).json()
    client.post(f"/api/videos/{video_id}/annotations/events/{event['id']}/retract", json={"expected_revision": 0, "reason": "Verificação de backup"})
    exp = experiment(client, video_id)
    client.post(f"/api/experiments/{exp}/step", json={"timestamp": 0})
    report = client.post(f"/api/experiments/{exp}/reveal").json()
    store = client.app.state.store
    original = store.predictions(exp)
    backup, restored = tmp_path / "backup", tmp_path / "restored"
    create_backup(store.root, backup)
    restore_backup(backup, restored)
    recovered = Store(restored)
    assert recovered.predictions(exp) == original and recovered.verify(exp)["valid"]
    assert ExperimentEngine(recovered).report(exp) == report
    assert recovered.annotation_histories(video_id) == store.annotation_histories(video_id)
    assert (restored / "videos" / recovered.video(video_id)["stored_name"]).read_bytes()
    with pytest.raises(ValueError, match="nova"):
        restore_backup(backup, restored)
    with pytest.raises(ValueError, match="nova"):
        create_backup(store.root, backup)


@pytest.mark.parametrize("tamper", ["content", "path", "missing"])
def test_invalid_backup_does_not_create_restore_target(client, imported, tmp_path, tamper):
    backup, target = tmp_path / "backup", tmp_path / "target"
    create_backup(client.app.state.store.root, backup)
    if tamper == "content":
        (backup / "anya.sqlite3").write_bytes(b"tampered")
    elif tamper == "missing":
        next((backup / "videos").iterdir()).unlink()
    else:
        manifest = json.loads((backup / "manifest.json").read_text())
        manifest["files"]["../outside"] = {"sha256": "0" * 64, "bytes": 0}
        (backup / "manifest.json").write_text(json.dumps(manifest))
    with pytest.raises(ValueError):
        restore_backup(backup, target)
    assert not target.exists()


def test_transient_windows_sharing_lock_is_retried_without_overwriting(tmp_path, monkeypatch):
    from pathlib import Path
    original = Path.rename
    attempts = []
    source, target = tmp_path / "staging", tmp_path / "new-target"
    source.mkdir()

    def locked_once(path, destination):
        attempts.append(1)
        if len(attempts) == 1:
            exc = PermissionError("Temporary Windows sharing lock")
            exc.winerror = 32
            raise exc
        return original(path, destination)

    monkeypatch.setattr(Path, "rename", locked_once)
    publish_directory(source, target)
    assert target.is_dir() and len(attempts) == 2
