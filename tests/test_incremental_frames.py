import subprocess
from concurrent.futures import ThreadPoolExecutor

import cv2
import numpy as np
import pytest

from backend.frames import FrameExtractor, _FrameStream
from backend.video import frame_at, probe
from tests.test_blind_replay import experiment


def pixels(png):
    return cv2.imdecode(np.frombuffer(png, np.uint8), cv2.IMREAD_COLOR)


def test_incremental_frames_match_reference_and_reuse_decoder(demo_video):
    timestamps = probe(demo_video)["frame_timestamps"]
    with FrameExtractor() as extractor:
        for cutoff in (0, 5.05, 10, 15):
            actual, png = extractor.frame_at(demo_video, timestamps, cutoff)
            expected, reference = frame_at(demo_video, timestamps, cutoff)
            assert actual == expected <= cutoff
            assert np.array_equal(pixels(png), pixels(reference))
        stats = extractor.stats()
        assert stats["decoder_starts"] == 1 and stats["consumed_frames"] == 151
        extractor.frame_at(demo_video, timestamps, 15)
        assert extractor.stats()["cache_hits"] == 1
        assert extractor.stats()["consumed_frames"] == 151


def test_cache_eviction_backward_read_and_shutdown(demo_video):
    timestamps = probe(demo_video)["frame_timestamps"]
    extractor = FrameExtractor(cache_size=2)
    for cutoff in (0, 5, 10):
        extractor.frame_at(demo_video, timestamps, cutoff)
    assert extractor.stats()["cached_frames"] == 2
    timestamp, png = extractor.frame_at(demo_video, timestamps, 0)
    assert timestamp == 0 and np.array_equal(pixels(png), pixels(frame_at(demo_video, timestamps, 0)[1]))
    assert extractor.stats()["decoder_starts"] == 2
    processes = [s.process for s in extractor.sessions.values()]
    extractor.close()
    assert all(p.poll() is not None for p in processes)
    assert extractor.stats()["active_sessions"] == 0


def test_variable_frame_rate_stream_matches_reference(demo_video, tmp_path):
    target = tmp_path / "vfr.mkv"
    subprocess.run(["ffmpeg", "-v", "error", "-i", str(demo_video),
                    "-vf", "setpts=if(lt(N\\,50)\\,N/(10*TB)\\,(5+(N-50)/5)/TB)",
                    "-fps_mode", "vfr", "-c:v", "libx264", str(target)], check=True, timeout=30)
    timestamps = probe(target)["frame_timestamps"]
    with FrameExtractor() as extractor:
        for cutoff in (4.99, 5.15, 5.35):
            timestamp, png = extractor.frame_at(target, timestamps, cutoff)
            expected, reference = frame_at(target, timestamps, cutoff)
            assert timestamp == expected <= cutoff
            assert np.array_equal(pixels(png), pixels(reference))


def test_concurrent_requests_are_serialized_without_mixing_frames(demo_video):
    timestamps = probe(demo_video)["frame_timestamps"]
    with FrameExtractor() as extractor, ThreadPoolExecutor(max_workers=3) as pool:
        cutoffs = [0, 15, 5]
        results = list(pool.map(lambda t: extractor.frame_at(demo_video, timestamps, t), cutoffs))
        for cutoff, (timestamp, png) in zip(cutoffs, results):
            assert timestamp == cutoff
            assert np.array_equal(pixels(png), pixels(frame_at(demo_video, timestamps, cutoff)[1]))


def test_decoder_session_capacity_closes_evicted_process(demo_video, tmp_path):
    other = tmp_path / "other.mp4"
    other.write_bytes(demo_video.read_bytes())
    timestamps = probe(demo_video)["frame_timestamps"]
    with FrameExtractor(max_sessions=1) as extractor:
        extractor.frame_at(demo_video, timestamps, 0)
        original = next(iter(extractor.sessions.values())).process
        extractor.frame_at(other, timestamps, 0)
        assert original.poll() is not None
        assert extractor.stats()["active_sessions"] == 1


@pytest.mark.parametrize("cutoff", [float("nan"), float("inf"), float("-inf"), -1])
def test_invalid_timestamp_is_denied_before_decoder_or_cache(demo_video, cutoff):
    timestamps = probe(demo_video)["frame_timestamps"]
    with FrameExtractor() as extractor:
        with pytest.raises(ValueError):
            extractor.frame_at(demo_video, timestamps, cutoff)
        assert extractor.stats()["decoder_starts"] == 0
    with pytest.raises(ValueError):
        frame_at(demo_video, timestamps, cutoff)


