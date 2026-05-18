import base64
import json
import os
import shutil
import socket
import struct
import subprocess
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse
from urllib.request import Request, urlopen

import pytest
import uvicorn

from dgentic import provider_runtime
from dgentic.database import reset_database_state
from dgentic.main import create_app
from dgentic.settings import get_settings

pytestmark = [
    pytest.mark.filterwarnings("ignore:websockets\\.legacy is deprecated:DeprecationWarning"),
    pytest.mark.filterwarnings(
        "ignore:websockets\\.server\\.WebSocketServerProtocol is deprecated:DeprecationWarning"
    ),
]
PROVIDER_ID = provider_runtime.EXTERNAL_OPENAI_COMPATIBLE_PROVIDER_ID


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _wait_for_http_json(url: str, *, timeout_seconds: float = 10.0) -> dict:
    deadline = time.monotonic() + timeout_seconds
    last_error: Exception | None = None
    while time.monotonic() < deadline:
        try:
            with urlopen(url, timeout=1.0) as response:
                return json.loads(response.read().decode("utf-8"))
        except Exception as exc:  # pragma: no cover - diagnostic path
            last_error = exc
            time.sleep(0.05)
    raise AssertionError(f"Timed out waiting for {url}: {last_error}")


def _http_json(
    method: str,
    url: str,
    *,
    payload: dict | None = None,
) -> tuple[int, dict]:
    body = None
    headers = {"Accept": "application/json"}
    if payload is not None:
        body = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"
    request = Request(url, data=body, headers=headers, method=method)
    with urlopen(request, timeout=5.0) as response:
        response_body = response.read().decode("utf-8")
        return response.status, json.loads(response_body) if response_body else {}


def _find_browser_executable() -> Path | None:
    configured = os.environ.get("DGENTIC_BROWSER_EXECUTABLE", "").strip()
    candidates = [
        configured,
        shutil.which("chrome"),
        shutil.which("chrome.exe"),
        shutil.which("msedge"),
        shutil.which("msedge.exe"),
        shutil.which("chromium"),
        shutil.which("chromium-browser"),
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    ]
    for candidate in candidates:
        if candidate:
            path = Path(candidate)
            if path.exists():
                return path
    return None


class _WebSocket:
    def __init__(self, url: str) -> None:
        parsed = urlparse(url)
        self._host = parsed.hostname or "127.0.0.1"
        self._port = parsed.port or 80
        self._path = parsed.path or "/"
        if parsed.query:
            self._path = f"{self._path}?{parsed.query}"
        self._socket = socket.create_connection((self._host, self._port), timeout=5)
        self._socket.settimeout(5)
        self._handshake()

    def close(self) -> None:
        try:
            self._socket.close()
        except OSError:
            pass

    def send_text(self, payload: str) -> None:
        body = payload.encode("utf-8")
        mask = os.urandom(4)
        header = bytearray([0x81])
        if len(body) <= 125:
            header.append(0x80 | len(body))
        elif len(body) <= 0xFFFF:
            header.append(0x80 | 126)
            header.extend(struct.pack("!H", len(body)))
        else:
            header.append(0x80 | 127)
            header.extend(struct.pack("!Q", len(body)))
        masked = bytes(byte ^ mask[index % 4] for index, byte in enumerate(body))
        self._socket.sendall(bytes(header) + mask + masked)

    def recv_text(self) -> str:
        chunks: list[bytes] = []
        while True:
            first, second = self._read_exact(2)
            fin = bool(first & 0x80)
            opcode = first & 0x0F
            masked = bool(second & 0x80)
            length = second & 0x7F
            if length == 126:
                length = struct.unpack("!H", self._read_exact(2))[0]
            elif length == 127:
                length = struct.unpack("!Q", self._read_exact(8))[0]
            mask = self._read_exact(4) if masked else b""
            payload = self._read_exact(length)
            if masked:
                payload = bytes(byte ^ mask[index % 4] for index, byte in enumerate(payload))
            if opcode == 0x8:
                raise AssertionError("Browser closed the DevTools websocket.")
            if opcode == 0x9:
                self._send_pong(payload)
                continue
            if opcode in {0x1, 0x2, 0x0}:
                chunks.append(payload)
                if fin:
                    return b"".join(chunks).decode("utf-8")

    def _handshake(self) -> None:
        key = base64.b64encode(os.urandom(16)).decode("ascii")
        request = (
            f"GET {self._path} HTTP/1.1\r\n"
            f"Host: {self._host}:{self._port}\r\n"
            "Upgrade: websocket\r\n"
            "Connection: Upgrade\r\n"
            f"Sec-WebSocket-Key: {key}\r\n"
            "Sec-WebSocket-Version: 13\r\n\r\n"
        )
        self._socket.sendall(request.encode("ascii"))
        response = b""
        while b"\r\n\r\n" not in response:
            chunk = self._socket.recv(4096)
            if not chunk:
                break
            response += chunk
        if b" 101 " not in response.split(b"\r\n", 1)[0]:
            raise AssertionError(f"DevTools websocket handshake failed: {response!r}")

    def _send_pong(self, payload: bytes) -> None:
        self._socket.sendall(bytes([0x8A, len(payload)]) + payload)

    def _read_exact(self, length: int) -> bytes:
        data = b""
        while len(data) < length:
            chunk = self._socket.recv(length - len(data))
            if not chunk:
                raise AssertionError("DevTools websocket closed unexpectedly.")
            data += chunk
        return data


class _DevToolsPage:
    def __init__(self, web_socket_url: str) -> None:
        self._ws = _WebSocket(web_socket_url)
        self._next_id = 0
        self.events: list[dict] = []

    def close(self) -> None:
        self._ws.close()

    def call(self, method: str, params: dict | None = None) -> dict:
        self._next_id += 1
        message_id = self._next_id
        self._ws.send_text(json.dumps({"id": message_id, "method": method, "params": params or {}}))
        while True:
            payload = json.loads(self._ws.recv_text())
            if payload.get("id") == message_id:
                if "error" in payload:
                    raise AssertionError(payload["error"])
                return payload.get("result", {})
            self.events.append(payload)

    def eval(self, expression: str):
        result = self.call(
            "Runtime.evaluate",
            {
                "expression": expression,
                "awaitPromise": True,
                "returnByValue": True,
                "userGesture": True,
            },
        )
        if "exceptionDetails" in result:
            raise AssertionError(result["exceptionDetails"])
        return result.get("result", {}).get("value")

    def wait_for(self, expression: str, *, timeout_seconds: float = 8.0):
        deadline = time.monotonic() + timeout_seconds
        last_value = None
        while time.monotonic() < deadline:
            last_value = self.eval(expression)
            if last_value:
                return last_value
            time.sleep(0.1)
        raise AssertionError(f"Timed out waiting for browser condition: {last_value!r}")


class _WebRetrievalSmokeHandler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        body = b"browser network approval smoke response"
        self.send_response(200)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, _format: str, *_args) -> None:
        return


def _write_browser_plugin_manifest(root_dir: Path, plugin_id: str, manifest: dict) -> None:
    plugin_dir = root_dir / "plugins" / plugin_id
    plugin_dir.mkdir(parents=True, exist_ok=True)
    (plugin_dir / "dgentic-plugin.json").write_text(
        json.dumps(manifest, indent=2) + "\n",
        encoding="utf-8",
    )


def _write_browser_plugin_component(
    root_dir: Path,
    plugin_id: str,
    relative_path: str,
    payload: dict,
) -> None:
    component_path = root_dir / "plugins" / plugin_id / relative_path
    component_path.parent.mkdir(parents=True, exist_ok=True)
    component_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


@pytest.fixture()
def ui_live_server(tmp_path, monkeypatch):
    root_dir = tmp_path / "workspace"
    root_dir.mkdir()
    monkeypatch.setenv("DGENTIC_ROOT_DIR", str(root_dir))
    monkeypatch.setenv("DGENTIC_DATA_DIR", str(tmp_path / "state"))
    monkeypatch.setenv("DGENTIC_ENVIRONMENT", "production")
    monkeypatch.setenv("DGENTIC_AUTH_ENABLED", "false")
    monkeypatch.setenv(
        "DGENTIC_EXTERNAL_OPENAI_COMPATIBLE_BASE_URL",
        "https://provider.example.test/v1",
    )
    monkeypatch.setenv("DGENTIC_EXTERNAL_OPENAI_COMPATIBLE_API_KEY_ENV", "BROWSER_PROVIDER_KEY")
    monkeypatch.setenv("DGENTIC_EXTERNAL_OPENAI_COMPATIBLE_MODELS", "gpt-browser")
    monkeypatch.setenv("BROWSER_PROVIDER_KEY", "browser-provider-key-secret")
    monkeypatch.setenv(
        "DGENTIC_NETWORK_DOMAIN_POLICY",
        json.dumps(
            {
                "rules": [
                    {
                        "domain": "127.0.0.1",
                        "mode": "approval_required",
                        "reason": "Browser network approval smoke.",
                    },
                    {
                        "domain": "provider.example.test",
                        "mode": "approval_required",
                        "reason": "Browser provider network approval smoke.",
                    },
                ]
            }
        ),
    )

    def fake_provider_post_json(
        _url: str,
        payload: dict,
        _timeout_seconds: float,
        *,
        headers: dict[str, str] | None = None,
    ) -> dict:
        assert headers and headers.get("Authorization") == "Bearer browser-provider-key-secret"
        return {
            "id": "chatcmpl-browser-provider-smoke",
            "model": payload.get("model", "gpt-browser"),
            "choices": [
                {
                    "index": 0,
                    "message": {
                        "role": "assistant",
                        "content": "Approved browser provider response.",
                    },
                    "finish_reason": "stop",
                }
            ],
        }

    monkeypatch.setattr(provider_runtime, "_post_json", fake_provider_post_json)
    provider_runtime.reset_provider_circuit_state()
    reset_database_state()
    get_settings.cache_clear()

    app = create_app()
    port = _free_port()
    server = uvicorn.Server(
        uvicorn.Config(
            app,
            host="127.0.0.1",
            port=port,
            log_level="warning",
            lifespan="off",
        )
    )
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    base_url = f"http://127.0.0.1:{port}"
    _wait_for_http_json(f"{base_url}/health")

    try:
        yield base_url, root_dir
    finally:
        server.should_exit = True
        thread.join(timeout=5)
        provider_runtime.reset_provider_circuit_state()
        reset_database_state()
        get_settings.cache_clear()


@pytest.fixture()
def web_retrieval_target_url():
    server = ThreadingHTTPServer(("127.0.0.1", _free_port()), _WebRetrievalSmokeHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_address[1]}/approved.txt"
    finally:
        server.shutdown()
        thread.join(timeout=5)
        server.server_close()


@pytest.fixture()
def socket_listener():
    listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    listener.bind(("127.0.0.1", 0))
    listener.listen(1)
    try:
        yield listener
    finally:
        listener.close()


@pytest.fixture()
def devtools_page(tmp_path):
    browser = _find_browser_executable()
    if browser is None:
        pytest.skip("Chromium-family browser not available for browser UI smoke test.")

    debug_port = _free_port()
    user_data_dir = tmp_path / "browser-profile"
    command = [
        str(browser),
        "--headless=new",
        "--disable-gpu",
        "--no-first-run",
        "--no-default-browser-check",
        f"--remote-debugging-port={debug_port}",
        f"--user-data-dir={user_data_dir}",
        "about:blank",
    ]
    process = subprocess.Popen(
        command,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
    try:
        targets = _wait_for_http_json(f"http://127.0.0.1:{debug_port}/json/list")
        page_target = next(
            (target for target in targets if target.get("type") == "page"),
            targets[0] if targets else None,
        )
        if page_target is None or not page_target.get("webSocketDebuggerUrl"):
            pytest.skip("Browser DevTools page target was not available.")
        page = _DevToolsPage(page_target["webSocketDebuggerUrl"])
        page.call("Page.enable")
        page.call("Runtime.enable")
        yield page
        page.close()
    finally:
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)


