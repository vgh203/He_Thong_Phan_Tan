"""
client.py
Group Client Node connecting to Key Server via TCP Socket.
Stores local key array (Leaf Key + Path KEKs + Root Group Key K_0).
Listens for multicast rekey messages and updates local key holdings dynamically.
Decrypts AES-256-GCM multicast payloads under root group key.
"""

import socket
import threading
import json
import logging
from typing import Dict, Any, Optional, List, Tuple
from crypto_utils import (
    encrypt_aes_gcm,
    decrypt_aes_gcm,
    key_to_hex,
    hex_to_key,
    format_key_short
)

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger("GroupClient")

class GroupClient:
    def __init__(self, client_id: str, role: str = "Subscriber", host: str = "127.0.0.1", port: int = 9999):
        self.client_id: str = client_id
        self.role: str = role
        self.host: str = host
        self.port: int = port

        self.leaf_id: Optional[int] = None
        self.keys: Dict[int, bytes] = {}       # Local key array: node_id -> 32-byte AES key
        self.path: List[int] = []              # Path from leaf up to root node 1

        self.sock: Optional[socket.socket] = None
        self.is_connected: bool = False
        self.listener_thread: Optional[threading.Thread] = None

        self.received_messages: List[Dict[str, Any]] = []
        self.logs: List[str] = []

        # Event flag for synchronization during automated testing
        self.rekey_event = threading.Event()
        self.multicast_event = threading.Event()

    def _log(self, msg: str):
        self.logs.append(msg)
        print(msg)

    def connect(self):
        """Establish TCP connection with Key Server."""
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.sock.connect((self.host, self.port))
        self.is_connected = True

        self.listener_thread = threading.Thread(target=self._listen_loop, daemon=True)
        self.listener_thread.start()

    def disconnect(self):
        """Close socket connection."""
        self.is_connected = False
        if self.sock:
            try:
                self.sock.close()
            except Exception:
                pass

    def _send_json(self, data: Dict[str, Any]):
        msg = (json.dumps(data) + "\n").encode("utf-8")
        self.sock.sendall(msg)

    def register_initial(self):
        """Register during initial setup (pre-existing member)."""
        req = {
            "cmd": "REGISTER_INITIAL",
            "client_id": self.client_id,
            "role": self.role
        }
        self._send_json(req)

    def join_group(self):
        """Join group dynamically (triggers Forward Secrecy Rekey on Server)."""
        req = {
            "cmd": "JOIN",
            "client_id": self.client_id,
            "role": self.role
        }
        self._send_json(req)

    def leave_group(self):
        """Leave group dynamically (triggers Backward Secrecy Rekey on Server)."""
        req = {
            "cmd": "LEAVE",
            "client_id": self.client_id
        }
        self._send_json(req)

    def publish_multicast(self, payload: str, eval_time: Optional[str] = None) -> None:
        """Send a request to publish a group multicast payload."""
        req = {
            "cmd": "MULTICAST_PUBLISH",
            "client_id": self.client_id,
            "role": self.role,
            "payload": payload,
            "time": eval_time
        }
        self._send_json(req)

    def _listen_loop(self):
        buffer = ""
        while self.is_connected:
            try:
                data = self.sock.recv(4096)
                if not data:
                    break
                buffer += data.decode("utf-8")
                while "\n" in buffer:
                    line, buffer = buffer.split("\n", 1)
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        msg = json.loads(line)
                        self._handle_server_message(msg)
                    except Exception as e:
                        logger.error(f"[{self.client_id}] Message handling error: {e}")
            except Exception:
                if not self.is_connected:
                    break

    def _handle_server_message(self, msg: Dict[str, Any]):
        msg_type = msg.get("msg_type") or msg.get("type")

        # 1. Received initial or join key bundle directly from Key Server
        if msg_type in ("INITIAL_KEYS", "JOIN_KEYS_BUNDLE"):
            self.leaf_id = msg["leaf_id"]
            self.path = msg["path"]
            raw_keys = msg["keys"]
            self.keys = {int(nid): hex_to_key(khex) for nid, khex in raw_keys.items()}
            self.rekey_event.set()

        # 2. Received Multicast Rekey Message (JOIN or LEAVE)
        elif msg_type == "REKEY_MESSAGE":
            self._process_rekey_message(msg)
            self.rekey_event.set()

        # 3. Received AES-256-GCM Multicast Message
        elif msg_type == "MULTICAST_DISPATCH":
            self._process_multicast_payload(msg)
            self.multicast_event.set()

    def _process_rekey_message(self, msg: Dict[str, Any]):
        rekey_type = msg.get("rekey_type")
        blocks = msg.get("rekey_blocks", [])
        updated_root = False

        if rekey_type == "JOIN":
            # For JOIN: blocks are encrypted under old keys
            for blk in blocks:
                target_nid = blk["target_node_id"]
                enc_nid = blk["encrypting_node_id"]
                if enc_nid in self.keys:
                    try:
                        nonce = bytes.fromhex(blk["nonce"])
                        ct = bytes.fromhex(blk["ciphertext"])
                        new_k = decrypt_aes_gcm(self.keys[enc_nid], nonce, ct)
                        self.keys[target_nid] = new_k
                        if target_nid == 1:
                            updated_root = True
                    except Exception as e:
                        pass

        elif rekey_type == "LEAVE":
            # For LEAVE: blocks are encrypted under child keys
            # Iterate until no more keys can be unlocked (progressing bottom-up to root)
            progress = True
            while progress:
                progress = False
                for blk in blocks:
                    target_nid = blk["target_node_id"]
                    enc_nid = blk["encrypting_node_id"]
                    # If this block is encrypted with a key we hold, and we haven't decrypted this target yet (or need update)
                    if enc_nid in self.keys and not blk.get("is_revoked_target", False):
                        if target_nid not in self.keys or self.keys[target_nid] != blk.get("_decrypted_val"):
                            try:
                                nonce = bytes.fromhex(blk["nonce"])
                                ct = bytes.fromhex(blk["ciphertext"])
                                new_k = decrypt_aes_gcm(self.keys[enc_nid], nonce, ct)
                                self.keys[target_nid] = new_k
                                blk["_decrypted_val"] = new_k
                                progress = True
                                if target_nid == 1:
                                    updated_root = True
                            except Exception:
                                pass

        if updated_root:
            # Slide 39 trace format:
            self._log(f"[{self.client_id}] Received Rekey Msg -> Updated Path Keys to Root Key K_0_New.")

    def _process_multicast_payload(self, msg: Dict[str, Any]):
        nonce_hex = msg["nonce"]
        ciphertext_hex = msg["ciphertext"]
        sender_id = msg.get("sender_id", "UNKNOWN")

        decrypted_text = self.try_decrypt_payload(nonce_hex, ciphertext_hex)
        if decrypted_text is not None:
            self.received_messages.append({
                "sender_id": sender_id,
                "text": decrypted_text,
                "timestamp": msg.get("timestamp")
            })

    def try_decrypt_payload(self, nonce_hex: str, ciphertext_hex: str, key_override: Optional[bytes] = None) -> Optional[str]:
        """
        Attempt to decrypt a multicast message using held Root Key (node 1) or key_override.
        Returns plaintext string if successful, None if decryption fails.
        """
        key = key_override or self.keys.get(1)
        if not key:
            return None
        try:
            nonce = bytes.fromhex(nonce_hex)
            ct = bytes.fromhex(ciphertext_hex)
            pt_bytes = decrypt_aes_gcm(key, nonce, ct)
            return pt_bytes.decode("utf-8")
        except Exception:
            # Decryption failed (Authentication tag mismatch / invalid key)
            return None

