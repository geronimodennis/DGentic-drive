import base64
import json
import os
import shutil
import socket
import struct
import subprocess
import threading
import time
from pathlib import Path
from urllib.parse import urlparse
from urllib.request import Request, urlopen

import pytest
import uvicorn

from dgentic.database import reset_database_state
from dgentic.main import create_app
from dgentic.settings import get_settings

pytestmark = [
    pytest.mark.filterwarnings("ignore:websockets\\.legacy is deprecated:DeprecationWarning"),
    pytest.mark.filterwarnings(
        "ignore:websockets\\.server\\.WebSocketServerProtocol is deprecated:DeprecationWarning"
    ),
]


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


@pytest.fixture()
def ui_live_server(tmp_path, monkeypatch):
    root_dir = tmp_path / "workspace"
    root_dir.mkdir()
    monkeypatch.setenv("DGENTIC_ROOT_DIR", str(root_dir))
    monkeypatch.setenv("DGENTIC_DATA_DIR", str(tmp_path / "state"))
    monkeypatch.setenv("DGENTIC_ENVIRONMENT", "production")
    monkeypatch.setenv("DGENTIC_AUTH_ENABLED", "false")
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
        reset_database_state()
        get_settings.cache_clear()


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
