"""Loopback browser with shared core operations, origin and per-session CSRF checks.

GET requests never write. Mutations are POST operations of the shared core, guarded by the exact
loopback Host, a matching Origin and a per-server token. File routes serve only contained files of a
project's mod folder (exact case, no links), allowlisted docs, a project's private top-level docs/*.md notes,
and export and Workshop-stage artifacts by validated id.
"""

import json
import platform
import re
import secrets
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlsplit

from . import __version__
from .commands import MANUAL, RELEASE_541, TABLES
from .core import envelope
from .errors import KenoError
from .images import preview_png

GET_OPERATIONS = {"list_projects", "project_view", "lookup_command", "search_game_data", "validate_mod", "compatibility",
                  "list_exports", "project_model", "compare_units", "design_report", "list_evidence", "list_workshop_stages",
                  "compare_classes", "catalog_page", "catalog_entry"}
POST_OPERATIONS = {"create_project", "preview_patch", "apply_patch", "preview_fields", "apply_fields",
                   "configure_project", "export_mod", "preview_block_edit", "apply_block_edit",
                   "preview_import_upload", "import_upload", "preview_art_upload", "apply_art_upload",
                   "preview_catalog_import", "apply_catalog_import", "record_evidence",
                   "preview_catalog_snapshot", "apply_catalog_snapshot", "preview_workshop_stage", "stage_workshop_bundle"}
UPLOADS = {"preview_import_upload", "import_upload", "preview_art_upload", "apply_art_upload",
           "preview_catalog_import", "apply_catalog_import", "preview_workshop_stage", "stage_workshop_bundle"}
WEB_ROOT = Path(__file__).parent / "web"
SOURCE_ROOT = Path(__file__).resolve().parent.parent
STATIC = {"/static/app.js": ("app.js", "text/javascript; charset=utf-8"),
          "/static/app.css": ("app.css", "text/css; charset=utf-8"),
          "/static/favicon.svg": ("favicon.svg", "image/svg+xml")}
# In-app documentation: a fixed allowlist read from the source checkout (absent in a wheel install).
DOCS = {"README.md": "README.md", "WEB-BROWSER.md": "docs/WEB-BROWSER.md", "AGENT_USAGE.md": "docs/AGENT_USAGE.md",
        "ASSET-RULESET.md": "docs/ASSET-RULESET.md", "CLI_REFERENCE.md": "docs/CLI_REFERENCE.md", "VALIDATION.md": "docs/VALIDATION.md", "CATALOG.md": "docs/CATALOG.md",
        "FACTION-DESIGN.md": "docs/FACTION-DESIGN.md"}
CONFLICTS = {"stale_revision", "project_locked", "inputs_changed", "dest_exists", "line_changed"}
CSP = ("default-src 'none'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'; "
       "object-src 'none'; frame-ancestors 'none'; base-uri 'none'; form-action 'none'")
SLUG = re.compile(r"^[a-z][a-z0-9_]{1,47}$")


def doc_path(name):
    """Read maintained checkout guides, or the same guides bundled by the wheel build."""
    source = SOURCE_ROOT / DOCS[name]
    installed = Path(__file__).parent / "docs" / name
    return source if source.is_file() else installed


def docs_available():
    return [{"name": name} for name in DOCS if doc_path(name).is_file()]