def test_browser_project_panel_can_edit_archive_and_restore_registered_project(
    ui_live_server,
    devtools_page,
) -> None:
    base_url, root_dir = ui_live_server
    project_dir = root_dir / "browser-project-alt"
    project_dir.mkdir()
    (project_dir / "README.md").write_text("# Browser project\n", encoding="utf-8")

    devtools_page.call("Page.navigate", {"url": f"{base_url}/ui/#project-context"})
    devtools_page.wait_for("document.readyState === 'complete'")
    devtools_page.wait_for("Boolean(document.querySelector('#projectForm'))")
    devtools_page.eval(
        f"""
        (() => {{
          document.querySelector("#projectNameInput").value = "Browser Project";
          document.querySelector("#projectRootInput").value = {json.dumps(str(project_dir))};
          document.querySelector("#projectForm").requestSubmit();
          return true;
        }})()
        """
    )
    devtools_page.wait_for(
        """
        [...document.querySelectorAll("#projectRegistryOutput .list-item")]
          .some((row) => row.textContent.includes("Browser Project"))
        """,
        timeout_seconds=10.0,
    )

    devtools_page.eval(
        """
        (() => {
          const row = [...document.querySelectorAll("#projectRegistryOutput .list-item")]
            .find((candidate) => candidate.textContent.includes("Browser Project"));
          row.querySelector('[data-testid="project-edit"]').click();
          return true;
        })()
        """
    )
    devtools_page.wait_for(
        """
        !document.querySelector("#projectEditPanel").hidden
          && document.querySelector("#projectEditNameInput")?.value === "Browser Project"
        """
    )
    devtools_page.eval(
        """
        (() => {
          document.querySelector("#projectEditNameInput").value = "Browser Project Renamed";
          document.querySelector("#projectEditStatusInput").value = "available";
          document.querySelector("#projectEditForm").requestSubmit();
          return true;
        })()
        """
    )
    devtools_page.wait_for(
        """
        document.querySelector("#projectEditOutput")?.textContent.includes("Project updated")
          && [...document.querySelectorAll("#projectRegistryOutput .list-item")]
            .some((row) => row.textContent.includes("Browser Project Renamed"))
        """,
        timeout_seconds=10.0,
    )
    list_status, list_body = _http_json("GET", f"{base_url}/projects")
    assert list_status == 200
    project = next(item for item in list_body if item["name"] == "Browser Project Renamed")
    assert project["status"] == "available"

    devtools_page.eval(
        """
        (() => {
          const row = [...document.querySelectorAll("#projectRegistryOutput .list-item")]
            .find((candidate) => candidate.textContent.includes("Browser Project Renamed"));
          row.querySelector('[data-testid="project-status-toggle"]').click();
          return true;
        })()
        """
    )
    devtools_page.wait_for(
        """
        [...document.querySelectorAll("#projectRegistryOutput .list-item")]
          .some((row) => row.textContent.includes("Browser Project Renamed")
            && row.textContent.includes("archived"))
        """,
        timeout_seconds=10.0,
    )
    archived_status, archived_body = _http_json("GET", f"{base_url}/projects")
    assert archived_status == 200
    archived_project = next(
        item for item in archived_body if item["name"] == "Browser Project Renamed"
    )
    assert archived_project["status"] == "archived"

    devtools_page.eval(
        """
        (() => {
          const row = [...document.querySelectorAll("#projectRegistryOutput .list-item")]
            .find((candidate) => candidate.textContent.includes("Browser Project Renamed"));
          row.querySelector('[data-testid="project-status-toggle"]').click();
          return true;
        })()
        """
    )
    devtools_page.wait_for(
        """
        [...document.querySelectorAll("#projectRegistryOutput .list-item")]
          .some((row) => row.textContent.includes("Browser Project Renamed")
            && row.textContent.includes("available"))
        """,
        timeout_seconds=10.0,
    )
    restored_status, restored_body = _http_json("GET", f"{base_url}/projects")
    assert restored_status == 200
    restored_project = next(
        item for item in restored_body if item["name"] == "Browser Project Renamed"
    )
    assert restored_project["status"] == "available"


def test_browser_workspace_editor_can_apply_and_revert_file_change(
    ui_live_server,
    devtools_page,
) -> None:
    base_url, root_dir = ui_live_server
    target = root_dir / "review-me.txt"
    target.write_text("alpha\n", encoding="utf-8")

    devtools_page.call("Page.navigate", {"url": f"{base_url}/ui/#workspace"})
    devtools_page.wait_for("document.readyState === 'complete'")
    devtools_page.wait_for(
        """
        [...document.querySelectorAll(".file-row")]
          .some((row) => row.textContent.includes("review-me.txt"))
        """
    )
    devtools_page.eval(
        """
        (() => {
          const row = [...document.querySelectorAll(".file-row")]
            .find((candidate) => candidate.textContent.includes("review-me.txt"));
          row.click();
          return true;
        })()
        """
    )
    devtools_page.wait_for(
        """
        document.querySelector("#workspaceEditorTitle")?.textContent.includes("review-me.txt")
          && document.querySelector("#workspaceEditor")?.value === "alpha\\n"
          && document.querySelector("#workspaceChangeReview")?.textContent
            .includes("No pending editor change")
        """
    )
    devtools_page.eval(
        """
        (() => {
          const editor = document.querySelector("#workspaceEditor");
          editor.value = "alpha\\nbeta\\n";
          editor.dispatchEvent(new Event("input", { bubbles: true }));
          return true;
        })()
        """
    )
    devtools_page.wait_for(
        """
        (() => {
          const review = document.querySelector("#workspaceChangeReview")?.textContent || "";
          return review.includes("Pending file change")
            && review.includes("Changed lines")
            && !document.querySelector("#workspaceApplyButton")?.disabled;
        })()
        """
    )
    devtools_page.eval('document.querySelector("#workspacePreviewButton").click()')
    devtools_page.wait_for(
        """
        document.querySelector("#toast")?.textContent.includes("Workspace change preview refreshed")
        """
    )
    devtools_page.eval('document.querySelector("#workspaceApplyButton").click()')
    devtools_page.wait_for(
        """
        document.querySelector("#workspaceStatus")?.textContent.includes("File change applied")
          && document.querySelector("#workspaceChangeReview")?.textContent
            .includes("No pending editor change")
          && document.querySelector("#workspaceChangeReview")?.textContent
            .includes("Revert available")
          && !document.querySelector("#workspaceRevertButton")?.disabled
        """
    )
    assert target.read_text(encoding="utf-8") == "alpha\nbeta\n"

    devtools_page.eval('document.querySelector("#workspaceRevertButton").click()')
    devtools_page.wait_for(
        """
        document.querySelector("#workspaceStatus")?.textContent.includes("File change reverted")
          && document.querySelector("#workspaceEditor")?.value === "alpha\\n"
          && document.querySelector("#workspaceRevertButton")?.disabled
        """
    )
    assert target.read_text(encoding="utf-8") == "alpha\n"


def test_browser_task_chat_can_plan_run_and_insert_execution_evidence(
    ui_live_server,
    devtools_page,
) -> None:
    base_url, _root_dir = ui_live_server

    devtools_page.call("Page.navigate", {"url": f"{base_url}/ui/#tasks"})
    devtools_page.wait_for("document.readyState === 'complete'")
    devtools_page.wait_for("Boolean(document.querySelector('#taskChatForm'))")
    devtools_page.eval(
        """
        (() => {
          document.querySelector("#taskChatInput").value =
            "Plan and run browser task-chat execution evidence.";
          document.querySelector("#taskChatContextInput").value =
            "Use existing task contracts only.";
          document.querySelector("#taskChatAcceptanceInput").value =
            "Transcript shows execution status.";
          document.querySelector("#taskChatRunInput").checked = true;
          document.querySelector("#taskChatSubmitButton").click();
          return true;
        })()
        """
    )
    devtools_page.wait_for(
        """
        (() => {
          const transcript = document.querySelector("#taskChatTranscript")?.textContent || "";
          const execution = document.querySelector(".task-chat-execution-card")?.textContent || "";
          return transcript.includes("Plan created")
            && transcript.includes("Task plan executed")
            && execution.includes("Execution Summary")
            && execution.includes("5 completed")
            && execution.includes("step-1")
            && Boolean(document.querySelector('[data-testid="task-chat-execution-use-evidence"]'));
        })()
        """
    )
    devtools_page.wait_for(
        """
        (() => {
          const context = document.querySelector("#taskChatContextStream")?.textContent || "";
          return document.querySelector("#plansMetric")?.textContent === "1"
            && document.querySelector("#runsMetric")?.textContent === "Runs: 1"
            && context.includes("1 plans / 1 runs");
        })()
        """
    )

    runs_status, runs_body = _http_json("GET", f"{base_url}/tasks/runs")
    assert runs_status == 200
    assert len(runs_body) == 1
    assert runs_body[0]["status"] == "completed"
    assert len(runs_body[0]["results"]) == 5
    assert all(result["status"] == "completed" for result in runs_body[0]["results"])

    devtools_page.eval(
        'document.querySelector("[data-testid=\\"task-chat-execution-use-evidence\\"]").click()'
    )
    devtools_page.wait_for(
        """
        (() => {
          const value = document.querySelector("#taskChatContextInput")?.value || "";
          return value.includes("Run ID:")
            && value.includes("Plan ID:")
            && value.includes("Status: completed")
            && value.includes("step-1:completed");
        })()
        """
    )


def test_browser_task_chat_can_create_orchestration_from_fresh_plan(
    ui_live_server,
    devtools_page,
) -> None:
    base_url, _root_dir = ui_live_server

    devtools_page.call("Page.navigate", {"url": f"{base_url}/ui/#tasks"})
    devtools_page.wait_for("document.readyState === 'complete'")
    devtools_page.wait_for("Boolean(document.querySelector('#taskChatForm'))")
    devtools_page.eval(
        """
        (() => {
          document.querySelector("#taskChatInput").value =
            "Create a browser task-chat orchestration handoff.";
          document.querySelector("#taskChatContextInput").value =
            "Keep orchestration execution explicit.";
          document.querySelector("#taskChatAcceptanceInput").value =
            "Chat creates an orchestration run.";
          document.querySelector("#taskChatRunInput").checked = false;
          document.querySelector("#taskChatSubmitButton").click();
          return true;
        })()
        """
    )
    devtools_page.wait_for(
        """
        (() => {
          const transcript = document.querySelector("#taskChatTranscript")?.textContent || "";
          return transcript.includes("Plan created")
            && Boolean(document.querySelector('[data-testid="task-plan-create-orchestration"]'));
        })()
        """
    )
    devtools_page.eval(
        'document.querySelector("[data-testid=\\"task-plan-create-orchestration\\"]").click()'
    )
    devtools_page.wait_for(
        """
        (() => {
          const transcript = document.querySelector("#taskChatTranscript")?.textContent || "";
          const orchestration =
            document.querySelector(".task-chat-orchestration-card")?.textContent || "";
          const detail = document.querySelector("#orchestrationDetail")?.textContent || "";
          const useContext = Boolean(
            document.querySelector('[data-testid="task-chat-orchestration-use-context"]')
          );
          return transcript.includes("Orchestration created")
            && orchestration.includes("Orchestration Run")
            && orchestration.includes("5 tasks")
            && detail.includes("Task Graph")
            && useContext;
        })()
        """
    )
    devtools_page.wait_for(
        """
        (() => {
          const context = document.querySelector("#taskChatContextStream")?.textContent || "";
          return context.includes("Orchestrations") && context.includes("1");
        })()
        """
    )

    runs_status, runs_body = _http_json("GET", f"{base_url}/tasks/orchestrations")
    assert runs_status == 200
    assert len(runs_body) == 1
    assert runs_body[0]["objective"] == "Create a browser task-chat orchestration handoff."
    assert len(runs_body[0]["tasks"]) == 5
    assert runs_body[0]["required_dod_evidence"] == ["tests", "docs", "review"]

    executions_status, executions_body = _http_json(
        "GET",
        f"{base_url}/tasks/orchestrations/{runs_body[0]['id']}/executions",
    )
    assert executions_status == 200
    assert executions_body == []

    devtools_page.eval(
        'document.querySelector("[data-testid=\\"task-chat-orchestration-use-context\\"]").click()'
    )
    devtools_page.wait_for(
        """
        (() => {
          const value = document.querySelector("#taskChatContextInput")?.value || "";
          return value.includes("Orchestration ID:")
            && value.includes("Objective: Create a browser task-chat orchestration handoff.")
            && value.includes("Status: running")
            && value.includes("Tasks: 5 tasks")
            && value.includes("Evidence: tests, docs, review");
        })()
        """
    )


