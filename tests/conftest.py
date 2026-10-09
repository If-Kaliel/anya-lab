import pytest
from fastapi.testclient import TestClient

from backend.app import create_app
from scripts.make_demo import make_demo


@pytest.fixture(scope="session")
def demo_video(tmp_path_factory):
    path = tmp_path_factory.mktemp("media") / "synthetic.mp4"
    make_demo(path)
    return path


@pytest.fixture
def client(tmp_path):
    with TestClient(create_app(tmp_path / "local-data")) as client:
        yield client


@pytest.fixture
def imported(client, demo_video):
    response = client.post("/api/videos", files={"file": ("demo.mp4", demo_video.read_bytes(), "video/mp4")}, data={"synthetic": "true"})
    assert response.status_code == 201, response.text
    return response.json()
