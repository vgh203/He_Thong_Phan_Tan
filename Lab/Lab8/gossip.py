
import argparse
import copy
import json
import multiprocessing as mp
import random
import socket
import socketserver
import threading
import time
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs

N = 5                       # số replica (S1..S5)
HOST = "127.0.0.1"
BASE_PORT = 9001            # S1 -> 9001 ... S5 -> 9005
GOSSIP_INTERVAL = 2.0       # slide 37: mỗi 2 giây
DEFAULT_T_CLEANUP = 60      # slide 14: T_cleanup (giây)


# ----------------------------------------------------------------------------
# TCP RPC helper (mỗi request = 1 dòng JSON, 1 kết nối)
# ----------------------------------------------------------------------------
def rpc(port, msg, timeout=1.5):
    with socket.create_connection((HOST, port), timeout=timeout) as s:
        s.settimeout(timeout)
        s.sendall((json.dumps(msg) + "\n").encode())
        buf = b""
        while not buf.endswith(b"\n"):
            chunk = s.recv(65536)
            if not chunk:
                break
            buf += chunk
    return json.loads(buf.decode())


def call(i, msg, timeout=1.5):
    """Gọi replica S<i>. Trả None nếu không kết nối được."""
    try:
        return rpc(BASE_PORT + i - 1, msg, timeout)
    except Exception:
        return None


def ok(r):
    return bool(r) and r.get("ok")


# ----------------------------------------------------------------------------
# REPLICA (chạy trong tiến trình riêng)
# ----------------------------------------------------------------------------
def fmt_update(name, key, e):
    if e["is_tombstone"]:
        return f"[{name}] Memory State Updated -> key='{key}' TOMBSTONE (Ver {e['version']})"
    return f"[{name}] Memory State Updated -> key='{key}' val='{e['value']}' (Ver {e['version']})"


def newer(a, b):
    """Entry a có mới hơn entry b không? Version cao hơn thắng; hoà version thì
    tombstone thắng rồi so giá trị để mọi replica hội tụ cùng một kết quả."""
    if b is None:
        return True
    return (a["version"], a["is_tombstone"], str(a["value"])) > \
           (b["version"], b["is_tombstone"], str(b["value"]))