def test_browser_task_chat_provider_reply_builds_payload_streams_and_inserts_context(
    ui_live_server,
    devtools_page,
) -> None:
    base_url, _root_dir = ui_live_server
    long_reply = "Task chat provider reply " + ("x" * 950) + " tail-marker"

    devtools_page.call("Page.navigate", {"url": f"{base_url}/ui/#tasks"})
    devtools_page.wait_for("document.readyState === 'complete'")
    devtools_page.wait_for("Boolean(document.querySelector('#taskChatProviderButton'))")
    unsupported_state = devtools_page.eval(
        """
        (() => {
          populateProviderApprovalControls({
            ok: true,
            data: [
              {
                id: "chat-provider",
                name: "Task Chat Provider",
                kind: "external",
                enabled: true,
                permission_mode: "approval_required",
                model_names: ["chat-model"],
                supports_streaming: true,
              },
              {
                id: "offline-provider",
                name: "Offline Provider",
                kind: "external",
                enabled: true,
                permission_mode: "approval_required",
                model_names: ["offline-model"],
                supports_streaming: false,
              },
            ],
          });
          const providerInput = document.querySelector("#taskChatProviderInput");
          const streamInput = document.querySelector("#taskChatProviderStreamInput");
          providerInput.value = "offline-provider";
          streamInput.checked = true;
          providerInput.dispatchEvent(new Event("change", { bubbles: true }));
          return {
            checked: streamInput.checked,
            disabled: streamInput.disabled,
            model: document.querySelector("#taskChatProviderModelInput").value,
          };
        })()
        """
    )
    assert unsupported_state == {
        "checked": False,
        "disabled": True,
        "model": "offline-model",
    }

    devtools_page.eval(
        f"""
        (() => {{
          const originalFetch = window.fetch.bind(window);
          window.__taskChatProviderRequests = [];
          window.__taskChatProviderStreamRequests = [];
          window.fetch = async (input, init = {{}}) => {{
            const url = typeof input === "string" ? input : input.url;
            if (url.endsWith("/providers/generate/stream")) {{
              window.__taskChatProviderStreamRequests.push(JSON.parse(init.body));
              const encoder = new TextEncoder();
              const lines = [
                JSON.stringify({{
                  provider_id: "chat-provider",
                  model: "chat-model",
                  event: "chunk",
                  delta: "Streamed task ",
                }}) + "\\n",
                JSON.stringify({{
                  provider_id: "chat-provider",
                  model: "chat-model",
                  event: "chunk",
                  delta: "chat reply.",
                  finish_reason: "stop",
                  duration_ms: 77,
                }}) + "\\n",
              ];
              return new Response(
                new ReadableStream({{
                  start(controller) {{
                    for (const line of lines) {{
                      controller.enqueue(encoder.encode(line));
                    }}
                    controller.close();
                  }},
                }}),
                {{ status: 200, headers: {{ "Content-Type": "application/x-ndjson" }} }},
              );
            }}
            if (url.endsWith("/providers/generate")) {{
              window.__taskChatProviderRequests.push(JSON.parse(init.body));
              return new Response(
                JSON.stringify({{
                  provider_id: "chat-provider",
                  model: "chat-model",
                  content: {json.dumps(long_reply)},
                  duration_ms: 42,
                  usage_metadata: {{ total_tokens: 12 }},
                  finish_reasons: ["stop"],
                }}),
                {{ status: 200, headers: {{ "Content-Type": "application/json" }} }},
              );
            }}
            return originalFetch(input, init);
          }};
          return true;
        }})()
        """
    )
    devtools_page.eval(
        """
        (() => {
          const providerInput = document.querySelector("#taskChatProviderInput");
          providerInput.value = "chat-provider";
          providerInput.dispatchEvent(new Event("change", { bubbles: true }));
          document.querySelector("#taskChatProviderModelInput").value = "chat-model";
          document.querySelector("#taskChatProviderApprovalInput").value = "provider-approval-chat";
          document.querySelector("#taskChatProviderNetworkApprovalInput").value =
            "network-approval-chat";
          document.querySelector("#taskChatProviderStreamInput").checked = false;
          document.querySelector("#taskChatInput").value = "Explain the task chat provider UI.";
          document.querySelector("#taskChatContextInput").value =
            "Context line one\\nContext line two";
          document.querySelector("#taskChatAcceptanceInput").value = "Reply can be reused";
          document.querySelector("#taskChatProviderButton").click();
          return true;
        })()
        """
    )
    devtools_page.wait_for(
        """
        (() => {
          const card = document.querySelector(".task-chat-execution-card")?.textContent || "";
          return card.includes("Provider Reply")
            && card.includes("Task chat provider reply")
            && Boolean(document.querySelector('[data-testid="task-chat-provider-use-response"]'));
        })()
        """,
        timeout_seconds=10.0,
    )
    payload = devtools_page.eval("window.__taskChatProviderRequests[0]")
    assert payload["provider_id"] == "chat-provider"
    assert payload["model"] == "chat-model"
    assert payload["stream"] is False
    assert payload["requested_by"] == "dashboard-task-chat"
    assert payload["timeout_seconds"] == 60
    assert payload["approval_id"] == "provider-approval-chat"
    assert payload["network_approval_id"] == "network-approval-chat"
    prompt = payload["messages"][0]["content"]
    assert payload["messages"][0]["role"] == "user"
    assert "Message: Explain the task chat provider UI." in prompt
    assert "Context line one" in prompt
    assert "Context line two" in prompt
    assert "Acceptance:" in prompt
    assert "Reply can be reused" in prompt

    devtools_page.eval(
        """
        document.querySelector('[data-testid="task-chat-provider-use-response"]').click()
        """
    )
    context_value = devtools_page.wait_for(
        """
        (() => {
          const value = document.querySelector("#taskChatContextInput")?.value || "";
          return value.includes("Provider reply")
            && value.includes("Content: Task chat provider reply")
            && !value.includes("tail-marker")
            && value;
        })()
        """
    )
    assert len(context_value) < len(long_reply) + 300

    devtools_page.eval(
        """
        (() => {
          document.querySelector("#taskChatInput").value = "Stream a provider answer.";
          document.querySelector("#taskChatContextInput").value = "Streaming context line";
          document.querySelector("#taskChatAcceptanceInput").value = "Stream card appears";
          document.querySelector("#taskChatProviderStreamInput").checked = true;
          document.querySelector("#taskChatProviderButton").click();
          return true;
        })()
        """
    )
    devtools_page.wait_for(
        """
        [...document.querySelectorAll(".task-chat-execution-card")]
          .some((card) => card.textContent.includes("Provider Stream")
            && card.textContent.includes("Streamed task chat reply."))
        """,
        timeout_seconds=10.0,
    )
    stream_payload = devtools_page.eval("window.__taskChatProviderStreamRequests[0]")
    assert stream_payload["provider_id"] == "chat-provider"
    assert stream_payload["model"] == "chat-model"
    assert stream_payload["stream"] is True
    assert stream_payload["messages"][0]["content"].startswith("Message: Stream a provider answer.")
    assert "Streaming context line" in stream_payload["messages"][0]["content"]
    assert "Stream card appears" in stream_payload["messages"][0]["content"]


def test_browser_memory_lifecycle_controls_preview_and_apply_seeded_memory(
    ui_live_server,
    devtools_page,
) -> None:
    base_url, _root_dir = ui_live_server
    create_status, create_body = _http_json(
        "POST",
        f"{base_url}/api/v1/memory/metadata",
        payload={
            "entity_type": "memory",
            "entity_id": "browser-lifecycle-expired-memory",
            "tags": ["ui-lifecycle-smoke"],
            "category": "ui-lifecycle-smoke",
            "description": "Browser lifecycle smoke candidate.",
            "relevance_score": 0.1,
            "expires_at": "2020-01-01T00:00:00+00:00",
        },
    )
    assert create_status == 201

    devtools_page.call("Page.navigate", {"url": f"{base_url}/ui/#reliability"})
    devtools_page.wait_for("document.readyState === 'complete'")
    devtools_page.wait_for("Boolean(document.querySelector('#memoryLifecyclePreviewForm'))")
    devtools_page.wait_for(
        """
        document.querySelector("#memoryReliabilityList")?.textContent
          .includes("browser-lifecycle-expired-memory")
        """
    )
    devtools_page.eval(
        """
        (() => {
          document.querySelector("#memoryLifecyclePreviewPanel").open = true;
          const values = {
            memoryLifecycleCategoryInput: "ui-lifecycle-smoke",
            memoryLifecycleLimitInput: "5",
            memoryLifecycleArchiveDaysInput: "3650",
            memoryLifecycleSoftPruneDaysInput: "3650",
            memoryLifecycleArchiveRelevanceInput: "0",
            memoryLifecycleSoftPruneRelevanceInput: "0",
            memoryLifecyclePromoteRelevanceInput: "1",
            memoryLifecyclePromoteAccessInput: "1000000",
            memoryLifecycleCompressDaysInput: "3650",
            memoryLifecycleCompressAccessInput: "1000000",
          };
          for (const [id, value] of Object.entries(values)) {
            const input = document.querySelector(`#${id}`);
            input.value = value;
            input.dispatchEvent(new Event("input", { bubbles: true }));
          }
          document.querySelector("#memoryLifecyclePreviewForm").requestSubmit();
          return true;
        })()
        """
    )
    devtools_page.wait_for(
        """
        (() => {
          const output = document.querySelector("#memoryLifecyclePreviewOutput")?.textContent || "";
          return output.includes("Lifecycle preview")
            && output.includes("browser-lifecycle-expired-memory")
            && output.includes("soft_prune");
        })()
        """
    )
    devtools_page.eval(
        """
        (() => {
          window.__memoryLifecycleConfirmCalls = 0;
          window.__memoryLifecycleConfirmMessage = "";
          window.confirm = (message) => {
            window.__memoryLifecycleConfirmCalls += 1;
            window.__memoryLifecycleConfirmMessage = message;
            return true;
          };
          document.querySelector("#memoryLifecycleApplyButton").click();
          return true;
        })()
        """
    )
    devtools_page.wait_for(
        """
        (() => {
          const output = document.querySelector("#memoryLifecyclePreviewOutput")?.textContent || "";
          return window.__memoryLifecycleConfirmCalls === 1
            && window.__memoryLifecycleConfirmMessage
              === "Apply memory lifecycle changes for the current filters?"
            && output.includes("Lifecycle applied")
            && output.includes("browser-lifecycle-expired-memory")
            && output.includes("soft_prune")
            && document.querySelector("#toast")?.textContent
              .includes("Memory lifecycle apply complete");
        })()
        """,
        timeout_seconds=10.0,
    )

    detail_status, detail_body = _http_json(
        "GET",
        f"{base_url}/api/v1/memory/metadata/{create_body['id']}",
    )
    assert detail_status == 200
    assert detail_body["lifecycle_state"] == "soft_pruned"
    assert detail_body["lifecycle_reason"] == "Memory is expired and eligible for soft pruning."


def test_browser_memory_metadata_detail_can_patch_editable_fields(
    ui_live_server,
    devtools_page,
) -> None:
    base_url, _root_dir = ui_live_server
    create_status, create_body = _http_json(
        "POST",
        f"{base_url}/api/v1/memory/metadata",
        payload={
            "entity_type": "memory",
            "entity_id": "browser-memory-edit",
            "tags": ["before-edit"],
            "category": "ui-memory-edit",
            "description": "Editable memory before browser smoke.",
            "relevance_score": 0.25,
            "retention_policy": "automatic",
        },
    )
    assert create_status == 201

    devtools_page.call("Page.navigate", {"url": f"{base_url}/ui/#reliability"})
    devtools_page.wait_for("document.readyState === 'complete'")
    devtools_page.wait_for(
        """
        document.querySelector("#memoryReliabilityList")?.textContent
          .includes("browser-memory-edit")
        """
    )
    devtools_page.eval(
        """
        (() => {
          const row = [...document.querySelectorAll("#memoryReliabilityList .list-item")]
            .find((candidate) => candidate.textContent.includes("browser-memory-edit"));
          row.querySelector('[data-testid="memory-reliability-detail"]').click();
          return true;
        })()
        """
    )
    devtools_page.wait_for(
        """
        document.querySelector("#memoryReliabilityDetail")?.textContent.includes("Memory detail")
          && Boolean(document.querySelector("#memoryMetadataTagsInput"))
        """
    )
    devtools_page.eval(
        """
        (() => {
          document.querySelector(".memory-metadata-editor").open = true;
          const values = {
            memoryMetadataTagsInput: "after-edit, browser",
            memoryMetadataCategoryInput: "ui-memory-edited",
            memoryMetadataDescriptionInput: "Editable memory after browser smoke.",
            memoryMetadataRelevanceInput: "0.85",
            memoryMetadataRetentionInput: "manual",
          };
          for (const [id, value] of Object.entries(values)) {
            const input = document.querySelector(`#${id}`);
            input.value = value;
            input.dispatchEvent(new Event("input", { bubbles: true }));
          }
          document.querySelector(".memory-metadata-editor form").requestSubmit();
          return true;
        })()
        """
    )
    devtools_page.wait_for(
        """
        document.querySelector("#toast")?.textContent.includes("Memory metadata updated.")
          && document.querySelector("#memoryReliabilityDetail")?.textContent
            .includes("ui-memory-edited")
        """,
        timeout_seconds=10.0,
    )

    detail_status, detail_body = _http_json(
        "GET",
        f"{base_url}/api/v1/memory/metadata/{create_body['id']}",
    )
    assert detail_status == 200
    assert detail_body["tags"] == ["after-edit", "browser"]
    assert detail_body["category"] == "ui-memory-edited"
    assert detail_body["description"] == "Editable memory after browser smoke."
    assert detail_body["relevance_score"] == 0.85
    assert detail_body["retention_policy"] == "manual"


