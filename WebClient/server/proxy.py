#!/usr/bin/env python3
import http.server
import mimetypes
import os
from pathlib import Path
import socketserver

import requests

PORT = int(os.environ.get("PROXY_PORT", "8000"))
API_BASE = os.environ.get("APERTUS_URL", "http://127.0.0.1:9000").rstrip("/")
CLIENT_DIR = Path(__file__).resolve().parents[1] / "client"


class Handler(http.server.BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"  # nicer for streaming

    def do_GET(self):
        if self.path in ("/", "/index.html"):
            rel_path = "index.html"
        else:
            rel_path = self.path.lstrip("/")

        path = os.path.join(str(CLIENT_DIR), rel_path)

        if not os.path.isfile(path):
            self.send_response(404)
            self.end_headers()
            return

        try:
            with open(path, "rb") as f:
                content = f.read()
            content_type, _ = mimetypes.guess_type(path)
            if not content_type:
                content_type = "application/octet-stream"

            self.send_response(200)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(content)))
            self.end_headers()
            self.wfile.write(content)
        except ConnectionAbortedError:
            pass
        except Exception:
            try:
                self.send_response(500)
                self.end_headers()
            except Exception:
                pass

    def do_POST(self):
        if not self.path.startswith("/v1/"):
            self.send_response(404)
            self.end_headers()
            return

        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length)

        try:
            headers = {
                "Content-Type": self.headers.get("Content-Type", "application/json"),
            }
            auth = self.headers.get("Authorization")
            if auth:
                headers["Authorization"] = auth

            r = requests.post(
                f"{API_BASE}{self.path}",
                data=body,
                headers=headers,
                stream=True,
                timeout=(10, 300),
            )

            self.send_response(r.status_code)

            for k, v in r.headers.items():
                kl = k.lower()
                if kl in ("content-length", "transfer-encoding", "content-encoding", "connection"):
                    continue
                self.send_header(k, v)
            self.send_header("Connection", "close")
            self.end_headers()

            tail = b""
            try:
                for chunk in r.iter_content(chunk_size=8192):
                    if not chunk:
                        continue
                    try:
                        self.wfile.write(chunk)
                        self.wfile.flush()
                    except ConnectionAbortedError:
                        break
                    tail = (tail + chunk)[-32:]
                    if b"data: [DONE]" in tail:
                        break
            finally:
                r.close()
                self.close_connection = True

        except Exception as e:
            msg = f'{{"error":"{e}"}}'.encode("utf-8")
            try:
                self.send_response(500)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(msg)))
                self.end_headers()
                self.wfile.write(msg)
            except Exception:
                pass


class ThreadedHTTPServer(socketserver.ThreadingMixIn, http.server.HTTPServer):
    daemon_threads = True
    allow_reuse_address = True


if __name__ == "__main__":
    if not CLIENT_DIR.exists():
        raise SystemExit(f"[ERROR] Client dir not found: {CLIENT_DIR}")
    with ThreadedHTTPServer(("127.0.0.1", PORT), Handler) as httpd:
        url = f"http://127.0.0.1:{PORT}"
        print(f"Serving UI + proxy on {url}")
        httpd.serve_forever()
