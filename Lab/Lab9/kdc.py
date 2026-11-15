"""
KDC Daemon (Key Distribution Center)
Implements the Needham-Schroeder ticket granting sequence.
Pre-shared keys: K_A (Alice <-> KDC) and K_B (Bob <-> KDC).
"""

import json
import socket
import threading
import sys
from common import (
    KDC_HOST,
    KDC_PORT,
    CLIENT_ID,
    SERVER_ID,
    KEY_A_CLIENT_KDC,
    KEY_B_SERVER_KDC,
)
from crypto_utils import (
    encrypt_aes_cbc,
    generate_session_key,
    send_msg,
    recv_msg,
)


class KDCDaemon:
    def __init__(self, host: str = KDC_HOST, port: int = KDC_PORT):
        self.host = host
        self.port = port
        self.running = False
        self.server_socket = None

    def start(self):
        """Starts the KDC server socket listener."""
        self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.server_socket.bind((self.host, self.port))
        self.server_socket.listen(5)
        self.running = True
        print(f"[KDC] KDC Daemon listening on {self.host}:{self.port}...", flush=True)

        try:
            while self.running:
                try:
                    conn, addr = self.server_socket.accept()
                except OSError:
                    break
                handler_thread = threading.Thread(target=self.handle_client, args=(conn, addr), daemon=True)
                handler_thread.start()
        except KeyboardInterrupt:
            print("\n[KDC] Shutting down KDC Daemon.", flush=True)
        finally:
            self.stop()

    def stop(self):
        self.running = False
        if self.server_socket:
            try:
                self.server_socket.close()
            except Exception:
                pass

    def handle_client(self, conn: socket.socket, addr):
        try:
            req = recv_msg(conn)
            if not req:
                return

            client_id = req.get("client_id")
            server_id = req.get("server_id")
            nonce_a = req.get("nonce_a")

            # Validate requested principals
            if client_id != CLIENT_ID or server_id != SERVER_ID:
                err_resp = {"status": "ERROR", "message": "Unknown principal identifiers"}
                send_msg(conn, err_resp)
                return

            # Step 2: Generate symmetric session key K_AB (32 bytes = 256 bits)
            k_ab = generate_session_key(32)
            k_ab_hex = k_ab.hex()

            # Create Ticket_Bob = E_K_B(K_AB, Client_ID)
            ticket_bob_data = {
                "session_key": k_ab_hex,
                "client_id": client_id
            }
            ticket_bob_encrypted = encrypt_aes_cbc(KEY_B_SERVER_KDC, json.dumps(ticket_bob_data))

            # Encrypt response with K_A: E_K_A(R_A, Bob, K_AB, Ticket_Bob)
            kdc_response_data = {
                "nonce_a": nonce_a,
                "server_id": server_id,
                "session_key": k_ab_hex,
                "ticket_bob": ticket_bob_encrypted
            }
            encrypted_payload = encrypt_aes_cbc(KEY_A_CLIENT_KDC, json.dumps(kdc_response_data))

            # Expected Console Trace output matching Slide 40:
            print(f"[KDC] Ticket_Bob Generated | Session Key K_AB Created.", flush=True)

            # Send response back to Client
            send_msg(conn, {
                "status": "OK",
                "encrypted_response": encrypted_payload
            })

        except Exception as e:
            print(f"[KDC] Error handling request: {e}", file=sys.stderr, flush=True)
        finally:
            try:
                conn.close()
            except Exception:
                pass


if __name__ == "__main__":
    kdc = KDCDaemon()
    kdc.start()