def test_browser_memory_metadata_detail_keeps_orchestration_context_read_only(
    ui_live_server,
    devtools_page,
) -> None:
    base_url, _root_dir = ui_live_server
    create_status, create_body = _http_json(
        "POST",
        f"{base_url}/tasks/orchestrations",
        payload={
            "objective": "Publish browser shared-memory context.",
            "shared_memory_tags": ["browser-readonly"],
            "tasks": [
                {
                    "id": "browser-memory-producer",
                    "title": "Browser memory producer",
                    "description": "Produce shared memory for read-only UI coverage.",
                    "role": "QA",
                    "declared_write_paths": ["tests/test_ui_browser.py"],
                    "validation": "Shared memory is published.",
                }
            ],
        },
    )
    assert create_status == 201
    complete_status, _complete_body = _http_json(
        "PATCH",
        f"{base_url}/tasks/orchestrations/{create_body['id']}/tasks/browser-memory-producer",
        payload={"status": "completed", "output": {"summary": "Browser read-only context."}},
    )
    assert complete_status == 200
    list_status, list_body = _http_json(
        "GET",
        f"{base_url}/api/v1/memory/metadata?category=orchestration_context&tags=browser-readonly",
    )
    assert list_status == 200
    assert list_body["total"] == 1
    metadata_id = list_body["items"][0]["id"]

    devtools_page.call("Page.navigate", {"url": f"{base_url}/ui/#reliability"})
    devtools_page.wait_for("document.readyState === 'complete'")
    devtools_page.wait_for(
        """
        document.querySelector("#memoryReliabilityList")?.textContent
          .includes("orchestration_context")
        """
    )
    devtools_page.eval(
        """
        (() => {
          const row = [...document.querySelectorAll("#memoryReliabilityList .list-item")]
            .find((candidate) => candidate.textContent.includes("orchestration_context"));
          row.querySelector('[data-testid="memory-reliability-detail"]').click();
          return true;
        })()
        """
    )
    devtools_page.wait_for(
        """
        (() => {
          const detail = document.querySelector("#memoryReliabilityDetail");
          const text = detail?.textContent || "";
          return text.includes("Memory detail")
            && text.includes("orchestration_context")
            && text.includes("Memory metadata read-only")
            && text.includes("Orchestration shared-memory metadata is service-authored.")
            && !detail.querySelector("#memoryMetadataTagsInput")
            && !detail.querySelector("#memoryMetadataCategoryInput")
            && !detail.querySelector('[data-testid="memory-metadata-save"]');
        })()
        """
    )

    detail_status, detail_body = _http_json(
        "GET",
        f"{base_url}/api/v1/memory/metadata/{metadata_id}",
    )
    assert detail_status == 200
    assert detail_body["category"] == "orchestration_context"
    assert "browser-memory-producer" in detail_body["description"]
    assert "[REDACTED]" in detail_body["description"]


def test_browser_git_diff_review_filters_and_bulk_visible_decisions(
    ui_live_server,
    devtools_page,
) -> None:
    base_url, _root_dir = ui_live_server

    devtools_page.call("Page.navigate", {"url": f"{base_url}/ui/#git"})
    devtools_page.wait_for("document.readyState === 'complete'")
    devtools_page.wait_for("Boolean(document.querySelector('#gitOutput'))")
    devtools_page.eval(
        r"""
        (() => {
          const output = document.querySelector("#gitOutput");
          output.replaceChildren();
          const target = document.createElement("div");
          target.id = "gitDiffReviewOutput";
          target.className = "git-diff-review-output";
          output.append(target);
          latestGitCheckpoint = {
            action: "commit",
            ready: true,
            checkpoint_digest: "browser-checkpoint-digest",
          };
          latestGitCheckpointRequest = { cwd: ".", test_evidence: ["browser"] };
          latestGitChangeReviewArtifacts = [];
          gitDiffReviewDecisions = {};
          gitDiffReviewDecisionFilter = "all";
          latestGitDiffReview = {
            action: "commit",
            branch: "main",
            head_sha: "1234567890abcdef",
            checkpoint_digest: "browser-checkpoint-digest",
            warnings: [],
            sections: [
              {
                scope: "staged",
                patch_digest: "digest-staged",
                byte_count: 120,
                returned_byte_count: 120,
                patch: "diff --git a/a.txt b/a.txt\n@@ -1 +1 @@\n-alpha\n+beta\n",
              },
              {
                scope: "unstaged",
                patch_digest: "digest-unstaged",
                byte_count: 140,
                returned_byte_count: 140,
                patch: "diff --git a/b.txt b/b.txt\n@@ -1 +1 @@\n-old\n+new\n",
              },
            ],
          };
          renderGitDiffReview(target, latestGitDiffReview);
          return true;
        })()
        """
    )
    devtools_page.wait_for(
        """
        gitDiffReviewDecisionCounts(latestGitDiffReview).pending === 2
          && document.querySelectorAll(".git-diff-section").length === 2
          && !document.querySelector("#gitApprovalSubmitButton").disabled
        """
    )
    devtools_page.eval('document.querySelector(".git-diff-section .danger-button").click()')
    devtools_page.wait_for(
        """
        gitDiffReviewDecisionCounts(latestGitDiffReview).rejected === 1
          && document.querySelector("#gitApprovalSubmitButton").disabled
        """
    )
    devtools_page.eval(
        'document.querySelector("[data-testid=\\"git-diff-filter-rejected\\"]").click()'
    )
    devtools_page.wait_for(
        """
        gitDiffReviewDecisionFilter === "rejected"
          && document.querySelectorAll(".git-diff-section").length === 1
        """
    )
    devtools_page.eval(
        'document.querySelector("[data-testid=\\"git-diff-clear-visible\\"]").click()'
    )
    devtools_page.wait_for(
        """
        gitDiffReviewDecisionCounts(latestGitDiffReview).rejected === 0
          && gitDiffReviewDecisionCounts(latestGitDiffReview).pending === 2
          && document.querySelector("#gitDiffReviewOutput")?.textContent
            .includes("No visible diff sections")
          && !document.querySelector("#gitApprovalSubmitButton").disabled
        """
    )
    devtools_page.eval('document.querySelector("[data-testid=\\"git-diff-filter-all\\"]").click()')
    devtools_page.eval(
        'document.querySelector("[data-testid=\\"git-diff-accept-visible\\"]").click()'
    )
    devtools_page.wait_for(
        """
        gitDiffReviewDecisionCounts(latestGitDiffReview).accepted === 2
          && gitDiffReviewDecisionCounts(latestGitDiffReview).pending === 0
          && document.querySelectorAll(".git-diff-section").length === 2
          && document.querySelector("#toast")?.textContent
            .includes("2 visible diff section(s) updated.")
        """
    )


def test_browser_approval_dashboard_can_review_and_approve_seeded_cli_approval(
    ui_live_server,
    devtools_page,
) -> None:
    base_url, _root_dir = ui_live_server
    create_status, create_body = _http_json(
        "POST",
        f"{base_url}/cli/approvals?requested_by=browser-seed",
        payload={"command": "python --version", "timeout_seconds": 10},
    )
    assert create_status == 201

    devtools_page.call("Page.navigate", {"url": f"{base_url}/ui/#approvals"})
    devtools_page.wait_for("document.readyState === 'complete'")
    devtools_page.wait_for("Boolean(document.querySelector('#approvalSourceInput'))")
    devtools_page.eval(
        """
        (() => {
          const input = document.querySelector("#approvalSourceInput");
          input.value = "cli";
          input.dispatchEvent(new Event("change", { bubbles: true }));
          return true;
        })()
        """
    )
    devtools_page.wait_for(
        """
        [...document.querySelectorAll(".approval-item")]
          .some((row) => row.textContent.includes("python --version"))
        """
    )
    devtools_page.eval(
        """
        (() => {
          const row = [...document.querySelectorAll(".approval-item")]
            .find((candidate) => candidate.textContent.includes("python --version"));
          row.querySelector("button").click();
          return true;
        })()
        """
    )
    devtools_page.wait_for(
        """
        document.querySelector("#approvalReview")?.textContent.includes("CLI review")
          && document.querySelector("#approvalReview")?.textContent.includes("Review Summary")
          && document.querySelector("#approvalReview")?.textContent.includes("pending")
        """
    )
    devtools_page.eval(
        """
        (() => {
          const review = document.querySelector("#approvalReview");
          review.querySelector(".decision-form input").value = "Browser approval smoke.";
          review.querySelector('button[data-decision="approve"]').click();
          return true;
        })()
        """
    )
    devtools_page.wait_for(
        """
        document.querySelector("#approvalReview")?.textContent.includes("approved")
          && Boolean([...document.querySelectorAll("#approvalReview button")]
            .find((button) => button.textContent.includes("Execute approved command")
              && !button.disabled))
        """
    )

    review_status, review_body = _http_json(
        "GET",
        f"{base_url}/cli/approvals/{create_body['id']}/review",
    )
    assert review_status == 200
    assert review_body["status"] == "approved"
    assert review_body["decision_reason"] == "Browser approval smoke."


def test_browser_task_chat_approval_context_opens_exact_review(
    ui_live_server,
    devtools_page,
) -> None:
    base_url, _root_dir = ui_live_server
    create_status, create_body = _http_json(
        "POST",
        f"{base_url}/cli/approvals?requested_by=task-chat-seed",
        payload={"command": "python --version", "timeout_seconds": 10},
    )
    assert create_status == 201

    devtools_page.call("Page.navigate", {"url": f"{base_url}/ui/#tasks"})
    devtools_page.wait_for("document.readyState === 'complete'")
    devtools_page.wait_for("Boolean(document.querySelector('#taskChatContextStream'))")
    devtools_page.wait_for(
        f"""
        document.querySelector("#taskChatContextStream")
          ?.textContent.includes("{create_body["id"]}")
          && document.querySelector("#taskChatContextStream")
            ?.textContent.includes("python --version")
        """
    )
    devtools_page.eval(
        f"""
        (() => {{
          const button = [...document.querySelectorAll('[data-testid="task-chat-approval-review"]')]
            .find((candidate) => candidate.dataset.approvalId === "{create_body["id"]}");
          button.click();
          return true;
        }})()
        """
    )
    devtools_page.wait_for(
        f"""
        window.location.hash === "#approvals"
          && document.querySelector("#approvalSourceInput")?.value === "cli"
          && document.querySelector('#approvalReview')
            ?.textContent.includes("{create_body["id"]}")
          && document.querySelector("#approvalReview")?.textContent.includes("CLI review")
          && document.querySelector("#approvalReview")?.textContent.includes("python --version")
          && document.querySelector("#approvalReview")?.textContent.includes("pending")
        """
    )