def test_future_cached_frame_and_nonfinite_api_values_remain_denied(client, imported):
    first = experiment(client, imported["id"])
    for cutoff in (0, 5, 10, 15):
        assert client.post(f"/api/experiments/{first}/step", json={"timestamp": cutoff}).status_code == 201
    second = experiment(client, imported["id"])
    client.post(f"/api/experiments/{second}/step", json={"timestamp": 0})
    assert client.get(f"/api/experiments/{second}/frame?timestamp=15").status_code == 400
    for value in ("NaN", "inf", "-inf"):
        assert client.get(f"/api/experiments/{second}/frame?timestamp={value}").status_code == 400


def test_decoder_timeout_and_invalid_stream_release_resources(demo_video, tmp_path, monkeypatch):
    broken = tmp_path / "corrupt.mp4"
    broken.write_bytes(b"not a video")
    with FrameExtractor() as extractor:
        with pytest.raises(ValueError):
            extractor.frame_at(broken, [0], 0)
        assert not extractor.sessions
        processes = []

        def timeout(session, remaining):
            processes.append(session.process)
            raise subprocess.TimeoutExpired(session.command, 120)

        monkeypatch.setattr(_FrameStream, "next_frame", timeout)
        with pytest.raises(subprocess.TimeoutExpired):
            extractor.frame_at(demo_video, probe(demo_video)["frame_timestamps"], 0)
        assert not extractor.sessions
        assert all(p.poll() is not None for p in processes)


@pytest.fixture(scope="module")
def keyframed_videos(tmp_path_factory):
    # 40s with B-frames and short GOPs: closed GOP MP4/MKV (MKV with a shifted first PTS) and open GOP MKV.
    root = tmp_path_factory.mktemp("keyframed")
    source = ["ffmpeg", "-v", "error", "-f", "lavfi", "-i", "testsrc2=size=320x180:rate=30", "-t", "40",
              "-c:v", "libx264", "-bf", "3", "-pix_fmt", "yuv420p"]
    videos = {"closed": (root / "closed.mp4", ["-g", "60"]),
              "shifted": (root / "shifted.mkv", ["-g", "60", "-output_ts_offset", "7"]),
              "open": (root / "open.mkv", ["-g", "45", "-x264-params", "open-gop=1", "-output_ts_offset", "7"])}
    for path, options in videos.values():
        subprocess.run([*source, *options, str(path)], check=True, timeout=120)
    return {name: path for name, (path, _) in videos.items()}


@pytest.mark.parametrize("name", ["closed", "shifted", "open"])
def test_long_jumps_seek_by_keyframe_and_match_reference_pixels(keyframed_videos, name):
    path = keyframed_videos[name]
    metadata = probe(path)
    timestamps, origin = metadata["frame_timestamps"], metadata["first_frame_pts"]
    with FrameExtractor() as extractor:
        for cutoff in (12.34, 31.0, 20.0, 20.5):
            actual, png = extractor.frame_at(path, timestamps, cutoff, origin)
            expected, reference = frame_at(path, timestamps, cutoff)
            assert actual == expected <= cutoff
            assert np.array_equal(pixels(png), pixels(reference))
        stats = extractor.stats()
        # 12.34, 31.0 and the backward jump to 20.0 seek; 20.5 continues the same session.
        assert stats["seeks"] == 3
        if name == "open":
            # Open GOPs report missing references after a seek; every seek is refused, never trusted.
            assert stats["seek_fallbacks"] == 3
        else:
            assert stats["seek_fallbacks"] == 0 and stats["consumed_frames"] < 3 * 90


def test_unverifiable_seek_falls_back_to_sequential_decoding(keyframed_videos):
    path = keyframed_videos["closed"]
    timestamps = probe(path)["frame_timestamps"]
    with FrameExtractor() as extractor:
        # A wrong clock origin cannot be matched to the frame table, so the seek is discarded.
        actual, png = extractor.frame_at(path, timestamps, 25.0, origin=0.0123)
        expected, reference = frame_at(path, timestamps, 25.0)
        assert actual == expected
        assert np.array_equal(pixels(png), pixels(reference))
        assert extractor.stats()["seek_fallbacks"] == 1


def test_legacy_imports_without_origin_never_seek(keyframed_videos):
    path = keyframed_videos["closed"]
    timestamps = probe(path)["frame_timestamps"]
    with FrameExtractor() as extractor:
        extractor.frame_at(path, timestamps, 30.0)
        assert extractor.stats()["seeks"] == 0 and extractor.stats()["consumed_frames"] == 901
