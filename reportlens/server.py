"""Loopback-only GUI. Capability token, host checks and no external resources."""
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse
import hmac
import json
import mimetypes
import secrets
import threading
import uuid
import webbrowser

from .package import MAX_PACKAGE, save_package


def make_server(service, port=0):
    token = secrets.token_urlsafe(32)
    web_root = Path(__file__).parent / "web"

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_):
            pass  # Do not put capability tokens in access logs.

        def respond(self, data, mime="application/json", status=200, filename=None):
            if not isinstance(data, bytes):
                data = json.dumps(data, ensure_ascii=False).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", mime)
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("Referrer-Policy", "no-referrer")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Content-Security-Policy", "default-src 'self'; img-src 'self'; style-src 'self'; script-src 'self'; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'none'")
            if filename:
                self.send_header("Content-Disposition", f'attachment; filename="{filename}"')
            self.end_headers()
            try:
                self.wfile.write(data)
            except (BrokenPipeError, ConnectionResetError):
                pass

        def authorized(self):
            expected_host = f"127.0.0.1:{self.server.server_port}"
            if self.headers.get("Host") != expected_host:
                self.respond({"error": "Invalid local host"}, status=403); return False
            origin = self.headers.get("Origin")
            if origin and origin != f"http://{expected_host}":
                self.respond({"error": "Cross-origin access is disabled"}, status=403); return False
            query = parse_qs(urlparse(self.path).query)
            supplied = self.headers.get("X-ReportLens-Token", query.get("token", [""])[0])
            # Static CSS/JS contain no user data. Everything else needs a token.
            public_static = self.command == "GET" and urlparse(self.path).path in ("/app.js", "/style.css")
            if not public_static and not hmac.compare_digest(supplied, token):
                self.respond({"error": "Open the full local URL printed by ReportLens"}, status=403); return False
            return True

        def do_GET(self):
            if not self.authorized(): return
            path = urlparse(self.path).path
            try:
                if path in ("/", "/app.js", "/style.css"):
                    file = web_root / ("index.html" if path == "/" else path[1:])
                    self.respond(file.read_bytes(), {".html": "text/html; charset=utf-8", ".js": "text/javascript; charset=utf-8", ".css": "text/css; charset=utf-8"}[file.suffix])
                elif path == "/api/status":
                    self.respond({**service.state, "monitor": service.monitor, "has_repository": bool(service.repo)})
                elif path == "/api/versions":
                    versions = service.repo.versions(False) if service.repo else []
                    relevant = service.repo.versions() if service.repo else []
                    self.respond({"versions": versions, "defaults": relevant[:2]})
                elif path == "/api/manifest":
                    self.respond({**service.manifest, "session": service.state["generation"]} if service.manifest else None)
                elif path.startswith("/assets/"):
                    _, _, session, image_name = path.split("/", 3)
                    directory, _ = service.sessions[int(session)]
                    if not image_name.replace("-", "").replace(".", "").isalnum():
                        raise ValueError("Invalid image request")
                    file = directory / "assets" / image_name
                    if file.suffix != ".png" or not file.is_file():
                        raise ValueError("Page image is unavailable")
                    self.respond(file.read_bytes(), "image/png")
                elif path.startswith("/download/"):
                    session = int(parse_qs(urlparse(self.path).query).get("session", [service.state["generation"]])[0])
                    directory, _ = service.sessions[session]
                    if not directory: raise ValueError("No comparison is open")
                    kind = path.rsplit("/", 1)[-1]
                    if kind == "package":
                        file = directory / "download.reportlens"
                        if not file.is_file(): save_package(directory, file)
                        self.respond(file.read_bytes(), "application/zip", filename="comparison.reportlens")
                    elif kind in ("diff", "before", "after"):
                        file = directory / f"{kind}.pdf"
                        if not file.is_file(): raise ValueError("This package does not contain a diff PDF")
                        self.respond(file.read_bytes(), "application/pdf", filename=f"{kind}.pdf")
                    else:
                        raise ValueError("Unknown download")
                else:
                    self.respond({"error": "Not found"}, status=404)
            except Exception as error:
                self.respond({"error": str(error)}, status=400)

        def do_POST(self):
            if not self.authorized(): return
            path = urlparse(self.path).path
            try:
                length = int(self.headers.get("Content-Length", "0"))
                limit = MAX_PACKAGE if path == "/api/open" else 16384
                if length <= 0 or length > limit:
                    raise ValueError("Empty or oversized request")
                if path == "/api/open":
                    if service.state["busy"]: raise ValueError("Wait for the current comparison to finish")
                    uploads = service.root / "uploads"; uploads.mkdir(exist_ok=True)
                    file = uploads / f"{uuid.uuid4().hex}.reportlens"
                    with file.open("wb") as stream:
                        remaining = length
                        while remaining:
                            chunk = self.rfile.read(min(remaining, 1024*1024))
                            if not chunk: raise ValueError("Incomplete upload")
                            stream.write(chunk); remaining -= len(chunk)
                    def open_uploaded():
                        try: service.open_package(file)
                        finally: file.unlink(missing_ok=True)
                    service.execute(open_uploaded)
                else:
                    data = json.loads(self.rfile.read(length))
                    if path == "/api/compare":
                        before, after = data.get("before"), data.get("after")
                        if before is not None and not isinstance(before, str) or after is not None and not isinstance(after, str):
                            raise ValueError("Revisions must be strings")
                        service.execute(lambda: service.compare_git(before or None, after or None))
                    elif path == "/api/monitor":
                        if not service.repo: raise ValueError("No repository configured")
                        service.monitor = data.get("enabled") is True
                    else:
                        raise ValueError("Unknown action")
                self.respond({"ok": True})
            except Exception as error:
                self.respond({"error": str(error)}, status=400)

    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    server.daemon_threads = True
    server.url = f"http://127.0.0.1:{server.server_port}/?token={token}"
    return server


def serve(service, port=0, open_browser=True):
    server = make_server(service, port)
    print(f"ReportLens is ready: {server.url}", flush=True)
    print("Keep this process running for the GUI and commit monitoring. Ctrl+C stops it.", flush=True)
    threading.Thread(target=service.monitor_loop, daemon=True).start()
    if open_browser: webbrowser.open(server.url)
    try: server.serve_forever()
    except KeyboardInterrupt: pass
    finally:
        service.stop.set()
        server.server_close()
