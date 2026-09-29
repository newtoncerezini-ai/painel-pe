#!/usr/bin/env python3
# proxy_tse.py — Proxy CORS read-only para a CDN de resultados do TSE
# Uso: python3 proxy_tse.py [porta]   (padrão 8765)
# Rotas: GET  /tse/oficial/<path>  → repassa https://resultados.tse.jus.br/oficial/<path>
#        OPTIONS                    → preflight CORS
# Segurança: somente GET, caminho restrito a ^oficial/[A-Za-z0-9._\-/]+ , sem query string.
# Repassa ETag/Last-Modified e If-None-Match (lógica 304 preservada).
import os, re, sys, urllib.request, urllib.error
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

TSE_ORIGIN = os.environ.get("TSE_ORIGIN", "https://resultados.tse.jus.br")
PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 8765
PATH_OK = re.compile(r"^oficial/[A-Za-z0-9._\-/]+$")
CORS = {
    "Access-Control-Allow-Origin": "*",
    "Access-Control-Allow-Methods": "GET",
    "Access-Control-Allow-Headers": "If-None-Match",
    "Access-Control-Expose-Headers": "ETag, Last-Modified",
    "Cache-Control": "no-store",
}
PASS_HEADERS = ("Content-Type", "ETag", "Last-Modified")


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def _cors(self):
        for k, v in CORS.items():
            self.send_header(k, v)

    def do_OPTIONS(self):
        self.send_response(204)
        self._cors()
        self.send_header("Content-Length", "0")
        self.end_headers()

    def _method_not_allowed(self):
        self._err(405, "somente GET/OPTIONS")

    do_HEAD = _method_not_allowed
    do_POST = _method_not_allowed
    do_PUT = _method_not_allowed
    do_DELETE = _method_not_allowed

    def do_GET(self):
        path = self.path.split("?")[0]
        if not path.startswith("/tse/"):
            self._err(404, "rota invalida")
            return
        sub = path[len("/tse/"):]
        if not PATH_OK.match(sub):
            self._err(403, "caminho nao permitido")
            return
        url = f"{TSE_ORIGIN}/{sub}"
        headers = {"User-Agent": "painel-apuracao-proxy/1.0"}
        inm = self.headers.get("If-None-Match")
        if inm:
            headers["If-None-Match"] = inm
        try:
            req = urllib.request.Request(url, headers=headers)
            try:
                resp = urllib.request.urlopen(req, timeout=15)
                body, status, rh = resp.read(), resp.status, resp.headers
            except urllib.error.HTTPError as e:
                body, status, rh = (e.read() or b""), e.code, e.headers
        except Exception as e:
            self._err(502, f"upstream indisponivel: {type(e).__name__}")
            return
        self.send_response(status)
        self._cors()
        for h in PASS_HEADERS:
            if rh.get(h):
                self.send_header(h, rh[h])
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        if status != 304:
            self.wfile.write(body)
        print(f"[{status}] {sub}{' (304 via If-None-Match)' if status == 304 else ''}", flush=True)

    def _err(self, code, msg):
        b = msg.encode()
        self.send_response(code)
        self._cors()
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.send_header("Content-Length", str(len(b)))
        self.end_headers()
        self.wfile.write(b)

    def log_message(self, *a):
        pass


if __name__ == "__main__":
    srv = ThreadingHTTPServer(("0.0.0.0", PORT), Handler)
    print(f"proxy TSE ativo na porta {PORT} -> {TSE_ORIGIN}", flush=True)
    srv.serve_forever()