class Replica:
    def __init__(self, rid, logq):
        self.id = rid
        self.name = f"S{rid}"
        self.port = BASE_PORT + rid - 1
        self.store = {}     # key -> {value, version, is_tombstone, ts}
        self.lock = threading.RLock()
        self.alive = True
        self.gossip_on = True
        self.t_cleanup = DEFAULT_T_CLEANUP
        self.logq = logq

    def log(self, text, kind="replica"):
        self.logq.put((kind, text))

    def merge(self, incoming):
        changed = []
        with self.lock:
            for k, e in incoming.items():
                if newer(e, self.store.get(k)):
                    self.store[k] = dict(e)
                    changed.append((k, dict(e)))
        return changed

    # ---- Push-Pull anti-entropy (slide 11, 37) ----
    def gossip_once(self):
        if not self.alive:
            return
        q = random.choice([i for i in range(1, N + 1) if i != self.id])
        qn = f"S{q}"
        with self.lock:
            snapshot = copy.deepcopy(self.store)
        r = call(q, {"op": "SYNC", "store": snapshot})       # PUSH toàn bộ write set
        if not ok(r):
            self.log(f"[GOSSIP] {self.name} -> {qn} unreachable (down)", "idle")
            return
        mine = self.merge(r["diff"])                          # PULL phần peer có mới hơn
        theirs = r["changed_on_peer"]
        if mine or theirs:
            self.log(f"[GOSSIP] {self.name} initiates Push-Pull Anti-Entropy with {qn}...", "gossip")
            for k, e in theirs:
                self.log(fmt_update(qn, k, e))
            for k, e in mine:
                self.log(fmt_update(self.name, k, e))
        else:
            self.log(f"[GOSSIP] {self.name} <-> {qn} already in sync", "idle")

    # ---- Tombstone garbage collection (slide 14) ----
    def purge(self):
        now = time.time()
        with self.lock:
            dead = [k for k, e in self.store.items()
                    if e["is_tombstone"] and now - e["ts"] > self.t_cleanup]
            for k in dead:
                del self.store[k]
        for k in dead:
            self.log(f"[{self.name}] Tombstone purged key='{k}' (age > T_cleanup={self.t_cleanup:g}s)")

    def gossip_loop(self):
        time.sleep(random.uniform(0, GOSSIP_INTERVAL))
        while True:
            time.sleep(GOSSIP_INTERVAL)
            if self.alive and self.gossip_on:
                try:
                    self.gossip_once()
                except Exception as ex:
                    self.log(f"[{self.name}] gossip error: {ex}", "error")
            if self.alive:
                self.purge()

    # ---- Request dispatcher ----
    def handle(self, m):
        op = m.get("op")
        # --- admin ops (luôn trả lời, kể cả khi replica "DOWN") ---
        if op == "DUMP":
            with self.lock:
                return {"ok": True, "alive": self.alive, "gossip": self.gossip_on,
                        "store": copy.deepcopy(self.store)}
        if op == "SET_ALIVE":
            self.alive = bool(m["alive"])
            return {"ok": True}
        if op == "SET_GOSSIP":
            self.gossip_on = bool(m["on"])
            return {"ok": True}
        if op == "SET_CLEANUP":
            self.t_cleanup = float(m["t"])
            return {"ok": True}
        if op == "RESET":
            with self.lock:
                self.store.clear()
            self.alive = True
            return {"ok": True}
        if op == "GOSSIP_NOW":
            threading.Thread(target=self.gossip_once, daemon=True).start()
            return {"ok": True}
        # --- data ops ---
        if not self.alive:
            return {"error": "down"}
        if op == "GET":
            with self.lock:
                e = self.store.get(m["key"])
                return {"ok": True, "entry": dict(e) if e else None}
        if op == "VERSION":
            with self.lock:
                e = self.store.get(m["key"])
                return {"ok": True, "version": e["version"] if e else 0}
        if op == "PUT":
            self.merge({m["key"]: m["entry"]})
            return {"ok": True, "version": m["entry"]["version"]}
        if op == "SYNC":
            incoming = m["store"]
            changed = self.merge(incoming)
            with self.lock:
                diff = {k: e for k, e in self.store.items()
                        if k not in incoming or newer(e, incoming[k])}
            return {"ok": True, "diff": diff, "changed_on_peer": [[k, e] for k, e in changed]}
        return {"error": "unknown op"}


class _Handler(socketserver.StreamRequestHandler):
    def handle(self):
        try:
            resp = self.server.replica.handle(json.loads(self.rfile.readline()))
        except Exception as ex:
            resp = {"error": str(ex)}
        self.wfile.write((json.dumps(resp) + "\n").encode())


class _Server(socketserver.ThreadingTCPServer):
    allow_reuse_address = True
    daemon_threads = True


def run_replica(rid, logq):
    r = Replica(rid, logq)
    srv = _Server((HOST, r.port), _Handler)
    srv.replica = r
    threading.Thread(target=r.gossip_loop, daemon=True).start()
    srv.serve_forever()


# ----------------------------------------------------------------------------
# CLIENT PROXY + điều phối dashboard (tiến trình chính)
# ----------------------------------------------------------------------------
def names(ids):
    n = [f"S{i}" for i in ids]
    return n[0] if len(n) == 1 else ", ".join(n[:-1]) + " and " + n[-1]


