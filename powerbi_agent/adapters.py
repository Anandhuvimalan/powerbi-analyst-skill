"""Official tool boundaries. No invented preview endpoints or shell interpolation."""
from __future__ import annotations

import asyncio
import datetime
import json
import os
import shutil
import subprocess
import time
import uuid
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Protocol

from .core import BuildError

ROOT = Path(__file__).resolve().parent.parent


class PowerBIModelAdapter(Protocol):
    def apply(self, folder: Path, plan: dict) -> list[str]: ...


class PowerBIReportAdapter(Protocol):
    def apply(self, folder: Path, model_folder: str, plan: dict) -> list[str]: ...


class PowerBIDesktopAdapter(Protocol):
    def status(self) -> dict: ...
    def open(self, project: Path) -> dict: ...
    def reload(self, pid: int) -> dict: ...
    def screenshot(self, page: str, pid: int, path: Path) -> dict: ...


def tool_command(package, entry, executable):
    local = Path(os.environ.get("POWERBI_AGENT_TOOLS_ROOT", ROOT)) / "node_modules" / "@microsoft" / package / entry
    if local.is_file() and shutil.which("node"):
        return [shutil.which("node"), str(local)]
    command = shutil.which(executable)
    if command and Path(command).suffix.lower() not in {".cmd", ".bat", ".ps1"}:
        return [command]
    # Global npm Windows shims cannot be safely passed arbitrary paths without a shell.
    npm_root = Path(os.environ.get("APPDATA", "")) / "npm" / "node_modules" / "@microsoft" / package / entry
    if npm_root.is_file() and shutil.which("node"):
        return [shutil.which("node"), str(npm_root)]
    return None