def test_browser_approval_dashboard_can_execute_seeded_filesystem_delete_approval(
    ui_live_server,
    devtools_page,
) -> None:
    base_url, root_dir = ui_live_server
    target = root_dir / "delete-me.txt"
    target.write_text("remove", encoding="utf-8")
    create_status, create_body = _http_json(
        "POST",
        f"{base_url}/filesystem/approvals",
        payload={"path": "delete-me.txt", "action": "delete"},
    )
    assert create_status == 201

    devtools_page.call("Page.navigate", {"url": f"{base_url}/ui/#approvals"})
    devtools_page.wait_for("document.readyState === 'complete'")
    devtools_page.wait_for("Boolean(document.querySelector('#approvalSourceInput'))")
    devtools_page.eval(
        """
        (() => {
          const input = document.querySelector("#approvalSourceInput");
          input.value = "filesystem";
          input.dispatchEvent(new Event("change", { bubbles: true }));
          return true;
        })()
        """
    )
    devtools_page.wait_for(
        """
        [...document.querySelectorAll(".approval-item")]
          .some((row) => row.textContent.includes("delete-me.txt"))
        """
    )
    devtools_page.eval(
        """
        (() => {
          const row = [...document.querySelectorAll(".approval-item")]
            .find((candidate) => candidate.textContent.includes("delete-me.txt"));
          row.querySelector("button").click();
          return true;
        })()
        """
    )
    devtools_page.wait_for(
        """
        document.querySelector("#approvalReview")?.textContent.includes("Filesystem review")
          && document.querySelector("#approvalReview")?.textContent.includes("pending")
        """
    )
    devtools_page.eval(
        """
        (() => {
          const review = document.querySelector("#approvalReview");
          review.querySelector(".decision-form input").value = "Browser filesystem smoke.";
          review.querySelector('button[data-decision="approve"]').click();
          return true;
        })()
        """
    )
    devtools_page.wait_for(
        """
        document.querySelector("#approvalReview")?.textContent.includes("approved")
          && Boolean(document.querySelector("#boundExecutionExecuteButton:not([disabled])"))
          && document.querySelector("#boundExecutionPayloadInput")?.value.includes('"approval_id"')
          && document.querySelector("#boundExecutionPayloadInput")
            ?.value.includes('"delete-me.txt"')
        """
    )
    devtools_page.eval('document.querySelector("#boundExecutionExecuteButton").click()')
    devtools_page.wait_for(
        """
        document.querySelector("#boundExecutionOutput")
          ?.textContent.includes("Bound request executed")
        """
    )

    review_status, review_body = _http_json(
        "GET",
        f"{base_url}/filesystem/approvals/{create_body['id']}/review",
    )
    assert review_status == 200
    assert review_body["status"] == "executed"
    assert not target.exists()


def test_browser_policy_panel_can_preflight_filesystem_guardrail(
    ui_live_server,
    devtools_page,
) -> None:
    base_url, _root_dir = ui_live_server

    devtools_page.call("Page.navigate", {"url": f"{base_url}/ui/#policy"})
    devtools_page.wait_for("document.readyState === 'complete'")
    devtools_page.wait_for("Boolean(document.querySelector('#filesystemPolicyCheckForm'))")
    devtools_page.eval(
        """
        (() => {
          document.querySelector("#filesystemPolicyCheckPanel").open = true;
          document.querySelector("#filesystemPolicyActionInput").value = "list";
          document.querySelector("#filesystemPolicyPathInput").value = ".";
          document.querySelector("#filesystemPolicyCheckForm")
            .dispatchEvent(new Event("submit", { bubbles: true, cancelable: true }));
          return true;
        })()
        """
    )
    devtools_page.wait_for(
        """
        document.querySelector("#filesystemPolicyCheckOutput")
          ?.textContent.includes("Filesystem guardrail decision")
          && document.querySelector("#filesystemPolicyCheckOutput")
            ?.textContent.includes("autopilot_safe")
        """
    )


def test_browser_policy_panel_can_create_and_toggle_network_rule(
    ui_live_server,
    devtools_page,
) -> None:
    base_url, _root_dir = ui_live_server

    devtools_page.call("Page.navigate", {"url": f"{base_url}/ui/#policy"})
    devtools_page.wait_for("document.readyState === 'complete'")
    devtools_page.wait_for("Boolean(document.querySelector('#networkDomainPolicyForm'))")
    devtools_page.eval(
        """
        (() => {
          document.querySelector("#networkDomainPolicyEditor").open = true;
          document.querySelector("#networkDomainPolicyDomainInput").value = "sprint16.example.test";
          document.querySelector("#networkDomainPolicyModeInput").value = "deny";
          document.querySelector("#networkDomainPolicyReasonInput").value =
            "Browser network rule smoke.";
          document.querySelector("#networkDomainPolicyPriorityInput").value = "5";
          document.querySelector("#networkDomainPolicyForm")
            .dispatchEvent(new Event("submit", { bubbles: true, cancelable: true }));
          return true;
        })()
        """
    )
    devtools_page.wait_for(
        """
        document.querySelector("#networkDomainPolicyEditorOutput")
          ?.textContent.includes("Network rule created")
          && document.querySelector("#networkDomainPolicyList")
            ?.textContent.includes("sprint16.example.test")
          && document.querySelector("#networkDomainPolicyList")
            ?.textContent.includes("deny")
        """
    )
    devtools_page.eval(
        """
        (() => {
          document.querySelector("#networkPolicyCheckPanel").open = true;
          document.querySelector("#networkPolicyUrlInput").value = "https://sprint16.example.test/v1";
          document.querySelector("#networkPolicySurfaceInput").value = "generic";
          document.querySelector("#networkPolicyCheckForm")
            .dispatchEvent(new Event("submit", { bubbles: true, cancelable: true }));
          return true;
        })()
        """
    )
    devtools_page.wait_for(
        """
        document.querySelector("#networkPolicyCheckOutput")
          ?.textContent.includes("Network policy decision")
          && document.querySelector("#networkPolicyCheckOutput")
            ?.textContent.includes("deny")
          && document.querySelector("#networkPolicyCheckOutput")
            ?.textContent.includes("sprint16.example.test")
        """
    )
    devtools_page.eval(
        """
        (() => {
          const row = [...document.querySelectorAll("#networkDomainPolicyList .list-item")]
            .find((candidate) => candidate.textContent.includes("sprint16.example.test"));
          row.querySelector('[data-testid="network-domain-policy-toggle"]').click();
          return true;
        })()
        """
    )
    devtools_page.wait_for(
        """
        document.querySelector("#networkDomainPolicyEditorOutput")
          ?.textContent.includes("Network rule updated")
          && document.querySelector("#networkDomainPolicyList")
            ?.textContent.includes("sprint16.example.test")
        """
    )
    devtools_page.eval(
        """
        (() => {
          document.querySelector("#networkPolicyCheckForm")
            .dispatchEvent(new Event("submit", { bubbles: true, cancelable: true }));
          return true;
        })()
        """
    )
    devtools_page.wait_for(
        """
        document.querySelector("#networkPolicyCheckOutput")
          ?.textContent.includes("Network policy decision")
          && document.querySelector("#networkPolicyCheckOutput")
            ?.textContent.includes("allow")
        """
    )

    rules_status, rules_body = _http_json("GET", f"{base_url}/network/policy/rules")
    assert rules_status == 200
    assert rules_body[0]["domain"] == "sprint16.example.test"
    assert rules_body[0]["enabled"] is False


def test_browser_policy_panel_can_activate_plugin_components(
    ui_live_server,
    devtools_page,
) -> None:
    base_url, root_dir = ui_live_server
    plugin_id = "browser-component-plugin"
    _write_browser_plugin_component(
        root_dir,
        plugin_id,
        "docs/runbook.json",
        {"name": "Browser runbook", "body": "Approve browser component activation."},
    )
    _write_browser_plugin_manifest(
        root_dir,
        plugin_id,
        {
            "plugin_id": plugin_id,
            "name": "Browser component plugin",
            "version": "1.0.0",
            "components": {"docs": ["Browser runbook"]},
            "docs": [{"path": "docs/runbook.json", "name": "Browser runbook"}],
        },
    )
    trust_status, _trust_body = _http_json(
        "PATCH",
        f"{base_url}/plugins/{plugin_id}/trust",
        payload={"status": "trusted", "reason": "Browser component smoke."},
    )
    assert trust_status == 200

    devtools_page.call("Page.navigate", {"url": f"{base_url}/ui/#policy"})
    devtools_page.wait_for("document.readyState === 'complete'")
    devtools_page.wait_for(
        """
        document.querySelector("#pluginList")?.textContent.includes("browser-component-plugin")
          && document.querySelector("#pluginList")?.textContent.includes("components 1")
        """
    )
    devtools_page.eval(
        """
        (() => {
          const row = [...document.querySelectorAll("#pluginList .list-item")]
            .find((candidate) => candidate.textContent.includes("browser-component-plugin"));
          row.querySelector('[data-testid="plugin-components-preview"]').click();
          return true;
        })()
        """
    )
    devtools_page.wait_for(
        """
        document.querySelector("#pluginActivationOutput")
          ?.textContent.includes("Plugin components preview")
          && document.querySelector("#pluginActivationOutput")
            ?.textContent.includes("Browser runbook")
          && document.querySelector("#pluginActivationOutput")
            ?.textContent.includes("ready")
        """
    )
    devtools_page.eval(
        """
        (() => {
          const row = [...document.querySelectorAll("#pluginList .list-item")]
            .find((candidate) => candidate.textContent.includes("browser-component-plugin"));
          row.querySelector('[data-testid="plugin-components-install"]').click();
          return true;
        })()
        """
    )
    devtools_page.wait_for(
        """
        document.querySelector("#pluginActivationOutput")
          ?.textContent.includes("Plugin components install")
          && document.querySelector("#pluginActivationOutput")
            ?.textContent.includes("installed")
        """
    )
    list_status, list_body = _http_json("GET", f"{base_url}/plugins/{plugin_id}/components")
    assert list_status == 200
    assert list_body["components"][0]["status"] == "installed"

    devtools_page.eval(
        """
        (() => {
          const row = [...document.querySelectorAll("#pluginList .list-item")]
            .find((candidate) => candidate.textContent.includes("browser-component-plugin"));
          row.querySelector('[data-testid="plugin-components-disable"]').click();
          return true;
        })()
        """
    )
    devtools_page.wait_for(
        """
        document.querySelector("#pluginActivationOutput")
          ?.textContent.includes("Plugin components disable")
          && document.querySelector("#pluginActivationOutput")
            ?.textContent.includes("disabled")
        """
    )
    disabled_status, disabled_body = _http_json(
        "GET",
        f"{base_url}/plugins/{plugin_id}/components",
    )
    assert disabled_status == 200
    assert disabled_body["components"][0]["status"] == "disabled"


def test_browser_policy_panel_can_request_filesystem_approval_after_preflight(
    ui_live_server,
    devtools_page,
) -> None:
    base_url, root_dir = ui_live_server
    target = root_dir / "request-delete.txt"
    target.write_text("remove", encoding="utf-8")

    devtools_page.call("Page.navigate", {"url": f"{base_url}/ui/#policy"})
    devtools_page.wait_for("document.readyState === 'complete'")
    devtools_page.wait_for("Boolean(document.querySelector('#filesystemPolicyCheckForm'))")
    devtools_page.eval(
        """
        (() => {
          document.querySelector("#filesystemPolicyCheckPanel").open = true;
          document.querySelector("#filesystemPolicyActionInput").value = "delete";
          document.querySelector("#filesystemPolicyPathInput").value = "request-delete.txt";
          document.querySelector("#filesystemPolicyCheckForm")
            .dispatchEvent(new Event("submit", { bubbles: true, cancelable: true }));
          return true;
        })()
        """
    )
    devtools_page.wait_for(
        """
        document.querySelector("#filesystemPolicyCheckOutput")
          ?.textContent.includes("approval_required")
          && !document.querySelector("#filesystemPolicyApprovalButton")?.disabled
        """
    )
    devtools_page.eval('document.querySelector("#filesystemPolicyApprovalButton").click()')
    devtools_page.wait_for(
        """
        document.querySelector("#filesystemPolicyCheckOutput")
          ?.textContent.includes("Filesystem approval created")
          && document.querySelector("#filesystemPolicyCheckOutput")
            ?.textContent.includes("request-delete.txt")
        """
    )

    approvals_status, approvals_body = _http_json(
        "GET",
        f"{base_url}/filesystem/approvals?status=pending",
    )
    assert approvals_status == 200
    assert any(
        approval["path"] == "request-delete.txt"
        and approval["action"] == "delete"
        and approval["status"] == "pending"
        for approval in approvals_body
    )

    devtools_page.call("Page.navigate", {"url": f"{base_url}/ui/#approvals"})
    devtools_page.wait_for("Boolean(document.querySelector('#approvalSourceInput'))")
    devtools_page.eval(
        """
        (() => {
          const input = document.querySelector("#approvalSourceInput");
          input.value = "filesystem";
          input.dispatchEvent(new Event("change", { bubbles: true }));
          return true;
        })()
        """
    )
    devtools_page.wait_for(
        """
        [...document.querySelectorAll(".approval-item")]
          .some((row) => row.textContent.includes("request-delete.txt"))
        """
    )


