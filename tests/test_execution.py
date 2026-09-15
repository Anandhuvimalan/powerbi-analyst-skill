import asyncio
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace

import pytest

from powerbi_agent.adapters import DesktopBridgeAdapter, ModelingMCPAdapter
from powerbi_agent.core import BuildError, ProjectState, read_json, write_json
from powerbi_agent.orchestrator import build
from powerbi_agent.qa import DIMENSIONS, visual_qa
from powerbi_agent.transaction import ProjectTransaction, digest


class OfflineCLI:
    def validate(self, *args):
        return {"check": "microsoft_report_cli", "status": "unavailable", "detail": "Test double"}


def request(tmp_path):
    (tmp_path / "data.csv").write_text("OrderId,Revenue,Cost,Region\n001,100,60,North\n002,200,90,South\n")
    return {"project": "D.pbip", "sources": ["data.csv"], "business_goal": "Analyze revenue and profit by region"}


def test_end_to_end_build_and_deterministic_rerun(tmp_path):
    spec = request(tmp_path)
    state = build(spec, tmp_path, report_cli=OfflineCLI())
    tx = ProjectTransaction(tmp_path / "D.pbip")
    before = read_json(tx.manifest)["files"]
    second = build(spec, tmp_path, report_cli=OfflineCLI())
    assert read_json(tx.manifest)["files"] == before
    assert (tmp_path / "D.Report/definition.pbir").is_file()
    assert state.status == second.status == "built_pending_runtime"
    assert any(r["check"] == "dax_runtime" and r["status"] == "not_run" for r in state.validation_results)


def test_failed_adapter_cannot_change_existing_project(tmp_path):
    spec = request(tmp_path)
    build(spec, tmp_path, report_cli=OfflineCLI())
    tx = ProjectTransaction(tmp_path / "D.pbip")
    before = read_json(tx.manifest)["files"]

    class BrokenWriter:
        def apply(self, *args):
            raise BuildError("Injected adapter failure")
    with pytest.raises(BuildError, match="Injected"):
        build(spec, tmp_path, report_adapter=BrokenWriter(), report_cli=OfflineCLI())
    assert all(digest(tmp_path / p) == h for p, h in before.items())
    assert not tx.lock.exists()


def test_user_edits_and_concurrent_edits_block_publication(tmp_path):
    with ProjectTransaction(tmp_path / "D.pbip") as tx:
        write_json(tx.stage / "D.pbip", {"original": 1})
        tx.publish()
    (tmp_path / "D.pbip").write_text("manual edit")
    with pytest.raises(BuildError, match="Externally edited"):
        with ProjectTransaction(tmp_path / "D.pbip"):
            pass
    assert (tmp_path / "D.pbip").read_text() == "manual edit"


def test_partial_publication_rolls_back(tmp_path, monkeypatch):
    write_json(tmp_path / "D.pbip", {"original": True})
    original = (tmp_path / "D.pbip").read_bytes()
    import powerbi_agent.transaction as module
    actual_replace = module.os.replace
    count = 0

    def fail_second(source, destination):
        nonlocal count
        count += 1
        if count == 2:
            raise OSError("Injected disk failure")
        actual_replace(source, destination)

    with ProjectTransaction(tmp_path / "D.pbip") as tx:
        write_json(tx.stage / "D.pbip", {"new": True})
        write_json(tx.stage / "Z.json", {"new": True})
        monkeypatch.setattr(module.os, "replace", fail_second)
        with pytest.raises(OSError, match="disk"):
            tx.publish()
        assert (tmp_path / "D.pbip").read_bytes() == original
        assert not (tmp_path / "Z.json").exists()
        assert not tx.journal.exists()


def test_path_traversal_in_starter_and_manifest_are_blocked(tmp_path):
    spec = request(tmp_path)
    write_json(tmp_path / "D.pbip", {"artifacts": [{"report": {"path": "../escape.Report"}}]})
    with pytest.raises(BuildError, match="escapes"):
        build(spec, tmp_path, report_cli=OfflineCLI())


def test_existing_unmanaged_model_is_preserved(tmp_path):
    spec = request(tmp_path)
    folder = tmp_path / "D.SemanticModel/definition/tables"
    folder.mkdir(parents=True)
    (folder / "T.tmdl").write_text("table T")
    with pytest.raises(BuildError, match="unmanaged"):
        build(spec, tmp_path, report_cli=OfflineCLI())
    assert (folder / "T.tmdl").read_text() == "table T"


