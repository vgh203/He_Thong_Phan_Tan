"""
server.py
Key Server (Key Graph Controller) hosting in-memory LKH Binary Tree and ABAC Engine.
Exposes a TCP socket server for group client nodes to connect, join, leave, and publish multicast messages.
"""

import socket
import threading
import json
import logging
from typing import Dict, Any, Optional, List, Tuple
from datetime import datetime

from crypto_utils import (
    encrypt_aes_gcm,
    decrypt_aes_gcm,
    key_to_hex,
    hex_to_key,
    format_key_short
)
from lkh_tree import LKHTree
from abac_engine import ABACPolicyEngine

# Configure clean logger format matching slide expectations
logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger("KeyServer")

class KeyServer:
    def __init__(self, host: str = "127.0.0.1", port: int = 9999, num_members: int = 8):
        self.host: str = host
        self.port: int = port
        self.num_members: int = num_members

        self.tree: LKHTree = LKHTree(num_members=num_members)
        self.abac_engine: ABACPolicyEngine = ABACPolicyEngine()

        self.server_socket: Optional[socket.socket] = None
        self.is_running: bool = False

        # Active client sockets: client_id -> (socket, addr, role)
        self.clients_lock = threading.Lock()
        self.connected_clients: Dict[str, Dict[str, Any]] = {}

        # Log history for dashboard / reporting
        self.logs: List[str] = []

        self._log(f"[KEY_SERVER] LKH Binary Tree Initialized (N={self.num_members} Members, Height h={self.tree.height}).")

    def _log(self, msg: str):
        self.logs.append(msg)
        print(msg)

    def start(self):
        """Start the TCP server socket listener."""
        self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.server_socket.bind((self.host, self.port))
        self.server_socket.listen(16)
        self.is_running = True
        logger.info(f"[KEY_SERVER] TCP Socket Server listening on {self.host}:{self.port}")

        listener_thread = threading.Thread(target=self._listen_loop, daemon=True)
        listener_thread.start()

    def stop(self):
        """Stop the TCP server."""
        self.is_running = False
        if self.server_socket:
            try:
                self.server_socket.close()
            except Exception:
                pass
        with self.clients_lock:
            for cid, data in self.connected_clients.items():
                try:
                    data["socket"].close()
                except Exception:
                    pass
            self.connected_clients.clear()
        logger.info("[KEY_SERVER] Key Server stopped.")

    def _listen_loop(self):
        while self.is_running:
            try:
                client_sock, addr = self.server_socket.accept()
                t = threading.Thread(target=self._handle_client_connection, args=(client_sock, addr), daemon=True)
                t.start()
            except Exception:
                if not self.is_running:
                    break

    def _send_json(self, sock: socket.socket, data: Dict[str, Any]):
        msg = (json.dumps(data) + "\n").encode("utf-8")
        sock.sendall(msg)

    def _broadcast_to_active(self, data: Dict[str, Any], exclude_client_id: Optional[str] = None):
        """Broadcast a message to all active connected clients, optionally excluding one."""
        with self.clients_lock:
            for cid, info in list(self.connected_clients.items()):
                if exclude_client_id and cid == exclude_client_id:
                    continue
                sock = info["socket"]
                try:
                    self._send_json(sock, data)
                except Exception as e:
                    logger.error(f"[KEY_SERVER] Error sending to {cid}: {e}")

    def _handle_client_connection(self, client_sock: socket.socket, addr: Tuple[str, int]):
        buffer = ""
        current_client_id: Optional[str] = None

        try:
            while self.is_running:
                data = client_sock.recv(4096)
                if not data:
                    break
                buffer += data.decode("utf-8")

                while "\n" in buffer:
                    line, buffer = buffer.split("\n", 1)
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        req = json.loads(line)
                        cmd = req.get("cmd")
                        if cmd == "REGISTER_INITIAL":
                            current_client_id = self._handle_register_initial(client_sock, req)
                        elif cmd == "JOIN":
                            current_client_id = self._handle_join(client_sock, req)
                        elif cmd == "LEAVE":
                            self._handle_leave(client_sock, req)
                        elif cmd == "MULTICAST_PUBLISH":
                            self._handle_multicast_publish(client_sock, req)
                        elif cmd == "GET_TREE_STATE":
                            self._send_json(client_sock, {"status": "OK", "state": self.tree.get_tree_state()})
                        else:
                            self._send_json(client_sock, {"status": "ERROR", "error": f"Unknown command {cmd}"})
                    except Exception as e:
                        logger.error(f"[KEY_SERVER] Request error: {e}")
                        self._send_json(client_sock, {"status": "ERROR", "error": str(e)})

        except Exception as e:
            pass
        finally:
            client_sock.close()
            if current_client_id:
                with self.clients_lock:
                    if current_client_id in self.connected_clients:
                        del self.connected_clients[current_client_id]

    def _handle_register_initial(self, sock: socket.socket, req: Dict[str, Any]) -> str:
        """Register a member initially during tree setup (without rekey broadcast)."""
        client_id = req["client_id"]
        role = req.get("role", "Subscriber")
        keys = self.tree.register_initial_member(client_id)
        leaf_id = self.tree.client_to_leaf[client_id]

        with self.clients_lock:
            self.connected_clients[client_id] = {
                "socket": sock,
                "role": role,
                "leaf_id": leaf_id
            }

        keys_hex = {str(nid): key_to_hex(k) for nid, k in keys.items()}
        self._send_json(sock, {
            "status": "OK",
            "msg_type": "INITIAL_KEYS",
            "client_id": client_id,
            "role": role,
            "leaf_id": leaf_id,
            "keys": keys_hex,
            "path": self.tree.get_path_to_root(leaf_id)
        })
        return client_id

    def _handle_join(self, sock: socket.socket, req: Dict[str, Any]) -> str:
        """Dynamic member JOIN with Forward Secrecy Rekeying."""
        client_id = req["client_id"]
        role = req.get("role", "Subscriber")
        leaf_id = self.tree.client_to_leaf.get(client_id)

        # 1. Perform LKH Join rekeying
        rekey_msg, client_key_bundle = self.tree.handle_join(client_id)
        blocks_count = rekey_msg["blocks_count"]

        # Log trace exactly as in Slide 39
        self._log(f"[{client_id}] Joining Group... LKH Rekey Sent: {blocks_count} Encrypted Blocks.")

        # 2. Register new connected client
        with self.clients_lock:
            self.connected_clients[client_id] = {
                "socket": sock,
                "role": role,
                "leaf_id": leaf_id
            }

        # 3. Send initial path keys securely to the new member
        keys_hex = {str(nid): key_to_hex(k) for nid, k in client_key_bundle.items()}
        self._send_json(sock, {
            "status": "OK",
            "msg_type": "JOIN_KEYS_BUNDLE",
            "client_id": client_id,
            "role": role,
            "leaf_id": leaf_id,
            "keys": keys_hex,
            "path": self.tree.get_path_to_root(leaf_id)
        })

        # 4. Multicast the 3 rekey blocks to all other members (Forward Secrecy)
        multicast_rekey = {
            "type": "REKEY_MESSAGE",
            "rekey_type": "JOIN",
            "client_id": client_id,
            "rekey_node_id": leaf_id,
            "blocks_count": blocks_count,
            "rekey_blocks": rekey_msg["rekey_blocks"]
        }
        self._broadcast_to_active(multicast_rekey, exclude_client_id=client_id)

        return client_id

    def _handle_leave(self, sock: socket.socket, req: Dict[str, Any]):
        """Dynamic member LEAVE with Backward Secrecy Rekeying."""
        client_id = req["client_id"]
        self._log(f"[{client_id}] Leaving Group... Executing Backward Secrecy Rekey.")

        # 1. Perform LKH Leave rekeying
        rekey_msg = self.tree.handle_leave(client_id)
        blocks_count = rekey_msg["blocks_count"]
        d = rekey_msg["d_factor"]
        h = rekey_msg["h_factor"]

        # Log trace exactly as in Slide 39
        self._log(f"[KEY_SERVER] Generated {blocks_count} Rekey Blocks (d*h = {d}*{h}). Revoked {client_id}.")

        # 2. Multicast rekey blocks to all remaining members
        multicast_rekey = {
            "type": "REKEY_MESSAGE",
            "rekey_type": "LEAVE",
            "revoked_client_id": client_id,
            "rekey_node_id": rekey_msg["rekey_node_id"],
            "blocks_count": blocks_count,
            "d_factor": d,
            "h_factor": h,
            "rekey_blocks": rekey_msg["rekey_blocks"]
        }
        self._broadcast_to_active(multicast_rekey, exclude_client_id=client_id)

        # 3. Remove client from connected clients
        with self.clients_lock:
            if client_id in self.connected_clients:
                del self.connected_clients[client_id]

        self._send_json(sock, {"status": "OK", "msg": f"Client {client_id} revoked successfully."})

    def _handle_multicast_publish(self, sock: socket.socket, req: Dict[str, Any]):
        """
        Multicast Publish handler with ABAC Policy Engine Evaluation and AES-256-GCM encryption.
        """
        client_id = req["client_id"]
        role = req.get("role")
        if not role:
            with self.clients_lock:
                if client_id in self.connected_clients:
                    role = self.connected_clients[client_id]["role"]
                else:
                    role = "Subscriber"

        action = req.get("action", "PUBLISH")
        eval_time = req.get("time")  # Optional simulated time string, e.g. "10:30" or "20:00"
        plaintext = req.get("payload", "")

        # 1. ABAC Policy Evaluation
        subject = {"id": client_id, "role": role}
        environment = {"time": eval_time} if eval_time else {}

        decision = self.abac_engine.evaluate(
            subject=subject,
            action=action,
            resource="MULTICAST_STREAM",
            environment=environment
        )

        if not decision.allowed:
            self._log(f"[ABAC_ENGINE] Policy Evaluation DENIED -> {decision.reason}")
            self._send_json(sock, {
                "status": "DENIED",
                "reason": decision.reason,
                "details": decision.details
            })
            return

        # Slide 39 trace on success
        self._log("[ABAC_ENGINE] Policy Evaluation PASSED -> Multicast Delivered.")

        # 2. Encrypt Multicast Payload using Current Root Key K_0 (Node 1) with AES-256-GCM
        root_key = self.tree.root_key
        payload_bytes = plaintext.encode("utf-8")
        nonce, ciphertext = encrypt_aes_gcm(root_key, payload_bytes)

        # Slide 39 trace on dispatch
        self._log("[KEY_SERVER] Multicast Dispatch: AES-256 Payload Encrypted under Root Key K_0.")

        # 3. Broadcast encrypted multicast to all active members
        multicast_packet = {
            "type": "MULTICAST_DISPATCH",
            "sender_id": client_id,
            "nonce": nonce.hex(),
            "ciphertext": ciphertext.hex(),
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }
        self._broadcast_to_active(multicast_packet)

        # Acknowledge publisher
        self._send_json(sock, {
            "status": "OK",
            "msg": "Multicast delivered",
            "decision": decision.to_dict(),
            "packet": multicast_packet
        })

    def dispatch_multicast_direct(self, client_id: str, payload: str, role: str = "Publisher", eval_time: str = "10:30") -> Dict[str, Any]:
        """
        Direct helper method to dispatch multicast programmatically (useful for simulations and dashboard).
        """
        subject = {"id": client_id, "role": role}
        environment = {"time": eval_time} if eval_time else {}

        decision = self.abac_engine.evaluate(
            subject=subject,
            action="PUBLISH",
            resource="MULTICAST_STREAM",
            environment=environment
        )

        if not decision.allowed:
            self._log(f"[ABAC_ENGINE] Policy Evaluation DENIED -> {decision.reason}")
            return {"status": "DENIED", "reason": decision.reason, "details": decision.details}

        self._log("[ABAC_ENGINE] Policy Evaluation PASSED -> Multicast Delivered.")

        root_key = self.tree.root_key
        payload_bytes = payload.encode("utf-8")
        nonce, ciphertext = encrypt_aes_gcm(root_key, payload_bytes)

        self._log("[KEY_SERVER] Multicast Dispatch: AES-256 Payload Encrypted under Root Key K_0.")

        packet = {
            "type": "MULTICAST_DISPATCH",
            "sender_id": client_id,
            "nonce": nonce.hex(),
            "ciphertext": ciphertext.hex(),
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }
        self._broadcast_to_active(packet)

        return {"status": "OK", "packet": packet, "decision": decision.to_dict()}

if __name__ == "__main__":
    import argparse
    import time

    parser = argparse.ArgumentParser(description="Key Server (LKH Key Graph Controller)")
    parser.add_argument("--host", type=str, default="127.0.0.1", help="Host interface")
    parser.add_argument("--port", type=int, default=9999, help="TCP port")
    parser.add_argument("--members", type=int, default=8, help="Number of members in group (default: 8)")
    args = parser.parse_args()

    server = KeyServer(host=args.host, port=args.port, num_members=args.members)
    server.start()
    print(f"Key Server running on {args.host}:{args.port}. Press Ctrl+C to stop.")

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\nStopping Key Server...")
        server.stop()