def test_browser_policy_panel_preserves_filesystem_approval_options(
    ui_live_server,
    devtools_page,
) -> None:
    base_url, root_dir = ui_live_server
    source = root_dir / "copy-source.txt"
    target = root_dir / "copy-target.txt"
    source.write_text("fresh", encoding="utf-8")
    target.write_text("stale", encoding="utf-8")

    devtools_page.call("Page.navigate", {"url": f"{base_url}/ui/#policy"})
    devtools_page.wait_for("document.readyState === 'complete'")
    devtools_page.wait_for("Boolean(document.querySelector('#filesystemPolicyCheckForm'))")
    devtools_page.eval(
        """
        (() => {
          document.querySelector("#filesystemPolicyCheckPanel").open = true;
          document.querySelector("#filesystemPolicyRequestDetails").open = true;
          document.querySelector("#filesystemPolicyActionInput").value = "copy";
          document.querySelector("#filesystemPolicyActionInput")
            .dispatchEvent(new Event("change", { bubbles: true }));
          document.querySelector("#filesystemPolicyPathInput").value = "copy-source.txt";
          document.querySelector("#filesystemPolicyTargetInput").value = "copy-target.txt";
          document.querySelector("#filesystemPolicyOverwriteInput").checked = true;
          document.querySelector("#filesystemPolicyOverwriteInput")
            .dispatchEvent(new Event("change", { bubbles: true }));
          document.querySelector("#filesystemPolicyCheckForm")
            .dispatchEvent(new Event("submit", { bubbles: true, cancelable: true }));
          return true;
        })()
        """
    )
    devtools_page.wait_for(
        """
        document.querySelector("#filesystemPolicyCheckOutput")
          ?.textContent.includes("approval_required")
          && !document.querySelector("#filesystemPolicyApprovalButton")?.disabled
        """
    )
    devtools_page.eval('document.querySelector("#filesystemPolicyApprovalButton").click()')
    devtools_page.wait_for(
        """
        document.querySelector("#filesystemPolicyCheckOutput")
          ?.textContent.includes("Filesystem approval created")
          && document.querySelector("#filesystemPolicyCheckOutput")
            ?.textContent.includes('"overwrite": true')
        """
    )

    approvals_status, approvals_body = _http_json(
        "GET",
        f"{base_url}/filesystem/approvals?status=pending",
    )
    assert approvals_status == 200
    approval = next(
        item
        for item in approvals_body
        if item["path"] == "copy-source.txt" and item["target_path"] == "copy-target.txt"
    )
    assert approval["action"] == "copy"
    assert approval["overwrite"] is True
    assert approval["recursive"] is False

    devtools_page.call("Page.navigate", {"url": f"{base_url}/ui/#approvals"})
    devtools_page.wait_for("Boolean(document.querySelector('#approvalSourceInput'))")
    devtools_page.eval(
        """
        (() => {
          const input = document.querySelector("#approvalSourceInput");
          input.value = "filesystem";
          input.dispatchEvent(new Event("change", { bubbles: true }));
          return true;
        })()
        """
    )
    devtools_page.wait_for(
        """
        [...document.querySelectorAll(".approval-item")]
          .some((row) => row.textContent.includes("copy-source.txt"))
        """
    )
    devtools_page.eval(
        """
        (() => {
          const row = [...document.querySelectorAll(".approval-item")]
            .find((candidate) => candidate.textContent.includes("copy-source.txt"));
          row.querySelector("button").click();
          return true;
        })()
        """
    )
    devtools_page.wait_for(
        """
        document.querySelector("#approvalReview")?.textContent.includes("Filesystem review")
          && document.querySelector("#approvalReview")?.textContent.includes("Path digest")
          && document.querySelector("#approvalReview")?.textContent.includes("Options digest")
        """
    )
    devtools_page.eval(
        """
        (() => {
          const review = document.querySelector("#approvalReview");
          review.querySelector(".decision-form input").value = "Browser copy approval.";
          review.querySelector('button[data-decision="approve"]').click();
          return true;
        })()
        """
    )
    devtools_page.wait_for(
        """
        document.querySelector("#approvalReview")?.textContent.includes("approved")
          && Boolean(document.querySelector("#boundExecutionExecuteButton:not([disabled])"))
          && document.querySelector("#boundExecutionPayloadInput")?.value
            .includes('"overwrite": true')
          && document.querySelector("#boundExecutionPayloadInput")
            ?.value.includes('"target_path": "copy-target.txt"')
        """
    )
    devtools_page.eval(
        """
        (() => {
          const textarea = document.querySelector("#boundExecutionPayloadInput");
          const payload = JSON.parse(textarea.value);
          payload.target_path = "wrong-target.txt";
          textarea.value = JSON.stringify(payload, null, 2);
          document.querySelector("#boundExecutionExecuteButton").click();
          return true;
        })()
        """
    )
    devtools_page.wait_for(
        """
        document.querySelector("#boundExecutionOutput")
          ?.textContent.includes("target_path must match the approved filesystem request")
        """
    )
    assert target.read_text(encoding="utf-8") == "stale"

    devtools_page.eval(
        """
        (() => {
          const textarea = document.querySelector("#boundExecutionPayloadInput");
          const payload = JSON.parse(textarea.value);
          payload.target_path = "copy-target.txt";
          textarea.value = JSON.stringify(payload, null, 2);
          document.querySelector("#boundExecutionExecuteButton").click();
          return true;
        })()
        """
    )
    devtools_page.wait_for(
        """
        document.querySelector("#boundExecutionOutput")
          ?.textContent.includes("Bound request executed")
        """
    )
    assert source.read_text(encoding="utf-8") == "fresh"
    assert target.read_text(encoding="utf-8") == "fresh"

    review_status, review_body = _http_json(
        "GET",
        f"{base_url}/filesystem/approvals/{approval['id']}/review",
    )
    assert review_status == 200
    assert review_body["status"] == "executed"


def test_browser_approval_dashboard_can_execute_seeded_web_retrieval_network_approval(
    ui_live_server,
    devtools_page,
    web_retrieval_target_url,
) -> None:
    base_url, _root_dir = ui_live_server
    create_status, create_body = _http_json(
        "POST",
        f"{base_url}/web-retrieval/network/approvals",
        payload={"url": web_retrieval_target_url, "requested_by": "browser-network-smoke"},
    )
    assert create_status == 201

    devtools_page.call("Page.navigate", {"url": f"{base_url}/ui/#approvals"})
    devtools_page.wait_for("document.readyState === 'complete'")
    devtools_page.wait_for("Boolean(document.querySelector('#approvalSourceInput'))")
    devtools_page.eval(
        """
        (() => {
          const input = document.querySelector("#approvalSourceInput");
          input.value = "network";
          input.dispatchEvent(new Event("change", { bubbles: true }));
          return true;
        })()
        """
    )
    devtools_page.wait_for(
        """
        [...document.querySelectorAll(".approval-item")]
          .some((row) => row.textContent.includes("approved.txt"))
        """
    )
    devtools_page.eval(
        """
        (() => {
          const row = [...document.querySelectorAll(".approval-item")]
            .find((candidate) => candidate.textContent.includes("approved.txt"));
          row.querySelector("button").click();
          return true;
        })()
        """
    )
    devtools_page.wait_for(
        """
        document.querySelector("#approvalReview")?.textContent.includes("Network review")
          && document.querySelector("#approvalReview")?.textContent.includes("web_retrieval")
          && document.querySelector("#approvalReview")?.textContent.includes("pending")
        """
    )
    devtools_page.eval(
        """
        (() => {
          const review = document.querySelector("#approvalReview");
          review.querySelector(".decision-form input").value = "Browser network smoke.";
          review.querySelector('button[data-decision="approve"]').click();
          return true;
        })()
        """
    )
    devtools_page.wait_for(
        """
        document.querySelector("#approvalReview")?.textContent.includes("approved")
          && Boolean(document.querySelector("#boundExecutionExecuteButton:not([disabled])"))
          && document.querySelector("#boundExecutionPayloadInput")?.value.includes('"approval_id"')
          && document.querySelector("#boundExecutionPayloadInput")?.value.includes("approved.txt")
        """
    )
    devtools_page.eval('document.querySelector("#boundExecutionExecuteButton").click()')
    devtools_page.wait_for(
        """
        document.querySelector("#boundExecutionOutput")
          ?.textContent.includes("Bound request executed")
          && document.querySelector("#boundExecutionOutput")
            ?.textContent.includes("browser network approval smoke response")
        """,
        timeout_seconds=10.0,
    )

    review_status, review_body = _http_json(
        "GET",
        f"{base_url}/network/approvals/{create_body['id']}/review",
    )
    assert review_status == 200
    assert review_body["status"] == "executed"


def test_browser_approval_dashboard_can_execute_seeded_provider_approval(
    ui_live_server,
    devtools_page,
) -> None:
    base_url, _root_dir = ui_live_server
    approval_payload = {
        "provider_id": PROVIDER_ID,
        "model": "gpt-browser",
        "messages": [{"role": "user", "content": "<original approved message content>"}],
        "temperature": 0.2,
        "max_tokens": 32,
    }
    create_status, create_body = _http_json(
        "POST",
        f"{base_url}/providers/{PROVIDER_ID}/approvals?requested_by=browser-provider-smoke",
        payload=approval_payload,
    )
    assert create_status == 201
    network_status, network_body = _http_json(
        "POST",
        f"{base_url}/network/approvals",
        payload={
            "url": "https://provider.example.test/v1",
            "surface": "provider",
            "action": "generate",
            "requested_by": "browser-provider-smoke",
        },
    )
    assert network_status == 201
    network_approve_status, _network_approve_body = _http_json(
        "POST",
        f"{base_url}/network/approvals/{network_body['id']}/approve",
        payload={"decided_by": "browser-provider-reviewer"},
    )
    assert network_approve_status == 200

    devtools_page.call("Page.navigate", {"url": f"{base_url}/ui/#approvals"})
    devtools_page.wait_for("document.readyState === 'complete'")
    devtools_page.wait_for("Boolean(document.querySelector('#approvalSourceInput'))")
    devtools_page.eval(
        """
        (() => {
          const input = document.querySelector("#approvalSourceInput");
          input.value = "provider";
          input.dispatchEvent(new Event("change", { bubbles: true }));
          return true;
        })()
        """
    )
    devtools_page.wait_for(
        f"""
        [...document.querySelectorAll(".approval-item")]
          .some((row) => row.textContent.includes("{PROVIDER_ID}"))
        """
    )
    devtools_page.eval(
        f"""
        (() => {{
          const row = [...document.querySelectorAll(".approval-item")]
            .find((candidate) => candidate.textContent.includes("{PROVIDER_ID}"));
          row.querySelector("button").click();
          return true;
        }})()
        """
    )
    devtools_page.wait_for(
        """
        document.querySelector("#approvalReview")?.textContent.includes("Provider review")
          && document.querySelector("#approvalReview")?.textContent.includes("gpt-browser")
          && document.querySelector("#approvalReview")?.textContent.includes("pending")
        """
    )
    devtools_page.eval(
        """
        (() => {
          const review = document.querySelector("#approvalReview");
          review.querySelector(".decision-form input").value = "Browser provider smoke.";
          review.querySelector('button[data-decision="approve"]').click();
          return true;
        })()
        """
    )
    devtools_page.wait_for(
        """
        document.querySelector("#approvalReview")?.textContent.includes("approved")
          && Boolean(document.querySelector("#boundExecutionExecuteButton:not([disabled])"))
          && document.querySelector("#boundExecutionPayloadInput")?.value.includes('"approval_id"')
          && document.querySelector("#boundExecutionPayloadInput")?.value
            .includes('"network_approval_id"')
          && document.querySelector("#boundExecutionPayloadInput")?.value
            .includes("<original approved message content>")
        """
    )
    devtools_page.eval(
        f"""
        (() => {{
          const textarea = document.querySelector("#boundExecutionPayloadInput");
          const payload = JSON.parse(textarea.value);
          payload.network_approval_id = "{network_body["id"]}";
          textarea.value = JSON.stringify(payload, null, 2);
          return true;
        }})()
        """
    )
    devtools_page.eval('document.querySelector("#boundExecutionExecuteButton").click()')
    devtools_page.wait_for(
        """
        document.querySelector("#boundExecutionOutput")
          ?.textContent.includes("Bound request executed")
          && document.querySelector("#boundExecutionOutput")
            ?.textContent.includes("Approved browser provider response.")
        """,
        timeout_seconds=10.0,
    )

    review_status, review_body = _http_json(
        "GET",
        f"{base_url}/providers/approvals/{create_body['id']}/review",
    )
    assert review_status == 200
    assert review_body["status"] == "executed"
    network_review_status, network_review_body = _http_json(
        "GET",
        f"{base_url}/network/approvals/{network_body['id']}/review",
    )
    assert network_review_status == 200
    assert network_review_body["status"] == "executed"


