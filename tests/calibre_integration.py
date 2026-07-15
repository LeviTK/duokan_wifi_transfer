#!/usr/bin/env python3
"""Calibre-hosted integration smoke test for multipart EPUB uploads."""

from __future__ import annotations

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import tempfile
import threading

import calibre.customize.ui as plugin_ui


PAYLOAD = b"PK\x03\x04duokan-automation-test-epub"


class UploadHandler(BaseHTTPRequestHandler):
    server_version = "DuokanAutomationTest/1.0"

    def do_POST(self):
        if self.path != "/files":
            self.send_error(404)
            return
        length = int(self.headers.get("Content-Length", "0"))
        body = self.rfile.read(length)
        self.server.upload_headers = self.headers
        self.server.upload_body = body
        self.send_response(200)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.end_headers()
        self.wfile.write("上传成功".encode("utf-8"))

    def log_message(self, format, *args):
        return


def main() -> None:
    plugin_ui.initialize_plugins()
    from calibre_plugins.duokan_wifi_transfer.ui import InterfacePlugin
    from calibre_plugins.duokan_wifi_transfer.main import ConnectionTestWorker, SendBooksWorker

    assert "finished" not in ConnectionTestWorker.__dict__
    assert "finished" not in SendBooksWorker.__dict__
    assert "result_ready" in ConnectionTestWorker.__dict__
    assert "completed" in SendBooksWorker.__dict__

    server = ThreadingHTTPServer(("127.0.0.1", 0), UploadHandler)
    server.upload_headers = None
    server.upload_body = None
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    try:
        with tempfile.TemporaryDirectory(prefix="duokan-upload-test.") as temp:
            epub = Path(temp) / "automation-test.epub"
            epub.write_bytes(PAYLOAD)
            plugin = InterfacePlugin.__new__(InterfacePlugin)
            plugin.duokan_wifi_address = f"http://127.0.0.1:{server.server_port}"
            success, error = plugin.send_book_to_duokan(str(epub), "自动化测试书籍")

        assert success is True, error
        assert error is None
        assert server.upload_headers is not None
        assert server.upload_body is not None
        assert server.upload_headers.get("User-Agent") == "Calibre Duokan Plugin/1.0"
        assert "multipart/form-data" in server.upload_headers.get("Content-Type", "")
        assert b'name="newfile"' in server.upload_body
        assert b'filename="automation-test.epub"' in server.upload_body
        assert PAYLOAD in server.upload_body
        print("UPLOAD OK: /files multipart 请求、字段名、文件名和 EPUB 内容均正确")
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


if __name__ == "__main__":
    main()
