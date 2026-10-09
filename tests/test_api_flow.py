from pathlib import Path
import subprocess

import pytest

from tests.test_blind_replay import experiment


def test_acceptance_import_predict_annotate_evaluate_export(client, imported):
    video_id = imported["id"]
    assert client.get(f"/api/videos/{video_id}/media", headers={"Range": "bytes=0-99"}).status_code == 206
    exp = experiment(client, video_id)
    for timestamp in (0, 5, 10, 15):
        response = client.post(f"/api/experiments/{exp}/step", json={"timestamp": timestamp})
        assert response.status_code == 201, response.text
        p = response.json()
        assert sum(p["probabilities"].values()) == pytest.approx(1)
    assert client.post(f"/api/experiments/{exp}/step", json={"timestamp": 20}).status_code == 400
    before = client.get(f"/api/experiments/{exp}/predictions").json()
    assert client.post(f"/api/experiments/{exp}/reveal").json()["metrics"]["evaluated"] == 0
    client.post(f"/api/videos/{video_id}/events", json={"timestamp": 8, "team": "ally"})
    client.post(f"/api/videos/{video_id}/events", json={"timestamp": 22, "team": "enemy"})
    client.post(f"/api/videos/{video_id}/reviews", json={"start": 0, "end": 30})
    report = client.post(f"/api/experiments/{exp}/reveal").json()
    assert report["metrics"]["evaluated"] == 4
    assert [r["label"] for r in report["rows"]] == ["ally_first", "ally_first", "enemy_first", "enemy_first"]
    assert report["mode"] == "technical_demo"
    assert client.get(f"/api/experiments/{exp}/predictions").json() == before
    for format in ("json", "csv", "srt"):
        response = client.get(f"/api/experiments/{exp}/export/{format}")
        assert response.status_code == 200 and len(response.content) > 20
    srt = client.get(f"/api/experiments/{exp}/export/srt").text
    assert "PREVISÃO REGISTRADA" in srt and "00:00:00,000 --> 00:00:04,000" in srt
    assert "RESULTADO" not in srt
    assert client.get(f"/api/experiments/{exp}/report").json() == report
    assert client.get("/api/comparison").json()[0]["evaluated"] == 4
    assert client.get(f"/api/videos/{video_id}/dataset").json()["schema_version"] == "1.0"


@pytest.mark.parametrize("filename,payload,status", [("clip.exe", b"not video", 400), ("clip.mp4", b"not video", 422), ("empty.mkv", b"", 422)])
def test_invalid_files(client, filename, payload, status):
    response = client.post("/api/videos", files={"file": (filename, payload)})
    assert response.status_code == status
    assert not list((client.app.state.store.root / "videos").iterdir())


def test_duplicate_recording_cross_split_denied(client, imported, demo_video):
    duplicate = client.post("/api/videos", files={"file": ("other-name.mp4", demo_video.read_bytes())}, data={"split": "train"})
    assert duplicate.status_code == 400


def test_input_paths_origin_and_extra_fields_denied(client, imported):
    assert client.get("/api/videos/..%2f..%2fsecret/media").status_code in {400, 404}
    response = client.post("/api/experiments", json={"video_id": imported["id"], "events": []})
    assert response.status_code == 422
    assert client.post("/api/experiments", json={"video_id": imported["id"]}, headers={"Origin": "https://untrusted.example"}).status_code == 403
    assert client.post(f"/api/videos/{imported['id']}/events", json={"timestamp": 99, "team": "ally"}).status_code == 400
    assert client.post(f"/api/videos/{imported['id']}/reviews", json={"start": 10, "end": 2}).status_code == 422


def test_upload_limit(client, demo_video, monkeypatch):
    monkeypatch.setenv("ANYA_MAX_UPLOAD_MB", "0")
    assert client.post("/api/videos", files={"file": ("demo.mp4", demo_video.read_bytes())}).status_code == 400


def test_actual_frame_never_after_cutoff(demo_video):
    from backend.video import frame_at, probe
    metadata = probe(demo_video)
    timestamp, png = frame_at(demo_video, metadata["frame_timestamps"], 5.05)
    assert timestamp == 5.0 and png.startswith(b"\x89PNG")
    assert timestamp <= 5.05


def test_variable_frame_rate_uses_presentation_timestamps(demo_video, tmp_path):
    from backend.video import frame_at, probe
    target = tmp_path / "variable-rate.mp4"
    subprocess.run(["ffmpeg", "-v", "error", "-i", str(demo_video),
                    "-vf", "setpts=if(lt(N\\,50)\\,N/(10*TB)\\,(5+(N-50)/5)/TB)",
                    "-fps_mode", "vfr", "-c:v", "libx264", str(target)], check=True, timeout=30)
    metadata = probe(target)
    timestamp, _ = frame_at(target, metadata["frame_timestamps"], 5.15)
    assert timestamp == pytest.approx(5.0)
    assert metadata["frame_timestamps"][51] == pytest.approx(5.2)


def test_mkv_ingestion_and_frame(client, demo_video, tmp_path):
    target = tmp_path / "demo.mkv"
    subprocess.run(["ffmpeg", "-v", "error", "-i", str(demo_video), "-c", "copy", str(target)], check=True, timeout=30)
    response = client.post("/api/videos", files={"file": ("demo.mkv", target.read_bytes())})
    assert response.status_code == 201, response.text
    assert response.json()["duration"] >= 29


def test_historical_model_uses_reviewed_training_only(client, imported, tmp_path):
    target = tmp_path / "other-match.mp4"
    subprocess.run(["ffmpeg", "-v", "error", "-f", "lavfi", "-i", "color=c=gray:s=320x180:r=5:d=30", "-c:v", "libx264", str(target)], check=True, timeout=30)
    training = client.post("/api/videos", files={"file": ("train.mp4", target.read_bytes())}, data={"split": "train"}).json()
    client.post(f"/api/videos/{training['id']}/reviews", json={"start": 0, "end": 30})
    exp = experiment(client, imported["id"], model_id="historical-v1", training_match_ids=[training["id"]])
    # Training changes after experiment creation cannot influence the frozen baseline.
    client.post(f"/api/videos/{training['id']}/events", json={"timestamp": 8, "team": "ally"})
    p = client.post(f"/api/experiments/{exp}/step", json={"timestamp": 0}).json()
    assert p["probabilities"] == pytest.approx({"ally_first": 1/7, "enemy_first": 1/7, "none": 5/7})
