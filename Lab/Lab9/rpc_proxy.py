"""
Secure RPC Proxy
Encapsulates KDC authentication, session negotiation, AES-256-CBC encryption,
HMAC-SHA256 generation/verification, and RPC payload marshalling.
"""

import json
import socket
import random
from common import (
    KDC_HOST,
    KDC_PORT,
    SERVER_HOST,
    SERVER_PORT,
    CLIENT_ID,
    SERVER_ID,
    KEY_A_CLIENT_KDC,
    DEFAULT_NONCE_RA,
)
from crypto_utils import (
    encrypt_aes_cbc,
    decrypt_aes_cbc,
    compute_hmac_sha256,
    verify_hmac_sha256,
    send_msg,
    recv_msg,
)


class SecureRPCProxy:
    def __init__(
        self,
        client_id: str = CLIENT_ID,
        server_id: str = SERVER_ID,
        kdc_host: str = KDC_HOST,
        kdc_port: int = KDC_PORT,
        server_host: str = SERVER_HOST,
        server_port: int = SERVER_PORT,
        key_a: bytes = KEY_A_CLIENT_KDC,
    ):
        self.client_id = client_id
        self.server_id = server_id
        self.kdc_host = kdc_host
        self.kdc_port = kdc_port
        self.server_host = server_host
        self.server_port = server_port
        self.key_a = key_a

        # State established after authentication
        self.session_key = None  # K_AB
        self.ticket_bob = None
        self.server_socket = None
        self.is_connected = False
        
        # Kept for anti-replay demonstration
        self.last_sent_packet = None

    def authenticate_with_kdc(self, nonce_a: int = DEFAULT_NONCE_RA) -> bool:
        """
        Step 1 & 2: Requests session key from KDC using Needham-Schroeder protocol.
        """
        # Slide 40 exact trace
        print(f"[CLIENT] Requesting Session Key for {self.server_id} from KDC (Nonce R_A = {nonce_a})...", flush=True)

        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as kdc_sock:
            kdc_sock.connect((self.kdc_host, self.kdc_port))
            req = {
                "client_id": self.client_id,
                "server_id": self.server_id,
                "nonce_a": nonce_a,
            }
            send_msg(kdc_sock, req)
            kdc_resp = recv_msg(kdc_sock)

        if not kdc_resp or kdc_resp.get("status") != "OK":
            raise RuntimeError(f"KDC authentication failed: {kdc_resp}")

        # Decrypt KDC response using K_A
        encrypted_response = kdc_resp.get("encrypted_response")
        decrypted_json_str = decrypt_aes_cbc(self.key_a, encrypted_response)
        data = json.loads(decrypted_json_str)

        # Verify Nonce R_A to prevent replay of old tickets
        if data.get("nonce_a") != nonce_a:
            raise ValueError(f"Nonce mismatch! Expected {nonce_a}, got {data.get('nonce_a')}")

        if data.get("server_id") != self.server_id:
            raise ValueError(f"Server ID mismatch! Expected {self.server_id}, got {data.get('server_id')}")

        self.session_key = bytes.fromhex(data["session_key"])
        self.ticket_bob = data["ticket_bob"]
        return True

    def establish_channel_with_server(self, challenge_hint: int | None = None) -> bool:
        """
        Step 3, 4, 5: Mutual authentication handshake with Server_Bob.
        """
        if not self.ticket_bob or not self.session_key:
            raise RuntimeError("Must authenticate with KDC before contacting Server.")

        self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.server_socket.connect((self.server_host, self.server_port))

        # Step 3: Forward Ticket_Bob to Server
        # Slide 40 exact trace
        print(f"[CLIENT] Decrypted Response | Ticket_Bob Forwarded to {self.server_id}.", flush=True)

        init_msg = {
            "type": "FORWARD_TICKET",
            "ticket_bob": self.ticket_bob,
        }
        if challenge_hint is not None:
            init_msg["challenge_hint"] = challenge_hint

        send_msg(self.server_socket, init_msg)

        # Step 4: Receive Nonce challenge R_B from Server
        challenge_msg = recv_msg(self.server_socket)
        if not challenge_msg or challenge_msg.get("type") != "NONCE_CHALLENGE":
            raise RuntimeError(f"Unexpected response from server: {challenge_msg}")

        encrypted_challenge = challenge_msg.get("challenge")
        decrypted_challenge = decrypt_aes_cbc(self.session_key, encrypted_challenge)
        challenge_data = json.loads(decrypted_challenge)
        nonce_b = challenge_data.get("nonce_b")

        # Step 5: Respond with E_K_AB(R_B - 1)
        response_b = nonce_b - 1
        encrypted_resp = encrypt_aes_cbc(self.session_key, json.dumps({"response_b": response_b}))
        send_msg(self.server_socket, {
            "type": "CHALLENGE_RESPONSE",
            "response": encrypted_resp
        })

        # Receive handshake confirmation
        ack = recv_msg(self.server_socket)
        if not ack or ack.get("status") != "OK":
            raise RuntimeError(f"Handshake failed with server: {ack}")

        self.is_connected = True
        # Slide 40 exact trace
        print(f"[CLIENT] Secure Channel Established with {self.server_id}!", flush=True)
        return True

    def call(self, method: str, *args, custom_nonce: int | None = None) -> dict:
        """
        Invokes a remote procedure call securely over AES-256-CBC with HMAC-SHA256
        and Anti-Replay protection.
        """
        if not self.is_connected or not self.server_socket:
            raise RuntimeError("Secure channel not established.")

        nonce_rpc = custom_nonce if custom_nonce is not None else random.randint(100000, 999999)

        # Format RPC invocation payload
        rpc_payload = {
            "nonce_rpc": nonce_rpc,
            "method": method,
            "params": list(args)
        }
        plaintext_json = json.dumps(rpc_payload)

        # 1. AES-256-CBC Encryption
        ciphertext_b64 = encrypt_aes_cbc(self.session_key, plaintext_json)

        # 2. HMAC-SHA256 Integrity Tag
        hmac_signature = compute_hmac_sha256(self.session_key, ciphertext_b64)

        packet = {
            "type": "SECURE_RPC",
            "payload": ciphertext_b64,
            "hmac": hmac_signature
        }

        # Save for replay testing
        self.last_sent_packet = packet

        # Format param string matching Slide 40: Write('Balance', 500)
        formatted_args = ", ".join(f"'{a}'" if isinstance(a, str) else str(a) for a in args)
        # Slide 40 exact trace
        print(f"[CLIENT] Executing Secure RPC: {method}({formatted_args}) | Encrypted Payload + HMAC Sent.", flush=True)

        send_msg(self.server_socket, packet)

        # Receive response from Server
        response_packet = recv_msg(self.server_socket)
        if not response_packet:
            raise RuntimeError("Connection closed by server.")

        # Check for server-reported errors (e.g. Replay attack, HMAC failure)
        if response_packet.get("status") == "ERROR":
            return response_packet

        # Verify HMAC on Server's response
        resp_payload = response_packet.get("payload")
        resp_hmac = response_packet.get("hmac")
        if not verify_hmac_sha256(self.session_key, resp_payload, resp_hmac):
            raise ValueError("[CLIENT] Server response HMAC verification failed!")

        # Decrypt Server response
        decrypted_resp = decrypt_aes_cbc(self.session_key, resp_payload)
        return json.loads(decrypted_resp)

    # Convenience RPC Methods
    def Write(self, key: str, value: any, custom_nonce: int | None = None) -> dict:
        return self.call("Write", key, value, custom_nonce=custom_nonce)

    def Read(self, key: str, custom_nonce: int | None = None) -> dict:
        return self.call("Read", key, custom_nonce=custom_nonce)

    def replay_last_rpc(self) -> dict:
        """
        Sends the exact previous RPC packet again to test Anti-Replay protection.
        """
        if not self.last_sent_packet:
            raise RuntimeError("No previous RPC packet available to replay.")

        print(f"[CLIENT] [ATTACK TEST] Replaying previous RPC packet to server...", flush=True)
        send_msg(self.server_socket, self.last_sent_packet)
        return recv_msg(self.server_socket)

    def send_tampered_rpc(self, method: str, *args) -> dict:
        """
        Simulates an active MITM attacker altering the ciphertext to test HMAC integrity check.
        """
        nonce_rpc = random.randint(100000, 999999)
        rpc_payload = {"nonce_rpc": nonce_rpc, "method": method, "params": list(args)}
        ciphertext_b64 = encrypt_aes_cbc(self.session_key, json.dumps(rpc_payload))
        
        # Legitimate HMAC for original ciphertext
        original_hmac = compute_hmac_sha256(self.session_key, ciphertext_b64)

        # Attacker tampers with 1 character of ciphertext
        tampered_ciphertext = ("A" if ciphertext_b64[0] != "A" else "B") + ciphertext_b64[1:]

        print(f"[CLIENT] [ATTACK TEST] Sending tampered ciphertext with old HMAC to server...", flush=True)
        tampered_packet = {
            "type": "SECURE_RPC",
            "payload": tampered_ciphertext,
            "hmac": original_hmac
        }
        send_msg(self.server_socket, tampered_packet)
        return recv_msg(self.server_socket)

    def close(self):
        """Closes the connection cleanly."""
        self.is_connected = False
        if self.server_socket:
            try:
                self.server_socket.close()
            except Exception:
                pass
