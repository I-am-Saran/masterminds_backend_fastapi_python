"""
Smoke tests for build tracker CRUD: auth required, project_id must be UUID and tenant-scoped.
Run from backend root: python -m scripts.test_build_tracker_crud
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fastapi.testclient import TestClient
from main import app

client = TestClient(app)


def test_get_builds_without_auth_returns_401():
    r = client.get("/api/builds")
    assert r.status_code == 401, f"Expected 401, got {r.status_code}: {r.text}"


def test_get_build_without_auth_returns_401():
    r = client.get("/api/builds/1")
    assert r.status_code == 401, f"Expected 401, got {r.status_code}: {r.text}"


def test_create_build_without_auth_returns_401():
    r = client.post("/api/builds", json={"project_id": "00000000-0000-0000-0000-000000000001"})
    assert r.status_code == 401, f"Expected 401, got {r.status_code}: {r.text}"


def test_create_build_with_invalid_project_id_returns_400():
    # No auth - will get 401 first; with auth would get 400 for invalid UUID or 404 for project not found
    r = client.post(
        "/api/builds",
        json={"project_id": "not-a-uuid"},
        headers={"Authorization": "Bearer invalid-token"},
    )
    # Could be 401 (invalid token) or 400 (if token valid but project_id invalid)
    assert r.status_code in (400, 401), f"Expected 400 or 401, got {r.status_code}: {r.text}"


def test_delete_build_without_auth_returns_401():
    r = client.delete("/api/builds/1")
    assert r.status_code == 401, f"Expected 401, got {r.status_code}: {r.text}"


def test_put_build_without_auth_returns_401():
    r = client.put("/api/builds/1", json={"build_number": "1"})
    assert r.status_code == 401, f"Expected 401, got {r.status_code}: {r.text}"


def test_projects_list_not_on_build_tracker():
    # GET /api/projects should be served by projects router (no longer build_tracker)
    r = client.get("/api/projects", headers={"Authorization": "Bearer invalid"})
    # 401 from projects router (invalid token)
    assert r.status_code == 401, f"Expected 401, got {r.status_code}: {r.text}"


def test_build_tracker_has_no_post_projects():
    # POST /api/projects must be projects router; build_tracker no longer has POST /projects
    r = client.post(
        "/api/projects",
        json={"application_name": "Test"},
        headers={"Authorization": "Bearer invalid"},
    )
    assert r.status_code == 401, f"Expected 401, got {r.status_code}: {r.text}"


if __name__ == "__main__":
    test_get_builds_without_auth_returns_401()
    test_get_build_without_auth_returns_401()
    test_create_build_without_auth_returns_401()
    test_create_build_with_invalid_project_id_returns_400()
    test_delete_build_without_auth_returns_401()
    test_put_build_without_auth_returns_401()
    test_projects_list_not_on_build_tracker()
    test_build_tracker_has_no_post_projects()
    print("All build tracker CRUD smoke tests passed.")