if __name__ == "__main__":
    import argparse
    import time

    parser = argparse.ArgumentParser(description="Group Client Node")
    parser.add_argument("--id", type=str, required=True, help="Client ID (e.g. CLIENT_1)")
    parser.add_argument("--role", type=str, default="Subscriber", choices=["Publisher", "Subscriber"], help="ABAC Role")
    parser.add_argument("--host", type=str, default="127.0.0.1", help="Key Server host")
    parser.add_argument("--port", type=int, default=9999, help="Key Server TCP port")
    parser.add_argument("--action", type=str, default="listen", choices=["listen", "publish", "join", "leave"], help="Initial action")
    parser.add_argument("--payload", type=str, default="Hello Multicast Group", help="Payload for publish action")
    parser.add_argument("--time", type=str, default=None, help="Simulated time (HH:MM) for ABAC evaluation")

    args = parser.parse_args()

    client = GroupClient(client_id=args.id, role=args.role, host=args.host, port=args.port)
    client.connect()

    if args.action == "join":
        client.join_group()
    else:
        client.register_initial()

    time.sleep(0.5)

    if args.action == "publish":
        print(f"[{args.id}] Requesting multicast publish...")
        client.publish_multicast(payload=args.payload, eval_time=args.time)
    elif args.action == "leave":
        print(f"[{args.id}] Requesting leave...")
        client.leave_group()

    print(f"[{args.id}] Client running and listening. Press Ctrl+C to disconnect.")
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print(f"\n[{args.id}] Disconnecting...")
        client.disconnect()
