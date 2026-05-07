import pytest
from fastapi.testclient import TestClient

from codemonkeys.dashboard.server import create_app


@pytest.fixture
def client():
    app = create_app()
    return TestClient(app)


def test_get_agents(client: TestClient):
    resp = client.get("/api/agents")
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)
    assert len(data) >= 3
    names = [a["name"] for a in data]
    assert "make_python_file_reviewer" in names


def test_get_agents_has_fields(client: TestClient):
    resp = client.get("/api/agents")
    agent = resp.json()[0]
    assert "name" in agent
    assert "description" in agent
    assert "accepts" in agent
    assert "default_model" in agent


def test_get_files_tree(client: TestClient):
    resp = client.get("/api/files/tree")
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)
    assert any(f.endswith(".py") for f in data)


def test_get_files_git_changed(client: TestClient):
    resp = client.get("/api/files/git/changed")
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


def test_get_files_git_staged(client: TestClient):
    resp = client.get("/api/files/git/staged")
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


def test_get_files_git_all_py(client: TestClient):
    resp = client.get("/api/files/git/all-py")
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)
    assert all(f.endswith(".py") for f in data)


def test_get_files_git_invalid_mode(client: TestClient):
    resp = client.get("/api/files/git/invalid")
    assert resp.status_code == 400


def test_list_runs_empty(client: TestClient):
    resp = client.get("/api/runs")
    assert resp.status_code == 200
    assert resp.json() == []