def test_browser_provider_runtime_can_create_provider_approval_request(
    ui_live_server,
    devtools_page,
) -> None:
    base_url, _root_dir = ui_live_server
    message = "browser-provider-builder-secret"

    devtools_page.call("Page.navigate", {"url": f"{base_url}/ui/#providers"})
    devtools_page.wait_for("document.readyState === 'complete'")
    devtools_page.wait_for("Boolean(document.querySelector('#providerApprovalRequestForm'))")
    devtools_page.eval(
        f"""
        (() => {{
          document.querySelector("#providerApprovalRequestPanel").open = true;
          document.querySelector("#providerApprovalProviderInput").value = "{PROVIDER_ID}";
          document.querySelector("#providerApprovalModelInput").value = "gpt-browser";
          document.querySelector("#providerApprovalRoleInput").value = "user";
          document.querySelector("#providerApprovalMessageInput").value = {json.dumps(message)};
          document.querySelector("#providerApprovalTemperatureInput").value = "0.2";
          document.querySelector("#providerApprovalMaxTokensInput").value = "32";
          document.querySelector("#providerApprovalTaskInput").value =
            "sprint-16-provider-builder";
          document.querySelector("#providerApprovalOptionsInput").value =
            JSON.stringify({{ top_p: 0.9 }}, null, 2);
          document.querySelector("#providerApprovalRequestForm").requestSubmit();
          return true;
        }})()
        """
    )
    devtools_page.wait_for(
        """
        document.querySelector("#providerApprovalRequestOutput")
          ?.textContent.includes("Provider approval created")
        """,
        timeout_seconds=10.0,
    )

    list_status, list_body = _http_json("GET", f"{base_url}/providers/approvals?status=pending")
    assert list_status == 200
    approval = next(item for item in list_body if item["task_id"] == "sprint-16-provider-builder")
    assert approval["provider_id"] == PROVIDER_ID
    assert approval["model"] == "gpt-browser"
    assert approval["option_keys"] == ["top_p"]
    assert approval["review_messages"] == [{"role": "user", "content_length": len(message)}]
    assert message not in json.dumps(approval)

    devtools_page.wait_for(
        f"""
        [...document.querySelectorAll(".approval-item")]
          .some((row) => row.textContent.includes("{PROVIDER_ID}"))
        """
    )
    devtools_page.eval(
        f"""
        (() => {{
          const row = [...document.querySelectorAll(".approval-item")]
            .find((candidate) => candidate.textContent.includes("{PROVIDER_ID}"));
          row.querySelector("button").click();
          return true;
        }})()
        """
    )
    devtools_page.wait_for(
        """
        document.querySelector("#approvalReview")?.textContent.includes("Provider review")
          && document.querySelector("#approvalReview")?.textContent.includes("gpt-browser")
          && document.querySelector("#approvalReview")?.textContent.includes("pending")
        """
    )


def test_browser_provider_runtime_can_run_bound_provider_generation(
    ui_live_server,
    devtools_page,
) -> None:
    base_url, _root_dir = ui_live_server
    requested_by = "dashboard-provider-generation"
    message = "browser provider generation prompt"
    approval_payload = {
        "provider_id": PROVIDER_ID,
        "model": "gpt-browser",
        "messages": [{"role": "user", "content": message}],
        "temperature": 0.2,
        "max_tokens": 32,
        "timeout_seconds": 60,
        "options": {"top_p": 0.9},
        "requested_by": requested_by,
    }
    create_status, create_body = _http_json(
        "POST",
        f"{base_url}/providers/{PROVIDER_ID}/approvals?requested_by={requested_by}",
        payload=approval_payload,
    )
    assert create_status == 201
    approve_status, _approve_body = _http_json(
        "POST",
        f"{base_url}/providers/approvals/{create_body['id']}/approve",
        payload={"decided_by": "browser-provider-generation-reviewer"},
    )
    assert approve_status == 200
    network_status, network_body = _http_json(
        "POST",
        f"{base_url}/network/approvals",
        payload={
            "url": "https://provider.example.test/v1",
            "surface": "provider",
            "action": "generate",
            "requested_by": requested_by,
        },
    )
    assert network_status == 201
    network_approve_status, _network_approve_body = _http_json(
        "POST",
        f"{base_url}/network/approvals/{network_body['id']}/approve",
        payload={"decided_by": "browser-provider-generation-reviewer"},
    )
    assert network_approve_status == 200

    devtools_page.call("Page.navigate", {"url": f"{base_url}/ui/#providers"})
    devtools_page.wait_for("document.readyState === 'complete'")
    devtools_page.wait_for("Boolean(document.querySelector('#providerGenerationForm'))")
    devtools_page.eval(
        f"""
        (() => {{
          document.querySelector("#providerGenerationPanel").open = true;
          document.querySelector("#providerGenerationProviderInput").value = "{PROVIDER_ID}";
          document.querySelector("#providerGenerationModelInput").value = "gpt-browser";
          document.querySelector("#providerGenerationRoleInput").value = "user";
          document.querySelector("#providerGenerationRequesterInput").value = "{requested_by}";
          document.querySelector("#providerGenerationMessageInput").value = {json.dumps(message)};
          document.querySelector("#providerGenerationApprovalInput").value = "{create_body["id"]}";
          document.querySelector("#providerGenerationNetworkApprovalInput").value =
            "{network_body["id"]}";
          document.querySelector("#providerGenerationTemperatureInput").value = "0.2";
          document.querySelector("#providerGenerationMaxTokensInput").value = "32";
          document.querySelector("#providerGenerationTimeoutInput").value = "60";
          document.querySelector("#providerGenerationOptionsInput").value =
            JSON.stringify({{ top_p: 0.9 }}, null, 2);
          document.querySelector("#providerGenerationForm").requestSubmit();
          return true;
        }})()
        """
    )
    devtools_page.wait_for(
        """
        document.querySelector("#providerGenerationOutput")
          ?.textContent.includes("Provider generation completed")
          && document.querySelector("#providerGenerationOutput")
            ?.textContent.includes("Approved browser provider response.")
        """,
        timeout_seconds=10.0,
    )
    devtools_page.eval(
        """
        document.querySelector('[data-testid="provider-generation-use-response"]').click()
        """
    )
    devtools_page.wait_for(
        """
        document.querySelector("#taskChatContextInput")
          ?.value.includes("Approved browser provider response.")
        """
    )

    review_status, review_body = _http_json(
        "GET",
        f"{base_url}/providers/approvals/{create_body['id']}/review",
    )
    assert review_status == 200
    assert review_body["status"] == "executed"
    network_review_status, network_review_body = _http_json(
        "GET",
        f"{base_url}/network/approvals/{network_body['id']}/review",
    )
    assert network_review_status == 200
    assert network_review_body["status"] == "executed"


def test_browser_provider_generation_streaming_accumulates_ndjson_and_context(
    ui_live_server,
    devtools_page,
) -> None:
    base_url, _root_dir = ui_live_server
    message = "browser streamed provider prompt secret"

    devtools_page.call("Page.navigate", {"url": f"{base_url}/ui/#providers"})
    devtools_page.wait_for("document.readyState === 'complete'")
    devtools_page.wait_for("Boolean(document.querySelector('#providerGenerationForm'))")
    devtools_page.wait_for("Boolean(document.querySelector('#providerGenerationStreamInput'))")
    unsupported_state = devtools_page.eval(
        """
        (() => {
          populateProviderApprovalControls({
            ok: true,
            data: [
              {
                id: "streaming-provider",
                name: "Streaming Provider",
                kind: "external",
                enabled: true,
                permission_mode: "approval_required",
                model_names: ["stream-model"],
                supports_streaming: true,
              },
              {
                id: "blocked-provider",
                name: "Blocked Provider",
                kind: "external",
                enabled: true,
                permission_mode: "approval_required",
                model_names: ["blocked-model"],
                supports_streaming: false,
              },
            ],
          });
          const providerInput = document.querySelector("#providerGenerationProviderInput");
          const streamInput = document.querySelector("#providerGenerationStreamInput");
          providerInput.value = "blocked-provider";
          streamInput.checked = true;
          providerInput.dispatchEvent(new Event("change", { bubbles: true }));
          return { checked: streamInput.checked, disabled: streamInput.disabled };
        })()
        """
    )
    assert unsupported_state["disabled"] or not unsupported_state["checked"]

    devtools_page.eval(
        """
        (() => {
          const originalFetch = window.fetch.bind(window);
          window.__providerGenerationStreamRequests = [];
          window.fetch = async (input, init = {}) => {
            const url = typeof input === "string" ? input : input.url;
            if (url.endsWith("/providers/generate/stream")) {
              window.__providerGenerationStreamRequests.push(JSON.parse(init.body));
              const encoder = new TextEncoder();
              const lines = [
                JSON.stringify({
                  provider_id: "streaming-provider",
                  model: "stream-model",
                  event: "chunk",
                  delta: "Streamed ",
                  raw_response_metadata: { id: "chatcmpl-ui-stream" },
                }) + "\\n",
                JSON.stringify({
                  provider_id: "streaming-provider",
                  model: "stream-model",
                  event: "chunk",
                  delta: "provider response.",
                  raw_response_metadata: { source: "safe-metadata" },
                }) + "\\n",
                JSON.stringify({
                  provider_id: "streaming-provider",
                  model: "stream-model",
                  event: "chunk",
                  delta: "",
                  finish_reason: "stop",
                  usage_metadata: {
                    prompt_tokens: 7,
                    completion_tokens: 3,
                    total_tokens: 10,
                  },
                  estimated_cost_usd: 0.0002,
                  duration_ms: 123,
                  raw_response_metadata: { finish_reason: "stop", source: "safe-metadata" },
                }) + "\\n",
              ];
              return new Response(
                new ReadableStream({
                  start(controller) {
                    for (const line of lines) {
                      controller.enqueue(encoder.encode(line));
                    }
                    controller.close();
                  },
                }),
                { status: 200, headers: { "Content-Type": "application/x-ndjson" } },
              );
            }
            return originalFetch(input, init);
          };
          return true;
        })()
        """
    )
    devtools_page.eval(
        f"""
        (() => {{
          document.querySelector("#providerGenerationPanel").open = true;
          document.querySelector("#providerGenerationProviderInput").value = "streaming-provider";
          document.querySelector("#providerGenerationProviderInput")
            .dispatchEvent(new Event("change", {{ bubbles: true }}));
          document.querySelector("#providerGenerationModelInput").value = "stream-model";
          document.querySelector("#providerGenerationStreamInput").checked = true;
          document.querySelector("#providerGenerationRoleInput").value = "developer";
          document.querySelector("#providerGenerationRequesterInput").value =
            "dashboard-provider-stream";
          document.querySelector("#providerGenerationMessageInput").value = {json.dumps(message)};
          document.querySelector("#providerGenerationApprovalInput").value =
            "provider-approval-stream";
          document.querySelector("#providerGenerationNetworkApprovalInput").value =
            "network-approval-stream";
          document.querySelector("#providerGenerationTemperatureInput").value = "0.4";
          document.querySelector("#providerGenerationMaxTokensInput").value = "64";
          document.querySelector("#providerGenerationTimeoutInput").value = "45";
          document.querySelector("#providerGenerationTaskInput").value =
            "sprint-16-provider-stream";
          document.querySelector("#providerGenerationAgentInput").value = "agent-stream";
          document.querySelector("#providerGenerationAgentRoleInput").value = "qa";
          document.querySelector("#providerGenerationOptionsInput").value =
            JSON.stringify({{ top_p: 0.8, seed: 16 }}, null, 2);
          document.querySelector("#providerGenerationForm").requestSubmit();
          return true;
        }})()
        """
    )
    devtools_page.wait_for(
        """
        document.querySelector("#providerGenerationOutput")
          ?.textContent.includes("Streamed provider response.")
          && document.querySelector("#providerGenerationOutput")
            ?.textContent.includes("safe-metadata")
          && document.querySelector("#providerGenerationOutput")
            ?.textContent.includes("total_tokens")
        """,
        timeout_seconds=10.0,
    )
    payload = devtools_page.eval("window.__providerGenerationStreamRequests[0]")
    assert payload["provider_id"] == "streaming-provider"
    assert payload["model"] == "stream-model"
    assert payload["messages"] == [{"role": "developer", "content": message}]
    assert payload["stream"] is True
    assert payload["requested_by"] == "dashboard-provider-stream"
    assert payload["approval_id"] == "provider-approval-stream"
    assert payload["network_approval_id"] == "network-approval-stream"
    assert payload["options"] == {"top_p": 0.8, "seed": 16}
    assert payload["timeout_seconds"] == 45
    assert payload["task_id"] == "sprint-16-provider-stream"
    assert payload["agent_id"] == "agent-stream"
    assert payload["agent_role"] == "qa"

    devtools_page.eval(
        """
        document.querySelector('[data-testid="provider-generation-use-response"]').click()
        """
    )
    devtools_page.wait_for(
        """
        document.querySelector("#taskChatContextInput")
          ?.value.includes("Streamed provider response.")
        """
    )


