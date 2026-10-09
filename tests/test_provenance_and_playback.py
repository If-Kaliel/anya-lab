import json
import subprocess
import time
from uuid import uuid4

import pytest

from backend.storage import canonical
from backend.video import probe


def remux(demo_video, tmp_path, offset=0):
    path = tmp_path / f"shifted-{offset}.mkv"
    subprocess.run(["ffmpeg", "-v", "error", "-i", str(demo_video), "-c", "copy",
                    "-output_ts_offset", str(offset), str(path)], check=True, timeout=30)
    return path


def test_source_identity_blocks_reencoded_cross_split_and_overlap(client, demo_video, tmp_path):
    first = client.post("/api/videos", files={"file": ("first.mp4", demo_video.read_bytes())},
                        data={"source_match_id": " Partida-07 ", "split": "train"})
    assert first.status_code == 201 and first.json()["source_match_id"] == "partida-07"
    other = remux(demo_video, tmp_path)
    for data, message in [({"split": "test"}, "mesmo split"), ({"split": "train"}, "sobrepostos")]:
        response = client.post("/api/videos", files={"file": ("other.mkv", other.read_bytes())},
                               data={"source_match_id": "PARTIDA-07", **data})
        assert response.status_code == 400 and message in response.json()["detail"]
    second = client.post("/api/videos", files={"file": ("next.mkv", other.read_bytes())},
                         data={"source_match_id": "PARTIDA-07", "source_offset": "30", "split": "train"})
    assert second.status_code == 201 and second.json()["source_offset"] == 30
    assert len(client.get("/api/videos").json()) == 2
    assert len(list((client.app.state.store.root / "videos").iterdir())) == 2


@pytest.mark.parametrize("data", [{"source_offset": "nan"}, {"source_offset": "inf"}, {"source_offset": "-1"}, {"source_match_id": "a" * 129}])
def test_invalid_provenance_is_rejected_without_orphan_media(client, demo_video, data):
    assert client.post("/api/videos", files={"file": ("bad.mp4", demo_video.read_bytes())}, data=data).status_code == 400
    assert not list((client.app.state.store.root / "videos").iterdir())


def test_inference_checks_source_identity_even_in_legacy_inconsistent_database(client, imported):
    store = client.app.state.store
    original = store.video(imported["id"])
    training = {**original, "id": uuid4().hex, "split": "train", "source_match_id": original["id"]}
    with store.connect() as db:
        db.execute("INSERT INTO videos VALUES(?,?)", (training["id"], canonical(training)))
    response = client.post("/api/experiments", json={"video_id": original["id"], "model_id": "historical-v1", "training_match_ids": [training["id"]]})
    assert response.status_code == 400 and "Vazamento" in response.json()["detail"]


def wait_preview(client, video_id):
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline:
        status = client.get(f"/api/videos/{video_id}/preview").json()
        if status["state"] in {"ready", "failed"}:
            assert status["state"] == "ready", status
            return status
        time.sleep(.05)
    pytest.fail("Preview did not finish within 30 seconds")


def test_shifted_pts_normalized_duration_and_browser_preview(client, demo_video, tmp_path):
    path = remux(demo_video, tmp_path, 7)
    metadata = probe(path)
    assert metadata["first_frame_pts"] >= 7
    assert metadata["duration"] == pytest.approx(30, abs=.001)
    assert metadata["frame_timestamps"][0] == 0
    uploaded = client.post("/api/videos", files={"file": ("offset.mkv", path.read_bytes())}).json()
    video_id = uploaded["id"]
    assert uploaded["requires_preview"]
    assert client.get(f"/api/videos/{video_id}/preview/media").status_code == 400
    assert client.post(f"/api/videos/{video_id}/preview").status_code == 202
    wait_preview(client, video_id)
    previews = client.app.state.previews
    preview = probe(previews.path(video_id))
    assert preview["first_frame_pts"] == pytest.approx(0, abs=.001)
    assert preview["duration"] == pytest.approx(30, abs=.05)
    assert preview["frame_timestamps"] == pytest.approx(metadata["frame_timestamps"], abs=.001)
    assert preview["codec"] == "h264"
    response = client.get(f"/api/videos/{video_id}/preview/media", headers={"Range": "bytes=0-99"})
    assert response.status_code == 206 and response.headers["content-type"] == "video/mp4"
    assert client.post(f"/api/videos/{video_id}/preview").json()["state"] == "ready"
    # Disposable preview metadata can be reconstructed after application restart.
    from backend.playback import PlaybackPreviews
    reopened = PlaybackPreviews(client.app.state.store)
    assert reopened.status(video_id)["state"] == "ready"
    reopened.close()
    exp = client.post("/api/experiments", json={"video_id": video_id}).json()["id"]
    assert client.post(f"/api/experiments/{exp}/step", json={"timestamp": 0}).status_code == 201
    assert client.get(f"/api/experiments/{exp}/frame?timestamp=1").status_code == 400


def test_audio_offset_remains_aligned_and_does_not_extend_video_duration(client, tmp_path):
    path = tmp_path / "audio.mkv"
    subprocess.run(["ffmpeg", "-v", "error", "-f", "lavfi", "-i", "testsrc=size=320x180:rate=10:duration=2",
                    "-f", "lavfi", "-i", "sine=frequency=440:duration=4", "-c:v", "libx264", "-pix_fmt", "yuv420p",
                    "-c:a", "aac", "-output_ts_offset", "5", str(path)], check=True, timeout=30)
    uploaded = client.post("/api/videos", files={"file": ("audio.mkv", path.read_bytes())}).json()
    assert uploaded["duration"] == pytest.approx(2, abs=.01)
    video_id = uploaded["id"]
    client.post(f"/api/videos/{video_id}/preview")
    wait_preview(client, video_id)
    target = client.app.state.previews.path(video_id)
    result = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "stream=codec_type,start_time:format=duration", "-of", "json", str(target)], capture_output=True, check=True)
    streams = json.loads(result.stdout)["streams"]
    assert {s["codec_type"] for s in streams} == {"video", "audio"}
    assert all(abs(float(s["start_time"])) < .05 for s in streams)
    assert client.post("/api/experiments", json={"video_id": video_id}).status_code == 400


def test_preview_failure_and_queue_limit_allow_retry(client, imported, monkeypatch):
    previews = client.app.state.previews
    previews.jobs = {"one": {"state": "queued"}, "two": {"state": "processing"}}
    assert client.post(f"/api/videos/{imported['id']}/preview").status_code == 400
    previews.jobs.clear()
    monkeypatch.setenv("ANYA_FFMPEG", "anya-nonexistent-ffmpeg")
    client.post(f"/api/videos/{imported['id']}/preview")
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline and previews.status(imported["id"])["state"] != "failed":
        time.sleep(.01)
    assert previews.status(imported["id"])["state"] == "failed"
    assert not list(previews.root.glob("*.mp4")) and not previews.processes
    monkeypatch.delenv("ANYA_FFMPEG")
    client.post(f"/api/videos/{imported['id']}/preview")
    wait_preview(client, imported["id"])