class Cluster:
    def __init__(self, logq):
        self.logq = logq
        self.cfg = {"nr": 3, "nw": 3, "select": "sequential", "t_cleanup": DEFAULT_T_CLEANUP}
        self.logs, self.next_id = [], 1
        self.log_lock = threading.Lock()
        self.op_lock = threading.Lock()
        self.pending = {}   # key -> (version, is_tombstone) đang chờ gossip hội tụ

    # ---- logging ----
    def log(self, kind, text):
        with self.log_lock:
            self.logs.append({"id": self.next_id, "kind": kind, "text": text})
            self.next_id += 1
            del self.logs[:-2000]

    def start_threads(self):
        threading.Thread(target=self._drain, daemon=True).start()
        threading.Thread(target=self._monitor, daemon=True).start()

    def _drain(self):
        while True:
            kind, text = self.logq.get()
            self.log(kind, text)

    def _monitor(self):
        """Phát hiện khi mọi replica đã hội tụ (dòng [SYSTEM] ... converged ở slide 38)."""
        while True:
            time.sleep(1)
            if not self.pending:
                continue
            dumps = [call(i, {"op": "DUMP"}) for i in range(1, N + 1)]
            if any(not ok(d) or not d["alive"] for d in dumps):
                continue
            for key, (ver, tomb) in list(self.pending.items()):
                good = True
                for d in dumps:
                    e = d["store"].get(key)
                    if e is None:
                        good = good and tomb          # tombstone đã bị purge ở khắp nơi
                    else:
                        good = good and e["version"] >= ver
                if good and self.pending.get(key) == (ver, tomb):
                    del self.pending[key]
                    how = "Tombstone" if tomb else "Anti-Entropy"
                    self.log("system", f"[SYSTEM] All nodes successfully converged via {how} gossip.")

    # ---- helpers ----
    def order(self):
        ids = list(range(1, N + 1))
        if self.cfg["select"] == "random":
            random.shuffle(ids)
        return ids

    def stale_report(self, key, members, newv):
        groups, down = {}, []
        for i in (x for x in range(1, N + 1) if x not in members):
            r = call(i, {"op": "GET", "key": key})
            if not ok(r):
                down.append(i)
                continue
            v = r["entry"]["version"] if r["entry"] else 0
            if v < newv:
                groups.setdefault(v, []).append(i)
        parts = [f"{names(l)} {'is' if len(l) == 1 else 'are'} stale (Ver {v})"
                 for v, l in sorted(groups.items())]
        if down:
            parts.append(f"{names(down)} {'is' if len(down) == 1 else 'are'} down")
        return "; ".join(parts)

    # ---- Gifford write: đọc version từ write quorum, ghi version+1 ----
    def write(self, key, value, tombstone=False):
        nw = self.cfg["nw"]
        with self.op_lock:
            if tombstone:
                self.log("client", f"[CLIENT] Delete key='{key}' (NW={nw})")
            else:
                self.log("client", f"[CLIENT] Write key='{key}' val='{value}' (NW={nw})")
            members, vers = [], {}
            for i in self.order():
                if len(members) == nw:
                    break
                r = call(i, {"op": "VERSION", "key": key})
                if ok(r):
                    members.append(i)
                    vers[i] = r["version"]
            if len(members) < nw:
                msg = f"Write FAILED: write quorum not reached ({len(members)}/{nw} replicas available)"
                self.log("error", f"[SYSTEM] {msg}")
                return {"ok": False, "msg": msg}
            newv = max(vers.values()) + 1
            entry = {"value": None if tombstone else value, "version": newv,
                     "is_tombstone": tombstone, "ts": time.time()}
            acks = [i for i in members if ok(call(i, {"op": "PUT", "key": key, "entry": entry}))]
            if acks:
                self.log("replica", " | ".join(f"[S{i}] Write ACK Ver {newv}" for i in acks))
            if len(acks) < nw:
                msg = f"Write FAILED: only {len(acks)}/{nw} ACKs"
                self.log("error", f"[SYSTEM] {msg}")
                return {"ok": False, "msg": msg}
            if tombstone:
                self.log("client", f"[CLIENT] Delete key='{key}' -> Written as Tombstone (Ver {newv})")
            stale = self.stale_report(key, members, newv)
            if stale:
                self.log("system", f"[SYSTEM] Write Committed. {stale}.")
                self.pending[key] = (newv, tombstone)
            else:
                self.log("system", "[SYSTEM] Write Committed. All replicas up to date.")
            return {"ok": True, "version": newv,
                    "msg": f"{'Delete' if tombstone else 'Write'} committed on {names(acks)} (Ver {newv})"
                           + (f" - {stale}" if stale else "")}

    # ---- Gifford read: hỏi NR replica, trả object có version cao nhất ----
    def read(self, key):
        nr = self.cfg["nr"]
        with self.op_lock:
            self.log("client", f"[CLIENT] Read key='{key}' (NR={nr})")
            got = {}
            for i in self.order():
                if len(got) == nr:
                    break
                r = call(i, {"op": "GET", "key": key})
                if ok(r):
                    got[i] = r["entry"]
            if len(got) < nr:
                msg = f"Read FAILED: read quorum not reached ({len(got)}/{nr} replicas available)"
                self.log("error", f"[SYSTEM] {msg}")
                return {"ok": False, "msg": msg}
            ver = lambda e: e["version"] if e else 0
            self.log("replica", " | ".join(f"[S{i}] Read Ver {ver(e)}" for i, e in got.items()))
            best = None
            for e in got.values():
                if e and newer(e, best):
                    best = e
            bv = ver(best)
            old = [i for i, e in got.items() if ver(e) < bv]
            if old:
                self.log("system", f"[SYSTEM] Stale replica(s) in read quorum: "
                                   f"{', '.join(f'S{i} (Ver {ver(got[i])})' for i in old)} - highest version returned.")
            if best is None:
                msg = f"key='{key}' not found (Ver 0)"
            elif best["is_tombstone"]:
                msg = f"key='{key}' is DELETED (Tombstone Ver {bv})"
            else:
                msg = f"key='{key}' val='{best['value']}' (Ver {bv})"
            self.log("system", f"[SYSTEM] Read result: {msg}")
            return {"ok": True, "msg": msg, "version": bv}

    # ---- cấu hình / điều khiển ----
    def broadcast(self, msg):
        for i in range(1, N + 1):
            call(i, msg)

    def set_config(self, b):
        c = self.cfg
        c["nr"] = max(1, min(N, int(b.get("nr", c["nr"]))))
        c["nw"] = max(1, min(N, int(b.get("nw", c["nw"]))))
        c["select"] = b.get("select", c["select"]) if b.get("select") in ("sequential", "random") else c["select"]
        c["t_cleanup"] = max(1, float(b.get("t_cleanup", c["t_cleanup"])))
        self.broadcast({"op": "SET_CLEANUP", "t": c["t_cleanup"]})
        r1, r2 = c["nr"] + c["nw"] > N, c["nw"] > N / 2
        self.log("system", f"[SYSTEM] Config: NR={c['nr']}, NW={c['nw']} | "
                           f"Rule1 NR+NW>N: {'PASS' if r1 else 'FAIL'} | Rule2 NW>N/2: {'PASS' if r2 else 'FAIL'} "
                           f"| T_cleanup={c['t_cleanup']:g}s | selection={c['select']}")

    def set_gossip(self, on):
        self.broadcast({"op": "SET_GOSSIP", "on": on})
        self.log("system", f"[SYSTEM] Gossip {'RESUMED' if on else 'PAUSED'} on all replicas.")

    def set_alive(self, i, alive):
        call(i, {"op": "SET_ALIVE", "alive": alive})
        self.log("system", f"[SYSTEM] S{i} {'recovered (UP)' if alive else 'crashed (DOWN)'}.")

    def reset(self):
        self.broadcast({"op": "RESET"})
        self.pending.clear()
        self.log("system", "[SYSTEM] Cluster reset: all stores cleared, all replicas UP.")

    def demo(self):
        """Tái hiện đúng console trace ở slide 38."""
        self.reset()
        self.cfg.update(nr=3, nw=3, select="sequential")
        self.set_config({})
        self.set_gossip(True)
        time.sleep(0.5)
        self.write("user1", "Bob")
        self._wait("user1")
        time.sleep(1)
        self.write("user1", None, tombstone=True)
        self._wait("user1")

    def _wait(self, key, secs=40):
        for _ in range(secs):
            if key not in self.pending:
                return
            time.sleep(1)

    def state(self, since):
        reps = []
        for i in range(1, N + 1):
            d = call(i, {"op": "DUMP"})
            reps.append({"id": i, "name": f"S{i}", "port": BASE_PORT + i - 1,
                         "reachable": ok(d), "alive": ok(d) and d["alive"],
                         "gossip": ok(d) and d["gossip"], "store": d["store"] if ok(d) else {}})
        with self.log_lock:
            logs = [l for l in self.logs if l["id"] > since]
        return {"cfg": self.cfg, "n": N, "replicas": reps, "logs": logs, "now": time.time(),
                "gossip_interval": GOSSIP_INTERVAL}