def run_json(command: list[str], timeout=120, allow_error=False, env=None):
    try:
        result = subprocess.run(command, capture_output=True, text=True, encoding="utf-8", timeout=timeout, env=env,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise BuildError(f"Tool {Path(command[0]).name} failed or timed out. Verify installation and connectivity: {exc}") from exc
    try:
        value = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise BuildError(f"Tool returned no valid JSON (exit {result.returncode}): {result.stderr[-1000:] or result.stdout[-1000:]}") from exc
    if result.returncode and not allow_error:
        raise BuildError(f"Tool failed: {json.dumps(value)[:2000]}")
    return value


class ReportAuthoringAdapter:
    def __init__(self, command=None):
        self.command = command or tool_command("powerbi-report-authoring-cli", "dist/cli.js", "powerbi-report-author")

    def validate(self, report: Path, remote_schema=False):
        if not self.command:
            return {"check": "microsoft_report_cli", "status": "unavailable", "detail": "Run npm ci in this repository."}
        value = run_json(self.command + ["validate", str(report)] + ([] if remote_schema else ["--no-schema"]), allow_error=True)
        return {"check": "microsoft_report_cli", "status": "pending", "remote_schema": remote_schema, "result": value}

    def describe(self, visual_type):
        if not self.command:
            raise BuildError("Microsoft report CLI unavailable; run npm ci.")
        return run_json(self.command + ["catalog", "describe", visual_type])


class DesktopBridgeAdapter:
    def __init__(self, command=None):
        self.command = command or tool_command("powerbi-desktop-bridge-cli", "dist/index.js", "powerbi-desktop")

    def _run(self, *args):
        if not self.command:
            raise BuildError("Desktop Bridge CLI unavailable. Run npm ci, install Power BI Desktop and enable secure local APIs in Preview features.")
        environment = None
        if args and args[0] == "open" and os.name == "nt" and not os.environ.get("PBI_DESKTOP_PATH"):
            # The official CLI currently misses Microsoft Store installations.
            # Discover through the registered package, never hard-code a versioned WindowsApps path.
            discovery = subprocess.run(["powershell.exe", "-NoProfile", "-NonInteractive", "-Command",
                "Get-AppxPackage -Name Microsoft.MicrosoftPowerBIDesktop | Select-Object -ExpandProperty InstallLocation"],
                capture_output=True, text=True, timeout=30, creationflags=subprocess.CREATE_NO_WINDOW)
            directories = [Path(line.strip()) / "bin" / "PBIDesktop.exe" for line in discovery.stdout.splitlines() if line.strip()]
            found = [p for p in directories if p.is_file()]
            if len(found) == 1:
                environment = {**os.environ, "PBI_DESKTOP_PATH": str(found[0])}
        return run_json(self.command + list(args), timeout=180, env=environment)

    def status(self):
        return self._run("status")

    def open(self, project):
        def matches():
            result = self.status()
            return [i for i in result.get("data", result).get("instances", [])
                    if i.get("bridgeStatus") == "connected" and Path(i.get("currentFilePath") or "").resolve() == project.resolve()]
        existing = matches()
        if len(existing) == 1:
            return {"status": "already_open", "pid": existing[0]["pid"]}
        if existing:
            raise BuildError("Several Desktop instances have this project open; close duplicates before automatic opening.")
        self._run("open", str(project))
        # CLI 0.1.2 may return an unrelated already-connected PID immediately.
        for attempt in range(30):
            found = matches()
            if len(found) == 1:
                return {"status": "opened", "pid": found[0]["pid"]}
            if len(found) > 1:
                raise BuildError("Several Desktop instances match the launched project.")
            time.sleep(2)
        raise BuildError("Desktop launched but this PBIP did not connect within 60 seconds. Inspect the matching Desktop instance for loading or credential errors.")

    def select_pid(self, project: Path, requested=None):
        result = self.status()
        data = result.get("data", result)
        matches = [i for i in data.get("instances", []) if i.get("bridgeStatus") == "connected"
                   and Path(i.get("currentFilePath") or "").resolve() == project.resolve()
                   and (requested is None or i.get("pid") == requested)]
        if len(matches) != 1:
            raise BuildError("No unique connected Desktop instance matches the project. Open this PBIP, enable secure local APIs, and set desktop.pid when needed.")
        return matches[0]["pid"]

    def reload(self, pid):
        return self._run("reload", "--pid", str(pid))

    def native_refresh(self, project: Path, pid: int):
        if os.name != "nt":
            raise BuildError("The optional native Refresh fallback requires Windows and English Desktop UI.")
        self.select_pid(project, pid)
        script = Path(__file__).parent / "tools" / "native_refresh.ps1"
        return run_json(["powershell.exe", "-NoProfile", "-NonInteractive", "-File", str(script), "-DesktopProcessId", str(pid)], timeout=45)

    def screenshot(self, page, pid, path):
        path.parent.mkdir(parents=True, exist_ok=True)
        for attempt in range(3):
            result = self._run("screenshot", page, "--pid", str(pid), "--output", str(path))
            if not path.is_file() or path.stat().st_size == 0:
                raise BuildError("Desktop screenshot command did not create an image.")
            from PIL import Image
            with Image.open(path) as img:
                colors = img.convert("RGB").resize((128, 128)).getcolors(16384)
                blank = max(count for count, _ in colors) / 16384 > .93
            if not blank:
                return result
            self.status()
        raise BuildError("Desktop returned nearly blank screenshots after three captures. Rendering/model reload is not finished or the report is empty; no visual QA pass was recorded.")


class ModelingMCPAdapter:
    """Discover schemas at runtime; call only advertised tools with validated inputs."""
    def __init__(self, command=None, timeout=90, allow_write=False):
        self.command = command or tool_command("powerbi-modeling-mcp", "index.js", "powerbi-modeling-mcp")
        self.timeout = timeout
        self.allow_write = allow_write

    @asynccontextmanager
    async def session(self):
        if not self.command:
            raise BuildError("Power BI Modeling MCP unavailable. Run npm ci or configure modeling.command. File-based execution remains available.")
        from mcp import ClientSession, StdioServerParameters
        from mcp.client.stdio import stdio_client
        args = self.command[1:] + ["--start"]
        args += ["--skipconfirmation"] if self.allow_write else ["--readonly"]
        try:
            async with stdio_client(StdioServerParameters(command=self.command[0], args=args, env={**os.environ,
                    "Logging__LogLevel__Default": "Error", "Logging__EventLog__LogLevel__Default": "None"})) as (read, write):
                async with ClientSession(read, write, read_timeout_seconds=datetime.timedelta(seconds=self.timeout)) as session:
                    await session.initialize()
                    yield session
        except BuildError:
            raise
        except Exception as exc:
            def details(error):
                nested = getattr(error, "exceptions", None)
                return "; ".join(details(e) for e in nested) if nested else f"{type(error).__name__}: {error}"
            raise BuildError(f"Modeling MCP connection/operation failed: {details(exc)}. Verify the server package, supported project format, Desktop/runtime availability and authentication.") from exc

    async def discover(self):
        async with self.session() as session:
            result = await session.list_tools()
            return [t.model_dump(mode="json", exclude_none=True) for t in result.tools]

    async def desktop_connection(self, desktop_pid: int):
        """Match the AS child process to the already verified Desktop PID, never its title."""
        if os.name != "nt":
            raise BuildError("Desktop runtime discovery requires Windows.")
        results = await self.operations([{"tool": "connection_operations", "arguments": {"request": {"operation": "ListLocalInstances"}}}])
        instances = []
        for result in results:
            for item in result.get("content", []):
                if item.get("type") == "text":
                    parsed = json.loads(item["text"])
                    if isinstance(parsed.get("data"), list):
                        instances.extend(parsed["data"])
        matches = []
        for instance in instances:
            process_id = instance.get("processId")
            port = instance.get("port")
            if type(process_id) is not int or type(port) is not int or not 1 <= port <= 65535:
                continue
            parent = run_json(["powershell.exe", "-NoProfile", "-NonInteractive", "-Command",
                f"Get-CimInstance Win32_Process -Filter 'ProcessId = {process_id}' | Select-Object -ExpandProperty ParentProcessId | ConvertTo-Json -Compress"])
            if parent == desktop_pid:
                matches.append({"operation": "Connect", "connectionString": f"Data Source=localhost:{port}"})
        if len(matches) != 1:
            raise BuildError("No unique Analysis Services child matches this Desktop project. Wait for model loading, or supply an explicit connection environment variable.")
        return matches[0]

    @staticmethod
    async def call(session, catalog, name, arguments):
        from jsonschema import validate
        tool = next((t for t in catalog if t["name"] == name), None)
        if not tool:
            raise BuildError(f"Installed MCP does not advertise {name}; update the adapter mapping for this version.")
        try:
            validate(arguments, tool["inputSchema"])
        except Exception as exc:
            raise BuildError(f"Arguments do not match discovered schema for {name}: {exc}") from exc
        result = await session.call_tool(name, arguments)
        if result.isError:
            raise BuildError(f"{name} failed: " + " ".join(getattr(c, "text", "") for c in result.content)[:1800])
        data = result.model_dump(mode="json", exclude_none=True)
        for content in data.get("content", []):
            if content.get("type") == "text":
                try:
                    parsed = json.loads(content["text"])
                    if isinstance(parsed, dict) and (parsed.get("success") is False or parsed.get("error")):
                        raise BuildError(f"{name} returned an operation error: {content['text'][:1800]}")
                except json.JSONDecodeError:
                    pass
        return data

    async def operations(self, operations: list[dict]):
        """Explicit operations for current server version; no automatic retry of mutations."""
        async with self.session() as session:
            catalog = [t.model_dump(mode="json") for t in (await session.list_tools()).tools]
            return [await self.call(session, catalog, op["tool"], op["arguments"]) for op in operations]

    async def execute_folder(self, folder: Path, measures: list[dict]):
        """Load staged TMDL with TOM, create measures through MCP, export canonical TMDL."""
        if not self.allow_write:
            raise BuildError("Offline model execution requires an adapter authorized for staged writes.")
        destination = folder.parent / "canonical-definition"
        async with self.session() as session:
            catalog = [t.model_dump(mode="json") for t in (await session.list_tools()).tools]
            results = [await self.call(session, catalog, "connection_operations", {"request": {"operation": "ConnectFolder", "folderPath": str(folder)}})]
            if measures:
                definitions = [{"tableName": m["table"], "name": m["name"], "expression": m["expression"],
                    "formatString": m.get("format", "#,##0.00"), "displayFolder": m.get("folder", "KPIs"), "description": m["reason"],
                    "lineageTag": str(uuid.uuid5(uuid.NAMESPACE_URL, m["table"] + "/measure/" + m["name"]))} for m in measures]
                results.append(await self.call(session, catalog, "measure_operations", {"request": {"operation": "Create", "definitions": definitions,
                    "options": {"continueOnError": False, "useTransaction": True}}}))
            results.append(await self.call(session, catalog, "database_operations", {"request": {"operation": "ExportToTmdlFolder", "tmdlFolderPath": str(destination)}}))
        if not (destination / "model.tmdl").is_file():
            raise BuildError("MCP export did not create model.tmdl; staged project was not published.")
        # Both locations are new directories inside the transaction stage, never user artifacts.
        if destination.resolve().parent != folder.resolve().parent:
            raise BuildError("Canonical model path is outside staging")
        shutil.rmtree(folder)
        destination.rename(folder)
        return {"check": "mcp_tmdl_execution", "status": "passed", "operations": len(results),
                "detail": "TOM loaded TMDL, MCP created measures and exported canonical definitions. DAX/M not executed."}

    async def verify_folder(self, folder):
        results = await self.operations([{"tool": "connection_operations", "arguments": {"request": {"operation": "ConnectFolder", "folderPath": str(folder)}}}])
        return {"check": "mcp_tmdl_parse", "status": "passed", "result": results}

    async def execute_dax(self, connection: dict, queries: list[str], expected_measures=None, refresh=False):
        endpoint = (str(connection.get("connectionString", "")) + str(connection.get("dataSource", ""))).lower()
        if refresh and any(host in endpoint for host in ("localhost", "127.0.0.1", "[::1]")):
            raise BuildError("Desktop XMLA refresh of M partitions did not complete reliably in live testing. Use Desktop's native Refresh, then verify without --refresh. XMLA refresh is reserved for configured non-Desktop servers.")
        async with self.session() as session:
            catalog = [t.model_dump(mode="json") for t in (await session.list_tools()).tools]
            await self.call(session, catalog, "connection_operations", {"request": connection})
            if expected_measures:
                metadata = await self.call(session, catalog, "measure_operations", {"request": {"operation": "Get",
                    "references": [{"name": m["name"], "tableName": m["table"]} for m in expected_measures]}})
                found = {}
                def collect(node):
                    if isinstance(node, dict):
                        lowered = {k.lower(): v for k, v in node.items()}
                        if isinstance(lowered.get("name"), str) and isinstance(lowered.get("expression"), str):
                            found[lowered["name"]] = lowered["expression"]
                        for key, value in node.items():
                            if key == "text" and isinstance(value, str):
                                try:
                                    collect(json.loads(value))
                                except json.JSONDecodeError:
                                    pass
                            else:
                                collect(value)
                    elif isinstance(node, list):
                        for value in node:
                            collect(value)
                collect(metadata)
                if any(found.get(m["name"], "").strip() != m["expression"].strip() for m in expected_measures):
                    raise BuildError("Connected model measures do not match the generated plan, or MCP metadata could not be interpreted. Open/refresh the correct PBIP before runtime verification.")
            if refresh:
                if not self.allow_write or not expected_measures:
                    raise BuildError("Refresh requires write authorization and verification of the expected model measures.")
                await self.call(session, catalog, "model_operations", {"request": {"operation": "RefreshWithXMLA", "refreshType": "Full"}})
            results = []
            for query in queries:
                await self.call(session, catalog, "dax_query_operations", {"request": {"operation": "Validate", "query": query, "timeoutSeconds": 30}})
                results.append(await self.call(session, catalog, "dax_query_operations", {"request": {"operation": "Execute", "query": query,
                    "maxRows": 100, "timeoutSeconds": 60, "getExecutionMetrics": True, "resultMode": "Inline"}}))
            return results
