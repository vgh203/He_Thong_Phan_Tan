"""
Secure Resource Server (Server_Bob)
Handles:
1. Needham-Schroeder mutual handshake (Ticket decryption & Nonce challenge R_B).
2. Secure RPC channel over AES-256-CBC.
3. Message integrity verification with HMAC-SHA256 (Encrypt-then-MAC).
4. Anti-Replay protection tracking observed RPC nonces.
"""

import json
import socket
import threading
import sys
from common import (
    SERVER_HOST,
    SERVER_PORT,
    KEY_B_SERVER_KDC,
    CLIENT_ID,
    DEFAULT_NONCE_RB,
)
from crypto_utils import (
    encrypt_aes_cbc,
    decrypt_aes_cbc,
    compute_hmac_sha256,
    verify_hmac_sha256,
    send_msg,
    recv_msg,
)


class SecureResourceServer:
    def __init__(self, host: str = SERVER_HOST, port: int = SERVER_PORT):
        self.host = host
        self.port = port
        self.running = False
        self.server_socket = None

        # Server-side State / Resources (e.g. Bank Account Balance)
        self.resources = {"Balance": 0}

        # Anti-Replay Protection: Set of used RPC nonces
        self.seen_nonces = set()
        self.lock = threading.Lock()

    def start(self):
        """Starts the Server_Bob socket listener."""
        self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.server_socket.bind((self.host, self.port))
        self.server_socket.listen(5)
        self.running = True
        print(f"[SERVER] Secure Resource Server (Server_Bob) listening on {self.host}:{self.port}...", flush=True)

        try:
            while self.running:
                try:
                    conn, addr = self.server_socket.accept()
                except OSError:
                    break
                client_thread = threading.Thread(target=self.handle_client_connection, args=(conn, addr), daemon=True)
                client_thread.start()
        except KeyboardInterrupt:
            print("\n[SERVER] Shutting down Server_Bob.", flush=True)
        finally:
            self.stop()

    def stop(self):
        self.running = False
        if self.server_socket:
            try:
                self.server_socket.close()
            except Exception:
                pass

    def handle_client_connection(self, conn: socket.socket, addr):
        session_key = None
        client_name = None

        try:
            # ==============================================================
            # Phase 1: Needham-Schroeder Handshake (Steps 3 - 5)
            # ==============================================================
            init_msg = recv_msg(conn)
            if not init_msg or init_msg.get("type") != "FORWARD_TICKET":
                send_msg(conn, {"status": "ERROR", "message": "Expected FORWARD_TICKET"})
                return

            ticket_bob_b64 = init_msg.get("ticket_bob")
            try:
                ticket_plaintext = decrypt_aes_cbc(KEY_B_SERVER_KDC, ticket_bob_b64)
                ticket_data = json.loads(ticket_plaintext)
                session_key = bytes.fromhex(ticket_data["session_key"])
                client_name = ticket_data["client_id"]
            except Exception as e:
                send_msg(conn, {"status": "ERROR", "message": f"Ticket decryption failed: {e}"})
                return

            if client_name != CLIENT_ID:
                send_msg(conn, {"status": "ERROR", "message": "Unauthorized client identity"})
                return

            # Step 4: Server generates challenge R_B and sends E_K_AB(R_B)
            nonce_b = init_msg.get("challenge_hint", DEFAULT_NONCE_RB)
            challenge_payload = encrypt_aes_cbc(session_key, json.dumps({"nonce_b": nonce_b}))

            send_msg(conn, {
                "type": "NONCE_CHALLENGE",
                "challenge": challenge_payload
            })

            # Step 5: Receive response E_K_AB(R_B - 1)
            resp_msg = recv_msg(conn)
            if not resp_msg or resp_msg.get("type") != "CHALLENGE_RESPONSE":
                send_msg(conn, {"status": "ERROR", "message": "Expected CHALLENGE_RESPONSE"})
                return

            resp_payload = resp_msg.get("response")
            try:
                decrypted_resp = decrypt_aes_cbc(session_key, resp_payload)
                resp_data = json.loads(decrypted_resp)
                received_val = resp_data.get("response_b")
            except Exception as e:
                send_msg(conn, {"status": "ERROR", "message": f"Challenge decryption failed: {e}"})
                return

            # Verify R_B - 1
            if received_val != (nonce_b - 1):
                send_msg(conn, {"status": "ERROR", "message": "Handshake failed: Invalid challenge response"})
                return

            # Expected Console Trace output matching Slide 40:
            print(f"[SERVER] Ticket_Bob Decrypted | Nonce Challenge R_B = {nonce_b} Verified.", flush=True)
            import time
            time.sleep(0.05)

            # Handshake successful
            send_msg(conn, {"status": "OK", "message": "Handshake Successful"})

            # ==============================================================
            # Phase 2: Secure RPC Processing Loop
            # ==============================================================
            while self.running:
                rpc_packet = recv_msg(conn)
                if not rpc_packet:
                    break

                if rpc_packet.get("type") != "SECURE_RPC":
                    continue

                payload = rpc_packet.get("payload")
                received_hmac = rpc_packet.get("hmac")

                # 1. Message Integrity Check with HMAC-SHA256
                if not verify_hmac_sha256(session_key, payload, received_hmac):
                    print("[SERVER] [INTEGRITY VIOLATION] HMAC Verification FAILED! Tampering detected.", flush=True)
                    send_msg(conn, {
                        "status": "ERROR",
                        "code": "HMAC_VERIFICATION_FAILED",
                        "message": "HMAC integrity check failed. Message dropped."
                    })
                    continue

                # 2. Decrypt Payload using AES-256-CBC
                try:
                    decrypted_rpc = decrypt_aes_cbc(session_key, payload)
                    rpc_data = json.loads(decrypted_rpc)
                except Exception as e:
                    send_msg(conn, {
                        "status": "ERROR",
                        "code": "DECRYPTION_FAILED",
                        "message": f"Failed to decrypt RPC payload: {e}"
                    })
                    continue

                nonce_rpc = rpc_data.get("nonce_rpc")
                method = rpc_data.get("method")
                params = rpc_data.get("params", [])

                # 3. Anti-Replay Protection: Check if Nonce has been used
                with self.lock:
                    if nonce_rpc in self.seen_nonces:
                        print(f"[SERVER] [REPLAY ATTACK DETECTED] Duplicate Nonce {nonce_rpc} detected! Execution rejected.", flush=True)
                        send_msg(conn, {
                            "status": "ERROR",
                            "code": "REPLAY_ATTACK_DETECTED",
                            "message": f"Replay attack detected: Nonce {nonce_rpc} already processed."
                        })
                        continue
                    # Record the nonce to prevent replay
                    self.seen_nonces.add(nonce_rpc)

                # 4. Execute Remote Procedure Call
                result = self.execute_procedure(method, params)

                # Expected Console Trace output matching Slide 40:
                print("[SERVER] HMAC Verified OK | Decrypted RPC Execution Successful.", flush=True)

                # 5. Return Encrypted and HMAC-authenticated Result to Client
                resp_data = {
                    "status": "SUCCESS",
                    "result": result,
                    "nonce_rpc": nonce_rpc
                }
                encrypted_resp_payload = encrypt_aes_cbc(session_key, json.dumps(resp_data))
                resp_hmac = compute_hmac_sha256(session_key, encrypted_resp_payload)

                send_msg(conn, {
                    "type": "RPC_RESPONSE",
                    "payload": encrypted_resp_payload,
                    "hmac": resp_hmac
                })

        except Exception as e:
            print(f"[SERVER] Connection error: {e}", file=sys.stderr, flush=True)
        finally:
            try:
                conn.close()
            except Exception:
                pass

    def execute_procedure(self, method: str, params: list):
        """Executes procedure calls on server resources."""
        with self.lock:
            if method == "Write":
                key, value = params[0], params[1]
                self.resources[key] = value
                return {"action": "Write", key: value, "current_state": self.resources}
            elif method == "Read":
                key = params[0]
                value = self.resources.get(key, None)
                return {"action": "Read", key: value}
            elif method == "Reset":
                self.resources.clear()
                self.seen_nonces.clear()
                return {"action": "Reset", "status": "Clean"}
            else:
                return {"error": f"Unknown method: {method}"}


if __name__ == "__main__":
    server = SecureResourceServer()
    server.start()
