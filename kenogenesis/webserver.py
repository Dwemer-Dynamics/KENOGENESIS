"""Loopback browser with shared core operations, origin and per-session CSRF checks."""

import json
import secrets
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

from .core import envelope

GET_OPERATIONS = {"list_projects", "project_view", "lookup_command", "search_game_data", "validate_mod", "compatibility"}
POST_OPERATIONS = {"create_project", "preview_patch", "apply_patch", "preview_fields", "apply_fields",
                   "configure_project", "export_mod"}
WEB_ROOT = Path(__file__).parent / "web"


def make_server(core, port=8766):
    token = secrets.token_urlsafe(32)

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, format, *args):
            print(format % args, file=sys.stderr)

        def _send(self, status, body, content_type="application/json"):
            if not isinstance(body, bytes):
                body = json.dumps(body, ensure_ascii=True).encode()
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Content-Security-Policy", "default-src 'self'; script-src 'self'; style-src 'self'; object-src 'none'; frame-ancestors 'none'; base-uri 'none'")
            self.end_headers()
            self.wfile.write(body)

        def _host_allowed(self):
            return self.headers.get("Host") == f"127.0.0.1:{self.server.server_port}"

        def do_GET(self):
            if not self._host_allowed():
                return self._send(403, {"ok": False, "error": {"code": "host", "message": "Use the printed loopback address."}})
            url = urlsplit(self.path)
            if url.path in ("/", "/app.js", "/style.css"):
                filename = {"/": "index.html", "/app.js": "app.js", "/style.css": "style.css"}[url.path]
                data = (WEB_ROOT / filename).read_bytes().replace(b"__CSRF_TOKEN__", token.encode())
                mime = {"index.html": "text/html; charset=utf-8", "app.js": "text/javascript; charset=utf-8", "style.css": "text/css; charset=utf-8"}[filename]
                return self._send(200, data, mime)
            name = url.path.removeprefix("/api/")
            if not url.path.startswith("/api/") or name not in GET_OPERATIONS:
                return self._send(404, {"ok": False, "error": {"code": "not_found"}})
            try:
                query = parse_qs(url.query)
                params = json.loads(query.get("args", ["{}"])[0])
                if not isinstance(params, dict):
                    raise ValueError("Expected JSON arguments")
                result = envelope(getattr(core, name), **params)
                return self._send(200 if result["ok"] else 400, result)
            except (ValueError, TypeError) as exc:
                return self._send(400, {"ok": False, "error": {"code": "bad_request", "message": str(exc)}})

        def do_POST(self):
            origin = f"http://127.0.0.1:{self.server.server_port}"
            if not self._host_allowed() or self.headers.get("Origin") != origin or self.headers.get("X-Kenogenesis-Token") != token:
                return self._send(403, {"ok": False, "error": {"code": "request_origin", "message": "Reload the local browser page."}})
            name = urlsplit(self.path).path.removeprefix("/api/")
            if name not in POST_OPERATIONS:
                return self._send(404, {"ok": False, "error": {"code": "not_found"}})
            try:
                size = int(self.headers.get("Content-Length", "0"))
                if not 0 < size <= 1024 * 1024 or self.headers.get("Content-Type") != "application/json":
                    raise ValueError("Use application/json with a body below 1 MiB")
                params = json.loads(self.rfile.read(size))
                if not isinstance(params, dict):
                    raise ValueError("Expected a JSON object")
                result = envelope(getattr(core, name), **params)
                return self._send(200 if result["ok"] else 409, result)
            except (ValueError, TypeError) as exc:
                return self._send(400, {"ok": False, "error": {"code": "bad_request", "message": str(exc)}})

    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    server.daemon_threads = True
    return server


def serve(core, port=8766):
    server = make_server(core, port)
    print(f"KENOGENESIS: http://127.0.0.1:{server.server_port}", file=sys.stderr, flush=True)
    try:
        server.serve_forever()
    finally:
        server.server_close()
