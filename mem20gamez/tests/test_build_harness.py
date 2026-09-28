"""Tests for the installed build harness.

The harness arrived as a loose `harness/src/` directory and is now a permanent
subpackage of mem20gamez. Integration is where this kind of move actually breaks,
so these tests target the seams: the package resolves its siblings, the app comes
up without a stale filesystem path, the docs are reachable, and the runner is
actually callable.

`bpy` only exists inside Blender, so nothing here may require it. If a test needs
Blender to pass, it is testing the wrong thing.
"""

from __future__ import annotations

import importlib
import json
import sys

import pytest

import mem20gamez.build_harness as harness
from mem20gamez.build_harness import docs as harness_docs

# --- the package resolves ----------------------------------------------------


def test_every_harness_module_imports():
    for name in harness.__all__:
        module = getattr(harness, name)
        assert module is not None, f"{name} did not import"


def test_v21_seam_actually_installs():
    """The runner tolerates a missing v21, so check it is really there.

    Without this the harness silently loses worker bucket routing and still
    looks healthy - the failure mode the import block was written to avoid.
    """
    runner = harness._load("runner")
    assert runner._V21 is not None, "v21 did not resolve as a subpackage; the seam is not installed"


def test_the_substrate_is_importable_for_the_seam():
    """v21 patches mem20's `llm`; the package must put the estate root on the path."""
    assert "/opt/mem20" in sys.path or harness._ESTATE_ROOT in sys.path
    import llm

    assert callable(llm.chat)


def test_lazy_attribute_access_still_works():
    assert harness.runner is harness._load("runner")
    assert harness.v21 is harness._load("v21")


def test_unknown_attribute_raises():
    with pytest.raises(AttributeError):
        _ = harness.definitely_not_a_module


# --- the surface report is honest -------------------------------------------


def test_surface_reports_real_capability():
    surface = harness.surface()
    assert surface["runner_available"] is True
    assert surface["v21_available"] is True
    assert surface["notes"] == [], f"harness reported problems: {surface['notes']}"
    assert surface["app_routes"], "the control surface exposes no API routes"


def test_surface_advertises_the_guide():
    """Findability is part of the deliverable, not a nicety."""
    pointer = harness.surface()["docs"]
    assert pointer["exists"] is True
    assert pointer["readme"].endswith("README.md")
    assert "docs" in pointer["terminal"]
    assert pointer["http"].startswith("/guide")
    assert len(pointer["one_line"]) > 40


def test_the_runner_entry_point_is_callable():
    runner = harness._load("runner")
    assert callable(runner.run_project)
    import inspect

    params = inspect.signature(runner.run_project).parameters
    assert "project" in params
    assert "dry_run" in params, "a planning mode must exist; it is the cheap way to test"


# --- the control surface comes up -------------------------------------------


@pytest.fixture(scope="module")
def client():
    from fastapi.testclient import TestClient

    from mem20gamez.build_harness.app import app

    return TestClient(app)


def test_the_app_imports_despite_the_original_desktop_path(client):
    """app.py used to hardcode /root/Desktop/Beef/harness/static and refused to load."""
    assert client.get("/api/projects").status_code == 200


@pytest.mark.parametrize("path", ["/guide", "/api/docs"])
def test_the_guide_is_reachable(client, path):
    response = client.get(path)
    assert response.status_code == 200
    assert len(response.text) > 3000, "the guide rendered nearly empty"


def test_the_api_serves_the_guide_as_structured_data(client):
    body = client.get("/api/docs").json()
    assert body["guide"]["exists"] is True
    assert "Lumen Forge" in body["markdown"]
    assert "naming law" in body["markdown"].lower()


def test_the_html_guide_contains_the_law(client):
    html = client.get("/guide").text
    assert "how will Jayson see it when he plays" in html, (
        "the central rule is missing from the rendered guide"
    )


def test_the_rendered_html_is_balanced(client):
    html = client.get("/guide").text
    for tag in ("pre", "ul", "table", "blockquote"):
        assert html.count(f"<{tag}>") == html.count(f"</{tag}>"), f"unbalanced <{tag}>"


def test_the_rendered_guide_keeps_its_tables(client):
    """The guide is table-heavy; a renderer that flattens tables loses its meaning."""
    assert client.get("/guide").text.count("<table>") >= 5


def test_swagger_is_not_shadowed_by_the_guide(client):
    """/docs is FastAPI's API reference; the guide must not have taken it over."""
    swagger = client.get("/docs")
    assert swagger.status_code == 200
    assert "swagger" in swagger.text.lower()


def test_the_root_route_never_500s(client):
    assert client.get("/").status_code == 200


# --- the guide itself --------------------------------------------------------


def test_the_readme_states_the_vision_gate_law():
    text = harness_docs.read()
    assert "vision" in text.lower()
    assert "naming law" in text.lower()
    assert "repair worker" in text.lower()


def test_the_readme_documents_every_cli_subcommand():
    text = harness_docs.read()
    for command in ("surface", "docs", "plan", "run", "serve"):
        assert f"build-harness {command}" in text, f"{command} is undocumented"


def test_the_readme_documents_the_environment_variables():
    text = harness_docs.read()
    for var in ("HARNESS_PROJECT_DIR", "HARNESS_PORT", "HARNESS_MAX_ATTEMPTS", "HARNESS_3D_LLM"):
        assert var in text, f"{var} is undocumented"


def test_readme_paths_point_at_the_real_home():
    """No stale /root/Desktop paths may survive the move."""
    text = harness_docs.read()
    assert "/root/Desktop" not in text, "the guide still references the original machine"


def test_the_project_dir_default_honours_the_environment(tmp_path, monkeypatch):
    monkeypatch.setenv("HARNESS_PROJECT_DIR", str(tmp_path / "harness-projects"))
    app_module = importlib.import_module("mem20gamez.build_harness.app")
    importlib.reload(app_module)
    try:
        assert app_module.PROJECT_DIR == tmp_path / "harness-projects"
        assert app_module.STATIC_DIR.is_dir(), "the static dir must be created, not assumed"
    finally:
        monkeypatch.delenv("HARNESS_PROJECT_DIR", raising=False)
        importlib.reload(app_module)


def test_docs_html_escapes_injected_markup():
    """A guide is content; it must not be able to inject script into /docs."""
    nasty = "# t\n\n<script>alert(1)</script>\n"
    html_out = harness_docs.as_html(nasty)
    assert "<script>" not in html_out
    assert "&lt;script&gt;" in html_out


def test_docs_pointer_is_json_serialisable():
    assert json.loads(json.dumps(harness_docs.pointer()))
