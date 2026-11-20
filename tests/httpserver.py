# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Kokou Bernard KPEDZI
"""Petit serveur HTTP local pour les tests : sert des octets fixes, avec ou sans Range."""
import re
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

BLOCK = 64 * 1024


def serve(data, ranges=True, delay=0.0, headers=None, seen=None, max_concurrent=None,
          throttle_first=0, retry_after=None, encoding=None):
    """Démarre un serveur ; retourne (url_de_base, arret).

    `seen` : liste où sont ajoutés les en-têtes de chaque requête reçue.
    `max_concurrent` : au-delà, les requêtes simultanées reçoivent 403 (anti-aspiration).
    `throttle_first` : les N premières requêtes reçoivent 429 (avec `retry_after` si fourni).
    `encoding` : valeur de Content-Encoding annoncée (sans compresser : serveur fautif).
    """
    state = {"active": 0, "count": 0}
    guard = threading.Lock()

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def refuse(self, code, extra=None):
            self.send_response(code)
            for k, v in (extra or {}).items():
                self.send_header(k, v)
            self.send_header("Content-Length", "0")
            self.end_headers()

        def do_GET(self):
            if seen is not None:
                seen.append(dict(self.headers.items()))
            with guard:
                state["count"] += 1
                index = state["count"]
                state["active"] += 1
                over = max_concurrent is not None and state["active"] > max_concurrent
            try:
                self.respond(index, over)
            finally:
                with guard:
                    state["active"] -= 1

        def respond(self, index, over):
            if index <= throttle_first:
                extra = {"Retry-After": str(retry_after)} if retry_after is not None else {}
                return self.refuse(429, extra)
            if over:
                return self.refuse(403)
            start, end = 0, len(data) - 1
            m = re.match(r"bytes=(\d+)-(\d*)$", self.headers.get("Range", ""))
            if ranges and m:
                start = int(m.group(1))
                end = min(int(m.group(2)) if m.group(2) else end, len(data) - 1)
                self.send_response(206)
                self.send_header("Content-Range", f"bytes {start}-{end}/{len(data)}")
                self.send_header("Accept-Ranges", "bytes")
            else:
                self.send_response(200)
            self.send_header("Content-Length", str(end - start + 1))
            self.send_header("Content-Type", "application/octet-stream")
            if encoding:
                self.send_header("Content-Encoding", encoding)
            for k, v in (headers or {}).items():
                self.send_header(k, v)
            self.end_headers()
            pos = start
            try:
                while pos <= end:
                    chunk = data[pos:min(pos + BLOCK, end + 1)]
                    self.wfile.write(chunk)
                    pos += len(chunk)
                    if delay:
                        time.sleep(delay)
            except (BrokenPipeError, ConnectionResetError):
                pass

    srv = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    srv.daemon_threads = True
    threading.Thread(target=srv.serve_forever, daemon=True).start()

    def stop():
        srv.shutdown()
        srv.server_close()

    return f"http://127.0.0.1:{srv.server_address[1]}", stop