def test_mcp_uses_discovered_schema_and_reports_errors():
    class Session:
        async def call_tool(self, name, args):
            return SimpleNamespace(isError=True, content=[SimpleNamespace(text="Bad DAX")])
    catalog = [{"name": "measure_operations", "inputSchema": {"type": "object", "required": ["request"]}}]
    with pytest.raises(BuildError, match="advertise"):
        asyncio.run(ModelingMCPAdapter.call(Session(), catalog, "invented_api", {}))
    with pytest.raises(BuildError, match="schema"):
        asyncio.run(ModelingMCPAdapter.call(Session(), catalog, "measure_operations", {}))
    with pytest.raises(BuildError, match="Bad DAX"):
        asyncio.run(ModelingMCPAdapter.call(Session(), catalog, "measure_operations", {"request": {}}))


def test_desktop_selection_never_guesses(tmp_path):
    project = tmp_path / "D.pbip"
    desktop = DesktopBridgeAdapter(command=["unused"])
    desktop.status = lambda: {"instances": [{"pid": i, "bridgeStatus": "connected", "currentFilePath": str(project)} for i in [1, 2]]}
    with pytest.raises(BuildError, match="unique"):
        desktop.select_pid(project)
    assert desktop.select_pid(project, 2) == 2


def test_desktop_xmla_refresh_is_rejected_before_connection():
    with pytest.raises(BuildError, match="native Refresh"):
        asyncio.run(ModelingMCPAdapter(command=["must-not-run"]).execute_dax(
            {"connectionString": "Data Source=localhost:12345"}, [], refresh=True))


def test_desktop_open_ignores_unrelated_pid_from_cli(tmp_path):
    desktop = DesktopBridgeAdapter(command=["unused"])
    project = tmp_path / "Fresh.pbip"
    states = iter([
        {"instances": [{"pid": 1, "bridgeStatus": "connected", "currentFilePath": str(tmp_path / "Other.pbip")}]},
        {"instances": [{"pid": 2, "bridgeStatus": "connected", "currentFilePath": str(project)}]}])
    desktop.status = lambda: next(states)
    desktop._run = lambda *a: {"pid": 1, "status": "launched"}
    assert desktop.open(project)["pid"] == 2


def test_blank_desktop_capture_is_rejected_after_bounded_retry(tmp_path):
    from PIL import Image
    desktop = DesktopBridgeAdapter(command=["unused"])
    captures = []
    target = tmp_path / "blank.png"
    def fake_run(*args):
        if args[0] == "screenshot":
            captures.append(args)
            Image.new("RGB", (256, 144), "#eeeeee").save(target)
        return {}
    desktop._run = fake_run
    with pytest.raises(BuildError, match="nearly blank"):
        desktop.screenshot("overview", 1, target)
    assert len(captures) == 3


def test_optional_runtime_stage_does_not_claim_a_mock_is_visual_qa(tmp_path, monkeypatch):
    import powerbi_agent.orchestrator as module
    spec = request(tmp_path)
    spec["runtime"] = {"connection_env": "TEST_PBI_CONNECTION"}
    monkeypatch.setenv("TEST_PBI_CONNECTION", "Data Source=test-server")
    monkeypatch.setattr(module, "execute_runtime", lambda *a: {"check": "dax_runtime", "status": "passed", "assessments": []})
    state = build(spec, tmp_path, report_cli=OfflineCLI())
    assert state.status == "built_runtime_verified"
    assert not state.screenshots and not state.qa_scores


def test_visual_qa_is_bounded_and_uses_screenshot_evidence(tmp_path, report, model):
    class Desktop:
        def select_pid(self, *args):
            return 123
        def screenshot(self, page, pid, path):
            path.write_bytes(b"mock image")
        def reload(self, pid):
            assert pid == 123

    class Reviewer:
        def review(self, request, directory):
            assert all(Path(p).is_file() for p in request["screenshots"])
            return {"scores": {k: 80 for k in DIMENSIONS}, "blocking_issues": True, "patches": [
                {"page": report["pages"][0]["name"], "visual_index": 0, "title": "Revenue metrics"}]}
    state = ProjectState(str(tmp_path / "D.pbip"), "sales")
    saved = []
    result, _ = visual_qa(state, tmp_path / "D.pbip", report, model, Desktop(), Reviewer(), saved.append, tmp_path, maximum=2)
    assert result["status"] == "needs_review"
    assert state.iteration_count == 2
    assert len(saved) == 1
    assert state.qa_scores[0]["evidence"] == "screenshot_review"