def make_server(core, port=8766):
    token = secrets.token_urlsafe(32)
    meta_cache = {}

    def meta():
        if not meta_cache:
            from .view import form_specs, opener_specs, registry
            # runtime names the interpreter serving this page so generated CLI instructions use the same Python.
            meta_cache.update(tool="KENOGENESIS", version=__version__, manual=MANUAL, release_notes=[RELEASE_541], registry=registry(),
                              forms=form_specs(), openers=opener_specs(), tables=TABLES,
                              runtime={"python_executable": sys.executable, "python_version": platform.python_version(),
                                       "platform": sys.platform})
        return {**meta_cache, "docs": docs_available(), "workspace": str(core.workspace)}

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, format, *args):
            print(format % args, file=sys.stderr)

        def _send(self, status, body, content_type="application/json", download=None):
            if not isinstance(body, bytes):
                body = json.dumps(body, ensure_ascii=True).encode()
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Referrer-Policy", "no-referrer")
            self.send_header("Cross-Origin-Resource-Policy", "same-origin")
            self.send_header("Content-Security-Policy", CSP)
            if download:
                safe = re.sub(r"[^A-Za-z0-9_.-]", "_", download)[:120] or "download"
                self.send_header("Content-Disposition", f'attachment; filename="{safe}"')
            self.end_headers()
            self.wfile.write(body)

        def _error(self, status, code, message):
            return self._send(status, {"ok": False, "error": {"code": code, "message": message}})

        def _host_allowed(self):
            return self.headers.get("Host") == f"127.0.0.1:{self.server.server_port}"

        def _result(self, function, **params):
            result = envelope(function, **params)
            if result["ok"]:
                return self._send(200, result)
            code = result["error"]["code"]
            return self._send(404 if code == "not_found" else 409 if code in CONFLICTS else 400, result)

        def do_GET(self):
            if not self._host_allowed():
                return self._error(403, "host", "Use the printed loopback address.")
            url = urlsplit(self.path)
            query = parse_qs(url.query)
            download = query.get("download", [""])[0] == "1"
            if url.path == "/":
                data = (WEB_ROOT / "index.html").read_bytes().replace(b"__CSRF_TOKEN__", token.encode())
                return self._send(200, data, "text/html; charset=utf-8")
            if url.path in STATIC:
                name, mime = STATIC[url.path]
                return self._send(200, (WEB_ROOT / name).read_bytes(), mime)
            if not url.path.startswith("/api/"):
                return self._error(404, "not_found", "Unknown page.")
            parts = [unquote(p) for p in url.path[len("/api/"):].split("/")]
            try:
                if len(parts) == 1 and parts[0] in GET_OPERATIONS:
                    params = json.loads(query.get("args", ["{}"])[0])
                    if not isinstance(params, dict):
                        raise ValueError("Expected JSON arguments")
                    return self._result(getattr(core, parts[0]), **params)
                if parts == ["meta"]:
                    return self._send(200, {"ok": True, "result": meta()})
                if parts[0] == "docs" and len(parts) == 2 and parts[1] in DOCS:
                    path = doc_path(parts[1])
                    if not path.is_file():
                        return self._error(404, "not_found", "This installation does not include that document.")
                    return self._send(200, path.read_bytes(), "text/markdown; charset=utf-8", parts[1] if download else None)
                if parts == ["projects"]:
                    return self._result(core.browser_projects)
                if parts[0] == "projects" and len(parts) >= 2 and SLUG.fullmatch(parts[1]):
                    return self._project_get(parts[1], parts[2:], query, download)
                return self._error(404, "not_found", "Unknown API route.")
            except (ValueError, TypeError) as exc:
                return self._error(400, "bad_request", str(exc))

        def _project_get(self, slug, rest, query, download):
            q = lambda k, d="": query.get(k, [d])[0]
            if not rest:
                return self._result(core.browser_model, project=slug)
            if rest == ["source"]:
                try:
                    data = core.mod_source(slug)
                except KenoError as exc:
                    return self._send(404 if exc.code == "not_found" else 400, {"ok": False, "error": exc.to_dict()})
                if not download:
                    from .parser import decode
                    data = decode(data)[0].encode("utf-8")
                return self._send(200, data, "text/plain; charset=utf-8", f"{slug}.c5m" if download else None)
            if rest[0] == "files" and len(rest) > 1:
                path = "/".join(rest[1:])
                try:
                    data = core.mod_file(slug, path)
                    if q("format") == "png" or path.lower().endswith(".png") and not download:
                        return self._send(200, preview_png(path, data), "image/png")
                except KenoError as exc:
                    return self._send(404, {"ok": False, "error": exc.to_dict()})
                except (ValueError, OSError) as exc:
                    return self._error(415, "preview_unavailable", str(exc))
                return self._send(200, data, "application/octet-stream", path.split("/")[-1])
            if rest == ["exports"]:
                return self._result(core.list_exports, project=slug)
            if rest[0] == "exports" and len(rest) == 3:
                try:
                    data, name = core.export_artifact(slug, rest[1], rest[2])
                except KenoError as exc:
                    return self._send(404, {"ok": False, "error": exc.to_dict()})
                if rest[2] == "manifest":
                    return self._send(200, data, "application/json", name if download else None)
                return self._send(200, data, "application/zip", name)
            if rest == ["workshop"]:
                return self._result(core.list_workshop_stages, project=slug)
            if rest[0] == "workshop" and len(rest) == 3:
                try:
                    data, name = core.workshop_artifact(slug, rest[1], rest[2])
                except KenoError as exc:
                    return self._send(404, {"ok": False, "error": exc.to_dict()})
                if rest[2] == "receipt":
                    return self._send(200, data, "application/json", name if download else None)
                return self._send(200, data, "application/zip", name)
            if rest == ["catalog"]:
                try:
                    conditions = json.loads(q("conditions", "[]"))
                except ValueError:
                    return self._error(400, "bad_filter", "The catalog conditions in this address are not valid. Reset the filters and add them again.")
                return self._result(core.catalog_page, project=slug, query=q("q"), kind=q("kind"), sort=q("sort", "name"),
                                    order=q("order", "asc"), page=int(q("page", "1") or 1), per=int(q("per", "40") or 40),
                                    conditions=conditions)
            # Private project notes: a listing and single top-level .md files under <project>/docs/ (see core.read_project_doc).
            if rest == ["docs"]:
                return self._result(core.list_project_docs, project=slug)
            if rest[0] == "docs" and len(rest) == 2:
                return self._result(core.read_project_doc, project=slug, name=rest[1])
            if rest[0] == "catalog" and len(rest) == 2 and rest[1].isdigit():
                return self._result(core.catalog_entry, project=slug, index=int(rest[1]))
            return self._error(404, "not_found", "Unknown project route.")

        def do_POST(self):
            origin = f"http://127.0.0.1:{self.server.server_port}"
            if not self._host_allowed() or self.headers.get("Origin") != origin or self.headers.get("X-Kenogenesis-Token") != token:
                return self._error(403, "request_origin", "Reload the local browser page.")
            name = urlsplit(self.path).path.removeprefix("/api/")
            if name not in POST_OPERATIONS:
                return self._error(404, "not_found", "Unknown operation.")
            try:
                limit = 12 * 1024 * 1024 if name in UPLOADS else 1024 * 1024
                size = int(self.headers.get("Content-Length", "0"))
                if size > limit:
                    return self._error(413, "body_too_large", f"The request exceeds {limit // (1024 * 1024)} MiB.")
                if size <= 0 or self.headers.get("Content-Type") != "application/json":
                    raise ValueError(f"Use application/json with a body below {limit // (1024 * 1024)} MiB")
                params = json.loads(self.rfile.read(size))
                if not isinstance(params, dict):
                    raise ValueError("Expected a JSON object")
                if name.endswith("catalog_import") and "paths" in params:
                    raise ValueError("The browser sends selected file contents; server paths are not read")
                result = envelope(getattr(core, name), **params)
                return self._send(200 if result["ok"] else 409 if result["error"]["code"] in CONFLICTS else 400, result)
            except (ValueError, TypeError) as exc:
                return self._error(400, "bad_request", str(exc))

    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    server.daemon_threads = True
    return server


def serve(core, port=8766, open_browser=False):
    server = make_server(core, port)
    address = f"http://127.0.0.1:{server.server_port}/"
    print(f"KENOGENESIS: {address}", file=sys.stderr, flush=True)
    try:
        if open_browser:
            # Only the exact loopback address the Host and Origin guards accept is opened.
            import webbrowser
            try:
                if not webbrowser.open(address):
                    print("The browser could not be opened; use the address above.", file=sys.stderr, flush=True)
            except OSError:
                print("The browser could not be opened; use the address above.", file=sys.stderr, flush=True)
        server.serve_forever()
    except KeyboardInterrupt:
        pass  # Ctrl+C is the normal way to stop the local server.
    finally:
        server.server_close()
