"""
ChordNode — core implementation of the Chord DHT protocol.

Key operations
--------------
* find_successor(id)   – O(log N) routing via finger table
* join(ip, port)       – join an existing ring (or create a new one)
* stabilize()          – periodic ring maintenance
* fix_fingers()        – periodic finger-table repair
* store(key, value)    – insert key-value into the DHT
* lookup(key)          – retrieve a value from the DHT
* send_message(name, text) – discover a node by name and message it
"""
from __future__ import annotations

import json
import logging
import random
import socket
import threading
import time
from typing import Optional

from .config import (M, RING_SIZE,
                     STABILIZE_INTERVAL, FIX_FINGERS_INTERVAL,
                     CHECK_PRED_INTERVAL)
from .finger_table import FingerTable, NodeInfo
from .network import send_rpc, _recv_exact
from .utils import hash_key, node_id_from_address, in_range

logger = logging.getLogger(__name__)


class ChordNode:
    # ──────────────────────────────────────────────────────
    # Construction
    # ──────────────────────────────────────────────────────
    def __init__(self, ip: str, port: int, name: str = ""):
        self.ip   = ip
        self.port = port
        self.name = name
        self.id   = node_id_from_address(ip, port)

        self.finger_table  = FingerTable(self.id)
        self.predecessor: Optional[NodeInfo] = None
        self.data_store: dict[str, object] = {}

        self._lock    = threading.RLock()
        self._running = False

        logger.info("Node created  id=%d  %s:%d  name=%s",
                    self.id, ip, port, name)

    # ── Convenience properties ─────────────────────────────
    @property
    def info(self) -> NodeInfo:
        return NodeInfo(id=self.id, ip=self.ip,
                        port=self.port, name=self.name)

    @property
    def successor(self) -> Optional[NodeInfo]:
        return self.finger_table.successor

    @successor.setter
    def successor(self, value: Optional[NodeInfo]):
        self.finger_table.successor = value

    # ──────────────────────────────────────────────────────
    # Chord Core
    # ──────────────────────────────────────────────────────
    def find_successor(self, key_id: int) -> NodeInfo:
        """
        Return the node responsible for *key_id*.
        Routing is O(log N) thanks to the finger table.
        """
        with self._lock:
            succ = self.successor

        # Single-node ring or null successor → we are responsible
        if succ is None or succ.id == self.id:
            return self.info

        # id falls in (self.id, succ.id]  → succ is the answer
        if in_range(key_id, self.id, succ.id, include_b=True):
            return succ

        # Ask the closest preceding finger to continue the search
        n0 = self._closest_preceding_node(key_id)
        if n0.id == self.id:
            return succ   # prevent infinite loop

        resp = send_rpc(n0.ip, n0.port,
                        {"type": "FIND_SUCCESSOR", "id": key_id})
        if "error" in resp or resp.get("node") is None:
            return succ   # fall back to direct successor
        return NodeInfo.from_dict(resp["node"])

    def _closest_preceding_node(self, key_id: int) -> NodeInfo:
        """Walk the finger table backwards to find the best forwarder."""
        with self._lock:
            for i in range(M - 1, -1, -1):
                f = self.finger_table[i]
                if f and in_range(f.id, self.id, key_id, include_b=False):
                    return f
        return self.info

    # ── Ring join ──────────────────────────────────────────
    def join(self, bootstrap_ip: str = None, bootstrap_port: int = None):
        """
        Join the Chord ring.
        If no bootstrap address is given, create a new single-node ring.
        After joining, immediately initialise ALL finger table entries so
        the ring is usable without waiting for fix_fingers() cycles.
        """
        if bootstrap_ip is None:
            # First node: the whole ring is just us
            for i in range(M):
                self.finger_table[i] = self.info
            self.predecessor = None
            logger.info("Node %d: created new ring", self.id)
        else:
            resp = send_rpc(bootstrap_ip, bootstrap_port,
                            {"type": "FIND_SUCCESSOR", "id": self.id})
            if "error" in resp:
                raise RuntimeError(
                    f"Cannot join ring via {bootstrap_ip}:{bootstrap_port}"
                    f" — {resp['error']}")
            self.successor  = NodeInfo.from_dict(resp["node"])
            self.predecessor = None
            logger.info("Node %d: joined ring, successor=%d",
                        self.id, self.successor.id)
            # Initialise remaining fingers immediately via bootstrap node
            for i in range(1, M):
                start = self.finger_table.starts[i]
                r = send_rpc(bootstrap_ip, bootstrap_port,
                             {"type": "FIND_SUCCESSOR", "id": start})
                if "error" not in r and r.get("node"):
                    self.finger_table[i] = NodeInfo.from_dict(r["node"])

    # ── Stabilisation ──────────────────────────────────────
    def stabilize(self):
        """
        Verify our immediate successor and tell it about us.
        Called periodically.
        """
        with self._lock:
            succ = self.successor

        if succ is None or succ.id == self.id:
            return

        resp = send_rpc(succ.ip, succ.port, {"type": "GET_PREDECESSOR"})
        if "error" not in resp and resp.get("node"):
            x = NodeInfo.from_dict(resp["node"])
            if in_range(x.id, self.id, succ.id, include_b=False):
                with self._lock:
                    self.successor = x
                    succ = x

        send_rpc(succ.ip, succ.port,
                 {"type": "NOTIFY", "node": self.info.to_dict()})

    def notify(self, candidate: NodeInfo):
        """
        *candidate* believes it might be our predecessor.
        Accept it if it's a better fit.
        """
        with self._lock:
            pred = self.predecessor

        if pred is None or in_range(candidate.id, pred.id,
                                    self.id, include_b=False):
            with self._lock:
                self.predecessor = candidate
            logger.debug("Node %d: predecessor → %d", self.id, candidate.id)

    def fix_fingers(self):
        """Refresh fingers sequentially (round-robin) each call."""
        if not hasattr(self, "_fix_finger_idx"):
            self._fix_finger_idx = 1
        i = self._fix_finger_idx
        self._fix_finger_idx = (i % (M - 1)) + 1   # cycles 1..M-1
        with self._lock:
            start = self.finger_table.starts[i]
        new_succ = self.find_successor(start)
        if new_succ:
            with self._lock:
                self.finger_table[i] = new_succ

    def check_predecessor(self):
        """Drop predecessor if it stops responding (fault detection)."""
        with self._lock:
            pred = self.predecessor
        if pred is None:
            return
        resp = send_rpc(pred.ip, pred.port, {"type": "PING"}, timeout=2.0)
        if "error" in resp:
            with self._lock:
                self.predecessor = None
            logger.info("Node %d: predecessor %d unreachable, cleared",
                        self.id, pred.id)

    # ──────────────────────────────────────────────────────
    # DHT Key-Value Store
    # ──────────────────────────────────────────────────────
    def store(self, key: str, value: object):
        """Insert (key → value) into the DHT at the responsible node."""
        key_id      = hash_key(key)
        responsible = self.find_successor(key_id)

        if responsible.id == self.id:
            with self._lock:
                self.data_store[key] = value
            logger.info("Node %d: stored '%s'", self.id, key)
        else:
            send_rpc(responsible.ip, responsible.port,
                     {"type": "STORE", "key": key, "value": value})

    def lookup(self, key: str) -> Optional[object]:
        """Retrieve the value for *key* from the DHT, or None."""
        key_id      = hash_key(key)
        responsible = self.find_successor(key_id)

        if responsible.id == self.id:
            with self._lock:
                return self.data_store.get(key)
        else:
            resp = send_rpc(responsible.ip, responsible.port,
                            {"type": "LOOKUP", "key": key})
            return resp.get("value") if "error" not in resp else None

    # ──────────────────────────────────────────────────────
    # Registration & Messaging
    # ──────────────────────────────────────────────────────
    def register(self):
        """Register this node's name → address mapping in the DHT."""
        if self.name:
            self.store(f"node:{self.name}", self.info.to_dict())
            logger.info("Node '%s' registered in DHT", self.name)

    def send_message(self, target_name: str, content: str) -> bool:
        """
        Look up *target_name* in the DHT, then send it a MESSAGE.
        Works even if the target's IP has changed (fault-tolerant).
        Steps:
          1. DHT lookup("node:<name>") → get current address
          2. Direct TCP MESSAGE to that address
        """
        record = self.lookup(f"node:{target_name}")
        if not record:
            print(f"[!] Node '{target_name}' not found in DHT.")
            return False

        target = NodeInfo.from_dict(record)
        logger.info("Sending message to '%s' at %s:%d",
                    target_name, target.ip, target.port)
        resp = send_rpc(target.ip, target.port, {
            "type":    "MESSAGE",
            "from":    self.name or str(self.id),
            "content": content,
        })
        if "error" in resp:
            logger.warning("Message to '%s' failed: %s",
                           target_name, resp["error"])
        return "error" not in resp

    # ──────────────────────────────────────────────────────
    # Lifecycle
    # ──────────────────────────────────────────────────────
    def start(self,
              bootstrap_ip: str = None,
              bootstrap_port: int = None):
        """Start the node: join the ring, register, launch threads."""
        self._running = True
        self.join(bootstrap_ip, bootstrap_port)
        self.register()

        threading.Thread(target=self._server_loop,
                         daemon=True, name=f"server-{self.id}").start()
        threading.Thread(target=self._maintenance_loop,
                         daemon=True, name=f"maint-{self.id}").start()

        logger.info("Node %d online at %s:%d", self.id, self.ip, self.port)

    def stop(self):
        self._running = False

    # ──────────────────────────────────────────────────────
    # TCP Server
    # ──────────────────────────────────────────────────────
    def _server_loop(self):
        srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        srv.bind((self.ip, self.port))
        srv.listen(20)
        srv.settimeout(1.0)
        logger.info("Node %d: listening on %s:%d", self.id, self.ip, self.port)

        while self._running:
            try:
                conn, _ = srv.accept()
                threading.Thread(target=self._handle,
                                 args=(conn,), daemon=True).start()
            except socket.timeout:
                continue
            except Exception as exc:
                if self._running:
                    logger.error("Server error: %s", exc)
        srv.close()

    def _handle(self, conn: socket.socket):
        """Handle one incoming RPC request."""
        try:
            raw_len = _recv_exact(conn, 4)
            if not raw_len:
                return
            length   = int.from_bytes(raw_len, "big")
            raw_body = _recv_exact(conn, length)
            if not raw_body:
                return
            msg  = json.loads(raw_body.decode("utf-8"))
            try:
                resp = self._dispatch(msg)
            except Exception as dispatch_exc:
                logger.error("Dispatch error for %s: %s",
                             msg.get("type"), dispatch_exc)
                resp = {"error": str(dispatch_exc)}
            payload = json.dumps(resp).encode("utf-8")
            conn.sendall(len(payload).to_bytes(4, "big") + payload)
        except Exception as exc:
            logger.debug("Handle error: %s", exc)
        finally:
            try:
                conn.close()
            except Exception:
                pass

    def _dispatch(self, msg: dict) -> dict:
        """Route an incoming RPC to the correct handler."""
        t = msg.get("type")

        if t == "FIND_SUCCESSOR":
            node = self.find_successor(msg["id"])
            return {"node": node.to_dict()}

        elif t == "GET_PREDECESSOR":
            with self._lock:
                pred = self.predecessor
            return {"node": pred.to_dict() if pred else None}

        elif t == "NOTIFY":
            self.notify(NodeInfo.from_dict(msg["node"]))
            return {"status": "ok"}

        elif t == "STORE":
            with self._lock:
                self.data_store[msg["key"]] = msg["value"]
            return {"status": "ok"}

        elif t == "LOOKUP":
            with self._lock:
                val = self.data_store.get(msg["key"])
            return {"value": val}

        elif t == "MESSAGE":
            sender  = msg.get("from", "?")
            content = msg.get("content", "")
            try:
                print(f"\n  [MSG] [{sender}]: {content}\n", flush=True)
            except Exception:
                pass
            return {"status": "ok"}

        elif t == "PING":
            return {"status": "pong", "id": self.id}

        elif t == "GET_INFO":
            with self._lock:
                return {
                    "id":          self.id,
                    "name":        self.name,
                    "ip":          self.ip,
                    "port":        self.port,
                    "successor":   self.successor.to_dict()
                                   if self.successor else None,
                    "predecessor": self.predecessor.to_dict()
                                   if self.predecessor else None,
                    "finger_table": self.finger_table.display(),
                    "keys":        list(self.data_store.keys()),
                }

        else:
            return {"error": f"unknown type: {t}"}

    # ──────────────────────────────────────────────────────
    # Maintenance Loop
    # ──────────────────────────────────────────────────────
    def _maintenance_loop(self):
        counters = {"stab": 0, "fix": 0, "pred": 0}
        while self._running:
            time.sleep(1)
            counters["stab"]  += 1
            counters["fix"]   += 1
            counters["pred"]  += 1

            if counters["stab"] >= STABILIZE_INTERVAL:
                try:
                    self.stabilize()
                except Exception as exc:
                    logger.debug("stabilize error: %s", exc)
                counters["stab"] = 0

            if counters["fix"] >= FIX_FINGERS_INTERVAL:
                try:
                    self.fix_fingers()
                except Exception as exc:
                    logger.debug("fix_fingers error: %s", exc)
                counters["fix"] = 0

            if counters["pred"] >= CHECK_PRED_INTERVAL:
                try:
                    self.check_predecessor()
                except Exception as exc:
                    logger.debug("check_predecessor error: %s", exc)
                counters["pred"] = 0

    # ──────────────────────────────────────────────────────
    # Status display
    # ──────────────────────────────────────────────────────
    def print_status(self):
        with self._lock:
            succ = self.successor
            pred = self.predecessor
            ft   = self.finger_table.display()
            keys = list(self.data_store.keys())

        print()
        print("=" * 60)
        print(f"  Node  : '{self.name}'  (ID = {self.id})")
        print(f"  Addr  : {self.ip}:{self.port}")
        print(f"  Succ  : {succ}")
        print(f"  Pred  : {pred}")
        print()
        print("  Finger Table (O(log N) routing):")
        print(ft)
        print()
        print(f"  DHT keys stored here: {keys}")
        print("=" * 60)
        print()