# ----------------------------------------------------------------------------
# HTTP SERVER (dashboard)
# ----------------------------------------------------------------------------
def make_handler(cl):
    class H(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def _send(self, obj, ctype="application/json", code=200):
            data = obj if isinstance(obj, bytes) else json.dumps(obj).encode()
            self.send_response(code)
            self.send_header("Content-Type", ctype + "; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(data)

        def do_GET(self):
            u = urlparse(self.path)
            if u.path == "/":
                self._send(HTML.encode(), "text/html")
            elif u.path == "/api/state":
                self._send(cl.state(int(parse_qs(u.query).get("since", ["0"])[0])))
            else:
                self._send({"error": "not found"}, code=404)

        def do_POST(self):
            n = int(self.headers.get("Content-Length", 0))
            try:
                b = json.loads(self.rfile.read(n) or b"{}")
            except Exception:
                b = {}
            p, key = self.path, str(b.get("key", "")).strip()
            if p in ("/api/write", "/api/read", "/api/delete") and not key:
                return self._send({"ok": False, "msg": "Nhập key trước đã."})
            if p == "/api/write":
                res = cl.write(key, str(b.get("value", "")))
            elif p == "/api/delete":
                res = cl.write(key, None, tombstone=True)
            elif p == "/api/read":
                res = cl.read(key)
            elif p == "/api/config":
                cl.set_config(b); res = {"ok": True}
            elif p == "/api/node":
                cl.set_alive(int(b["id"]), bool(b["alive"])); res = {"ok": True}
            elif p == "/api/gossip":
                cl.set_gossip(bool(b["on"])); res = {"ok": True}
            elif p == "/api/gossip_now":
                targets = [int(b["id"])] if b.get("id") else range(1, N + 1)
                for i in targets:
                    call(i, {"op": "GOSSIP_NOW"})
                res = {"ok": True}
            elif p == "/api/reset":
                cl.reset(); res = {"ok": True}
            elif p == "/api/demo":
                threading.Thread(target=cl.demo, daemon=True).start(); res = {"ok": True}
            else:
                return self._send({"error": "not found"}, code=404)
            self._send(res)
    return H


HTML = r"""<!doctype html>
<html lang="vi"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Lab 08 - Gossip &amp; Quorum</title>
<style>
:root{--bg:#f3f4f8;--panel:#fff;--ink:#16203f;--mut:#69728f;--line:#d9dce8;--navy:#1b2a63;--red:#c4161c;
--ok:#177a43;--okbg:#dff3e7;--bad:#b3261e;--badbg:#fbe3e1;--warn:#8a5a00;--warnbg:#fdf0cf;--con:#0e1633}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--ink);font:15px/1.45 "Segoe UI",system-ui,sans-serif}
header{background:var(--navy);color:#fff;padding:14px 24px;display:flex;gap:18px;align-items:baseline;flex-wrap:wrap;border-bottom:4px solid var(--red)}
header h1{margin:0;font:700 20px Georgia,serif}
header span{color:#b9c2e6;font-size:13px}
main{display:grid;grid-template-columns:340px 1fr;gap:16px;padding:16px 24px;max-width:1500px;margin:auto}
@media(max-width:980px){main{grid-template-columns:1fr}}
section{background:var(--panel);border:1px solid var(--line);border-radius:6px;padding:14px 16px}
h2{margin:0 0 10px;font:700 15px Georgia,serif;color:var(--navy)}
label{display:block;font-size:13px;color:var(--mut);margin:8px 0 3px}
input,select{width:100%;padding:7px 9px;border:1px solid var(--line);border-radius:4px;font:inherit;background:#fff;color:var(--ink)}
input:focus,select:focus,button:focus-visible{outline:2px solid var(--navy);outline-offset:1px}
.row{display:flex;gap:8px}.row>*{flex:1}
button{padding:7px 12px;border:1px solid var(--navy);background:#fff;color:var(--navy);border-radius:4px;font:600 14px inherit;cursor:pointer}
button:hover{background:#eef1fb}button:disabled{opacity:.4;cursor:not-allowed}
button.p{background:var(--navy);color:#fff}button.p:hover{background:#26397f}
button.r{background:var(--red);border-color:var(--red);color:#fff}button.r:hover{background:#a31217}
.b{display:inline-block;padding:1px 8px;border-radius:10px;font-size:12px;font-weight:700}
.g{background:var(--okbg);color:var(--ok)}.rd{background:var(--badbg);color:var(--bad)}.w{background:var(--warnbg);color:var(--warn)}
#rules div{font-size:13.5px;margin:4px 0}
#warn{margin-top:8px;padding:7px 9px;background:var(--warnbg);color:var(--warn);border-radius:4px;font-size:13px}
#res{margin-top:10px;padding:8px 10px;border-radius:4px;font-size:13.5px;min-height:20px;background:#eef0f7;word-break:break-word}
#res.ok{background:var(--okbg);color:var(--ok)}#res.err{background:var(--badbg);color:var(--bad)}
.col{display:flex;flex-direction:column;gap:16px}
#replicas{display:grid;grid-template-columns:repeat(auto-fill,minmax(235px,1fr));gap:12px}
.rep{border:1px solid var(--line);border-top:4px solid var(--ok);border-radius:6px;padding:10px;background:#fff;display:flex;flex-direction:column;gap:8px}
.rep.down{border-top-color:var(--bad);background:#faf3f2}
.rh{display:flex;gap:8px;align-items:baseline}.rh small{color:var(--mut);flex:1}
table{width:100%;border-collapse:collapse;font-size:13px}
th{text-align:left;color:var(--mut);font-weight:600;border-bottom:1px solid var(--line);padding:2px 4px}
td{padding:4px;border-bottom:1px solid #eef0f6}
tr.stale td{background:var(--warnbg)}tr.tomb td{background:#f4e6e6}
.mut{color:var(--mut)}
.ra{display:flex;gap:6px}.ra button{flex:1;padding:5px 6px;font-size:13px}
#console{background:var(--con);color:#d7def5;border-radius:6px;padding:10px 12px;height:330px;overflow:auto;font:12.5px/1.55 Consolas,"Courier New",monospace}
#console div{white-space:pre-wrap;word-break:break-word}
.k-client{color:#7db4ff}.k-system{color:#6fe0a0}.k-gossip{color:#ffc857}.k-replica{color:#c9a8ff}.k-error{color:#ff7b72}.k-idle{color:#6b7599}
.bar{display:flex;gap:12px;align-items:center;margin-bottom:8px;flex-wrap:wrap;font-size:13px}
.bar label{display:flex;gap:6px;align-items:center;margin:0}.bar input{width:auto}
.legend{font-size:12.5px;color:var(--mut);margin-top:8px}
</style></head><body>
<header><h1>INT1405 · Lecture 08 Lab: Gossip &amp; Quorum KV Store</h1>
<span>5 replica (TCP) · Gifford quorum · Push-Pull Anti-Entropy · Tombstones</span></header>
<main>
<div class="col">
 <section><h2>Cấu hình Gifford Quorum (N = <span id="nN">5</span>)</h2>
  <div class="row"><div><label for="nr">Read quorum NR</label><input id="nr" type="number" min="1" max="5" value="3"></div>
  <div><label for="nw">Write quorum NW</label><input id="nw" type="number" min="1" max="5" value="3"></div></div>
  <label for="sel">Cách chọn replica vào quorum</label>
  <select id="sel"><option value="sequential">Tuần tự S1 → S5 (giống trace slide 38)</option><option value="random">Ngẫu nhiên</option></select>
  <label for="tc">T_cleanup của tombstone (giây)</label><input id="tc" type="number" min="1" value="60">
  <div class="row" style="margin-top:10px"><button class="p" onclick="applyCfg()">Áp dụng</button></div>
  <div id="rules" style="margin-top:10px"></div><div id="warn" hidden></div></section>
 <section><h2>Client proxy</h2>
  <label for="k">Key</label><input id="k" value="user1">
  <label for="v">Value</label><input id="v" value="Bob">
  <div class="row" style="margin-top:10px"><button class="p" onclick="act('write')">Write</button><button onclick="act('read')">Read</button><button class="r" onclick="act('delete')">Delete</button></div>
  <div id="res">Chưa có thao tác.</div></section>
 <section><h2>Điều khiển cluster</h2>
  <div class="row"><button id="gbtn" onclick="toggleGossip()">⏸ Tạm dừng Gossip</button><button onclick="gnow()">🔁 Gossip 1 vòng</button></div>
  <div class="row" style="margin-top:8px"><button class="p" onclick="post('/api/demo')">▶ Chạy demo slide 38</button><button onclick="doReset()">Reset</button></div>
  <div class="legend">Gossip tự chạy mỗi 2 giây. Tạm dừng gossip rồi Write để thấy replica nào bị stale; crash replica để thử fault tolerance.</div></section>
</div>
<div class="col">
 <section><h2>Replica S1..S5 <span class="mut" style="font-weight:400;font-size:13px">key → {value, version, is_tombstone}</span></h2>
  <div id="replicas"></div>
  <div class="legend">Hàng vàng = replica đang giữ version cũ (stale) hoặc chưa có key. Hàng đỏ nhạt = tombstone (kèm tuổi / T_cleanup).</div></section>
 <section><h2>Console trace log</h2>
  <div class="bar"><label><input type="checkbox" id="idle" onchange="renderLogs()"> Hiện gossip rảnh (đã đồng bộ)</label>
   <label><input type="checkbox" id="auto" checked> Tự cuộn</label><button onclick="allLogs=[];renderLogs()">Xoá màn hình</button></div>
  <div id="console"></div></section>
</div></main>
<script>
const $=id=>document.getElementById(id);
let since=0,cfg=null,dirty=false,allLogs=[],N=5;
const esc=s=>String(s).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
async function post(p,b){const r=await fetch(p,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(b||{})});const j=await r.json();tick();return j}
['nr','nw','sel','tc'].forEach(i=>$(i).addEventListener('input',()=>{dirty=true;rules()}));
function rules(){
 const nr=+$('nr').value,nw=+$('nw').value,r1=nr+nw>N,r2=nw>N/2;
 const bd=x=>`<span class="b ${x?'g':'rd'}">${x?'PASS':'FAIL'}</span>`;
 $('rules').innerHTML=`<div>Rule 1 (Read-Write): N<sub>R</sub>+N<sub>W</sub> &gt; N → ${nr}+${nw}=${nr+nw} ${r1?'&gt;':'≤'} ${N} ${bd(r1)}</div>
 <div>Rule 2 (Write-Write): N<sub>W</sub> &gt; N/2 → ${nw} ${r2?'&gt;':'≤'} ${N/2} ${bd(r2)}</div>
 <div>Write fault tolerance = N − N<sub>W</sub> = <b>${N-nw}</b> replica</div>
 <div>Read fault tolerance = N − N<sub>R</sub> = <b>${N-nr}</b> replica</div>`;
 const w=$('warn');w.hidden=r1&&r2;
 w.textContent=!r1?'Vi phạm Rule 1: read quorum có thể không giao với write quorum → đọc được dữ liệu cũ.':'Vi phạm Rule 2: hai write quorum có thể tách rời → ghi xung đột.';
}
async function applyCfg(){await post('/api/config',{nr:+$('nr').value,nw:+$('nw').value,select:$('sel').value,t_cleanup:+$('tc').value});dirty=false}
async function act(a){
 const j=await post('/api/'+a,{key:$('k').value,value:$('v').value});
 $('res').textContent=j.msg||'';$('res').className=j.ok?'ok':'err';
}
async function toggleGossip(){await post('/api/gossip',{on:$('gbtn').dataset.on!=='1'})}
const gnow=id=>post('/api/gossip_now',id?{id}:{});
const node=(id,alive)=>post('/api/node',{id,alive});
async function doReset(){await post('/api/reset');allLogs=[];renderLogs()}
function card(r,keys,maxv,now){
 const rows=keys.map(k=>{const e=r.store[k];
  if(!e)return `<tr class="stale"><td>${esc(k)}</td><td class="mut">(chưa có)</td><td>v0</td><td><span class="b w">stale</span></td></tr>`;
  const stale=e.version<maxv[k];
  const val=e.is_tombstone?`<b style="color:var(--bad)">DELETED</b><br><small class="mut">${Math.round(now-e.ts)}s / ${cfg.t_cleanup}s</small>`:esc(e.value);
  return `<tr class="${stale?'stale':e.is_tombstone?'tomb':''}"><td>${esc(k)}</td><td>${val}</td><td>v${e.version}</td><td>${stale?'<span class="b w">stale</span>':'<span class="b g">fresh</span>'}</td></tr>`}).join('')
  ||'<tr><td colspan="4" class="mut">(trống)</td></tr>';
 return `<div class="rep ${r.alive?'':'down'}"><div class="rh"><b>${r.name}</b><small>TCP :${r.port}</small><span class="b ${r.alive?'g':'rd'}">${r.alive?'UP':'DOWN'}</span></div>
 <table><tr><th>Key</th><th>Value</th><th>Ver</th><th></th></tr>${rows}</table>
 <div class="ra"><button onclick="node(${r.id},${!r.alive})">${r.alive?'💥 Crash':'♻ Recover'}</button><button onclick="gnow(${r.id})" ${r.alive?'':'disabled'}>🔁 Gossip</button></div></div>`}
function renderLogs(){
 const c=$('console'),show=$('idle').checked,near=c.scrollHeight-c.scrollTop-c.clientHeight<60;
 c.innerHTML=allLogs.filter(l=>show||l.kind!=='idle').map(l=>`<div class="k-${l.kind}">${esc(l.text)}</div>`).join('');
 if($('auto').checked&&near||allLogs.length<2)c.scrollTop=c.scrollHeight}
async function tick(){
 try{
  const s=await (await fetch('/api/state?since='+since)).json();
  cfg=s.cfg;N=s.n;$('nN').textContent=N;
  if(!dirty){$('nr').value=cfg.nr;$('nw').value=cfg.nw;$('sel').value=cfg.select;$('tc').value=cfg.t_cleanup}
  rules();
  const keys=[...new Set(s.replicas.flatMap(r=>Object.keys(r.store)))].sort(),maxv={};
  s.replicas.forEach(r=>{for(const k in r.store)maxv[k]=Math.max(maxv[k]||0,r.store[k].version)});
  $('replicas').innerHTML=s.replicas.map(r=>card(r,keys,maxv,s.now)).join('');
  const on=s.replicas.some(r=>r.gossip);$('gbtn').dataset.on=on?'1':'0';
  $('gbtn').textContent=on?'⏸ Tạm dừng Gossip':'▶ Bật Gossip';
  if(s.logs.length){allLogs=allLogs.concat(s.logs).slice(-1500);since=s.logs[s.logs.length-1].id;renderLogs()}
 }catch(e){}
}
tick();setInterval(tick,1000);
</script></body></html>
"""


# ----------------------------------------------------------------------------
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8080, help="cổng dashboard (mặc định 8080)")
    ap.add_argument("--no-browser", action="store_true")
    a = ap.parse_args()

    logq = mp.Queue()
    procs = [mp.Process(target=run_replica, args=(i, logq), daemon=True) for i in range(1, N + 1)]
    for p in procs:
        p.start()
    time.sleep(0.8)

    cl = Cluster(logq)
    cl.start_threads()
    cl.log("system", f"[SYSTEM] {N} replica processes started (S1..S{N}, TCP ports {BASE_PORT}-{BASE_PORT + N - 1}).")
    cl.set_config({})
    httpd = ThreadingHTTPServer((HOST, a.port), make_handler(cl))
    url = f"http://localhost:{a.port}"
    print(f"\n  Dashboard: {url}   (Ctrl+C để dừng)\n")
    if not a.no_browser:
        threading.Timer(0.5, lambda: webbrowser.open(url)).start()
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        for p in procs:
            p.terminate()


if __name__ == "__main__":
    mp.freeze_support()
    main()