def test_browser_approval_dashboard_can_execute_seeded_tool_approval(
    ui_live_server,
    devtools_page,
) -> None:
    base_url, _root_dir = ui_live_server
    tool_name = "browser-approval-tool"
    generate_status, _generate_body = _http_json(
        "POST",
        f"{base_url}/tools/generate",
        payload={
            "name": tool_name,
            "description": "Browser approval smoke tool.",
            "trigger_source": "main_agent",
            "permission_mode": "approval_required",
            "source_code": (
                "def run(payload):\n    return {'ok': True, 'value': payload.get('value')}\n"
            ),
        },
    )
    assert generate_status == 201
    create_status, create_body = _http_json(
        "POST",
        f"{base_url}/tools/{tool_name}/approvals?requested_by=browser-tool-smoke",
        payload={"payload": {"value": "browser-tool-value"}, "timeout_seconds": 5},
    )
    assert create_status == 201

    devtools_page.call("Page.navigate", {"url": f"{base_url}/ui/#approvals"})
    devtools_page.wait_for("document.readyState === 'complete'")
    devtools_page.wait_for("Boolean(document.querySelector('#approvalSourceInput'))")
    devtools_page.eval(
        """
        (() => {
          const input = document.querySelector("#approvalSourceInput");
          input.value = "tool";
          input.dispatchEvent(new Event("change", { bubbles: true }));
          return true;
        })()
        """
    )
    devtools_page.wait_for(
        f"""
        [...document.querySelectorAll(".approval-item")]
          .some((row) => row.textContent.includes("{tool_name}"))
        """
    )
    devtools_page.eval(
        f"""
        (() => {{
          const row = [...document.querySelectorAll(".approval-item")]
            .find((candidate) => candidate.textContent.includes("{tool_name}"));
          row.querySelector("button").click();
          return true;
        }})()
        """
    )
    devtools_page.wait_for(
        """
        document.querySelector("#approvalReview")?.textContent.includes("Tool review")
          && document.querySelector("#approvalReview")?.textContent
            .includes("browser-approval-tool")
          && document.querySelector("#approvalReview")?.textContent.includes("pending")
        """
    )
    devtools_page.eval(
        """
        (() => {
          const review = document.querySelector("#approvalReview");
          review.querySelector(".decision-form input").value = "Browser tool smoke.";
          review.querySelector('button[data-decision="approve"]').click();
          return true;
        })()
        """
    )
    devtools_page.wait_for(
        """
        document.querySelector("#approvalReview")?.textContent.includes("approved")
          && Boolean(document.querySelector("#boundExecutionExecuteButton:not([disabled])"))
          && document.querySelector("#boundExecutionPayloadInput")?.value.includes('"approval_id"')
          && document.querySelector("#boundExecutionPayloadInput")?.value
            .includes("browser-tool-value")
        """
    )
    devtools_page.eval('document.querySelector("#boundExecutionExecuteButton").click()')
    devtools_page.wait_for(
        """
        document.querySelector("#boundExecutionOutput")
          ?.textContent.includes("Bound request executed")
          && document.querySelector("#boundExecutionOutput")
            ?.textContent.includes("browser-tool-value")
        """,
        timeout_seconds=10.0,
    )

    review_status, review_body = _http_json(
        "GET",
        f"{base_url}/tools/approvals/{create_body['id']}/review",
    )
    assert review_status == 200
    assert review_body["status"] == "executed"


def test_browser_provider_runtime_can_create_tool_approval_request(
    ui_live_server,
    devtools_page,
) -> None:
    base_url, _root_dir = ui_live_server
    tool_name = "browser-builder-approval-tool"
    payload_value = "browser-tool-builder-value"
    generate_status, _generate_body = _http_json(
        "POST",
        f"{base_url}/tools/generate",
        payload={
            "name": tool_name,
            "description": "Browser approval request builder smoke tool.",
            "trigger_source": "main_agent",
            "permission_mode": "approval_required",
            "source_code": (
                "def run(payload):\n    return {'ok': True, 'value': payload.get('value')}\n"
            ),
        },
    )
    assert generate_status == 201

    devtools_page.call("Page.navigate", {"url": f"{base_url}/ui/#providers"})
    devtools_page.wait_for("document.readyState === 'complete'")
    devtools_page.wait_for("Boolean(document.querySelector('#toolApprovalRequestForm'))")
    devtools_page.eval(
        f"""
        (() => {{
          document.querySelector("#toolApprovalRequestPanel").open = true;
          document.querySelector("#toolApprovalNameInput").value = "{tool_name}";
          document.querySelector("#toolApprovalTaskInput").value = "sprint-16-tool-builder";
          document.querySelector("#toolApprovalTimeoutInput").value = "5";
          document.querySelector("#toolApprovalPayloadInput").value =
            JSON.stringify({{ value: {json.dumps(payload_value)} }}, null, 2);
          document.querySelector("#toolApprovalRequestForm").requestSubmit();
          return true;
        }})()
        """
    )
    devtools_page.wait_for(
        """
        document.querySelector("#toolApprovalRequestOutput")
          ?.textContent.includes("Tool approval created")
        """,
        timeout_seconds=10.0,
    )

    list_status, list_body = _http_json("GET", f"{base_url}/tools/approvals?status=pending")
    assert list_status == 200
    approval = next(item for item in list_body if item["task_id"] == "sprint-16-tool-builder")
    assert approval["tool_name"] == tool_name
    assert approval["review_payload"] == {"value": payload_value}
    assert approval["timeout_seconds"] == 5

    devtools_page.wait_for(
        f"""
        [...document.querySelectorAll(".approval-item")]
          .some((row) => row.textContent.includes("{tool_name}"))
        """
    )
    devtools_page.eval(
        f"""
        (() => {{
          const row = [...document.querySelectorAll(".approval-item")]
            .find((candidate) => candidate.textContent.includes("{tool_name}"));
          row.querySelector("button").click();
          return true;
        }})()
        """
    )
    devtools_page.wait_for(
        """
        document.querySelector("#approvalReview")?.textContent.includes("Tool review")
          && document.querySelector("#approvalReview")?.textContent
            .includes("browser-builder-approval-tool")
          && document.querySelector("#approvalReview")?.textContent.includes("pending")
        """
    )


def test_browser_approval_dashboard_can_execute_seeded_tool_network_approval(
    ui_live_server,
    devtools_page,
    socket_listener,
) -> None:
    base_url, _root_dir = ui_live_server
    host, port = socket_listener.getsockname()
    tool_name = "browser-network-approval-tool"
    generate_status, _generate_body = _http_json(
        "POST",
        f"{base_url}/tools/generate",
        payload={
            "name": tool_name,
            "description": "Browser generated-tool network approval smoke.",
            "trigger_source": "main_agent",
            "permission_mode": "approval_required",
            "source_code": (
                "import socket\n\n"
                "def run(payload):\n"
                f"    with socket.create_connection(({host!r}, {port}), timeout=2):\n"
                "        return {'ok': True, 'value': payload.get('value')}\n"
            ),
        },
    )
    assert generate_status == 201
    create_status, create_body = _http_json(
        "POST",
        f"{base_url}/tools/{tool_name}/approvals?requested_by=browser-tool-network-smoke",
        payload={"payload": {"value": "browser-tool-network-value"}, "timeout_seconds": 5},
    )
    assert create_status == 201
    network_status, network_body = _http_json(
        "POST",
        f"{base_url}/network/approvals",
        payload={
            "url": f"https://{host}:{port}",
            "surface": "generated_tool",
            "action": "socket_connect",
            "requested_by": "browser-tool-network-smoke",
        },
    )
    assert network_status == 201
    network_approve_status, _network_approve_body = _http_json(
        "POST",
        f"{base_url}/network/approvals/{network_body['id']}/approve",
        payload={"decided_by": "browser-tool-network-reviewer"},
    )
    assert network_approve_status == 200

    devtools_page.call("Page.navigate", {"url": f"{base_url}/ui/#approvals"})
    devtools_page.wait_for("document.readyState === 'complete'")
    devtools_page.wait_for("Boolean(document.querySelector('#approvalSourceInput'))")
    devtools_page.eval(
        """
        (() => {
          const input = document.querySelector("#approvalSourceInput");
          input.value = "tool";
          input.dispatchEvent(new Event("change", { bubbles: true }));
          return true;
        })()
        """
    )
    devtools_page.wait_for(
        f"""
        [...document.querySelectorAll(".approval-item")]
          .some((row) => row.textContent.includes("{tool_name}"))
        """
    )
    devtools_page.eval(
        f"""
        (() => {{
          const row = [...document.querySelectorAll(".approval-item")]
            .find((candidate) => candidate.textContent.includes("{tool_name}"));
          row.querySelector("button").click();
          return true;
        }})()
        """
    )
    devtools_page.wait_for(
        """
        document.querySelector("#approvalReview")?.textContent.includes("Tool review")
          && document.querySelector("#approvalReview")?.textContent
            .includes("browser-network-approval-tool")
          && document.querySelector("#approvalReview")?.textContent.includes("pending")
        """
    )
    devtools_page.eval(
        """
        (() => {
          const review = document.querySelector("#approvalReview");
          review.querySelector(".decision-form input").value = "Browser tool network smoke.";
          review.querySelector('button[data-decision="approve"]').click();
          return true;
        })()
        """
    )
    devtools_page.wait_for(
        """
        document.querySelector("#approvalReview")?.textContent.includes("approved")
          && Boolean(document.querySelector("#boundExecutionExecuteButton:not([disabled])"))
          && document.querySelector("#boundExecutionPayloadInput")?.value.includes('"approval_id"')
          && document.querySelector("#boundExecutionPayloadInput")?.value
            .includes('"network_approval_id"')
          && document.querySelector("#boundExecutionPayloadInput")?.value
            .includes("browser-tool-network-value")
        """
    )
    devtools_page.eval(
        f"""
        (() => {{
          const textarea = document.querySelector("#boundExecutionPayloadInput");
          const payload = JSON.parse(textarea.value);
          payload.network_approval_id = "{network_body["id"]}";
          textarea.value = JSON.stringify(payload, null, 2);
          return true;
        }})()
        """
    )
    devtools_page.eval('document.querySelector("#boundExecutionExecuteButton").click()')
    devtools_page.wait_for(
        """
        document.querySelector("#boundExecutionOutput")
          ?.textContent.includes("Bound request executed")
          && document.querySelector("#boundExecutionOutput")
            ?.textContent.includes("browser-tool-network-value")
        """,
        timeout_seconds=10.0,
    )

    review_status, review_body = _http_json(
        "GET",
        f"{base_url}/tools/approvals/{create_body['id']}/review",
    )
    assert review_status == 200
    assert review_body["status"] == "executed"
    network_review_status, network_review_body = _http_json(
        "GET",
        f"{base_url}/network/approvals/{network_body['id']}/review",
    )
    assert network_review_status == 200
    assert network_review_body["status"] == "executed"
