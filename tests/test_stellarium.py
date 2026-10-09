"""Stellarium pointing (pyoccult.stellarium): the Remote Control requests (location, time as JD UT with the clock
stopped, J2000 view vector, field), against a small local HTTP server; and a clean failure without Stellarium."""
import sys, os, json, threading, urllib.parse
from http.server import BaseHTTPRequestHandler, HTTPServer
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'src'))
from pyoccult import stellarium as S, urls as U

got = []
class H(BaseHTTPRequestHandler):
    def do_POST(self):
        n = int(self.headers.get("Content-Length", 0))
        got.append((self.path, dict(urllib.parse.parse_qsl(self.rfile.read(n).decode()))))
        self.send_response(200); self.end_headers(); self.wfile.write(b"ok")
    def log_message(self, *a): pass
srv = HTTPServer(("127.0.0.1", 0), H)
threading.Thread(target=srv.serve_forever, daemon=True).start()
U.URL_STELLARIUM_API = f"http://127.0.0.1:{srv.server_port}/api"

ok, msg = S.show(90.0, 0.0, "2026-10-15T03:13:07", 0.5, lat=47.0, lon=9.6, ele=958)
assert ok, msg
paths = [p for p, _ in got]
assert paths == ["/api/location/setlocationfields", "/api/main/time", "/api/main/view", "/api/main/fov"], paths
f = dict(got)
assert f["/api/location/setlocationfields"]["latitude"] == "47.000000" and f["/api/location/setlocationfields"]["altitude"] == "958"
assert abs(float(f["/api/main/time"]["time"]) - 2461328.6341088) < 1e-6 and f["/api/main/time"]["timerate"] == "0"
v = json.loads(f["/api/main/view"]["j2000"])
assert abs(v[0]) < 1e-9 and abs(v[1] - 1) < 1e-9 and abs(v[2]) < 1e-9, v
assert f["/api/main/fov"]["fov"] == "0.5000"
got.clear()
assert S.show(90.0, 0.0, "2026-10-15T03:13:07", set_location=False, lat=47.0, lon=9.6)[0] and got[0][0] == "/api/main/time"
srv.shutdown(); srv.server_close()
ok, msg = S.show(90.0, 0.0, "2026-10-15T03:13:07")                  # nobody listening: a message, no exception
assert not ok and "not reachable" in msg, msg
assert not S.show(90.0, 0.0, "not a time")[0]
print("STELLARIUM TESTS PASSED")
