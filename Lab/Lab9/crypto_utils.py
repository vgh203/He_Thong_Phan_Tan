"""
Cryptographic and Socket Messaging Utilities
Supports AES-256-CBC, PKCS7 Padding, HMAC-SHA256, and Length-Prefixed Framing.
"""

import base64
import json
import secrets
import struct
import socket
import hmac
import hashlib
from Crypto.Cipher import AES
from Crypto.Util.Padding import pad, unpad


# ==========================================
# AES-CBC Encryption & Decryption
# ==========================================

def encrypt_aes_cbc(key: bytes, plaintext_str: str) -> str:
    """
    Encrypts a plaintext string using AES-CBC with PKCS7 padding.
    A fresh 16-byte random IV is generated for each encryption.
    Returns: Base64-encoded string containing (IV + Ciphertext).
    """
    if len(key) not in (16, 24, 32):
        raise ValueError("AES key must be 16, 24, or 32 bytes long.")
    
    iv = secrets.token_bytes(16)
    cipher = AES.new(key, AES.MODE_CBC, iv=iv)
    padded_data = pad(plaintext_str.encode("utf-8"), AES.block_size)
    ciphertext = cipher.encrypt(padded_data)
    
    # Prepend IV to ciphertext for easy transmission and decryption
    combined = iv + ciphertext
    return base64.b64encode(combined).decode("utf-8")


def decrypt_aes_cbc(key: bytes, b64_combined_str: str) -> str:
    """
    Decrypts a Base64-encoded string containing (IV + Ciphertext) using AES-CBC.
    Unpads using PKCS7 and returns the original plaintext string.
    """
    raw_bytes = base64.b64decode(b64_combined_str.encode("utf-8"))
    if len(raw_bytes) < 16:
        raise ValueError("Invalid ciphertext length: must be at least 16 bytes for IV.")
    
    iv = raw_bytes[:16]
    ciphertext = raw_bytes[16:]
    
    cipher = AES.new(key, AES.MODE_CBC, iv=iv)
    decrypted_padded = cipher.decrypt(ciphertext)
    plaintext_bytes = unpad(decrypted_padded, AES.block_size)
    return plaintext_bytes.decode("utf-8")


# ==========================================
# HMAC-SHA256 Integrity Verification
# ==========================================

def compute_hmac_sha256(key: bytes, message: str) -> str:
    """
    Computes HMAC-SHA256 checksum for a given message string using the provided key.
    Returns: Hexadecimal string representation of the HMAC.
    """
    h = hmac.new(key, message.encode("utf-8"), hashlib.sha256)
    return h.hexdigest()


def verify_hmac_sha256(key: bytes, message: str, expected_hmac: str) -> bool:
    """
    Verifies the HMAC-SHA256 checksum using constant-time comparison to prevent timing attacks.
    """
    actual_hmac = compute_hmac_sha256(key, message)
    return hmac.compare_digest(actual_hmac, expected_hmac)


def generate_session_key(length: int = 32) -> bytes:
    """
    Generates a cryptographically secure random session key (AES-256: 32 bytes).
    """
    return secrets.token_bytes(length)


# ==========================================
# Robust Socket Framing (Length-Prefixed)
# ==========================================

def send_msg(sock: socket.socket, msg_dict: dict):
    """
    Sends a JSON dictionary over a socket prefixed with 4-byte big-endian message length.
    """
    data_bytes = json.dumps(msg_dict).encode("utf-8")
    length_prefix = struct.pack(">I", len(data_bytes))
    sock.sendall(length_prefix + data_bytes)


def recv_msg(sock: socket.socket) -> dict | None:
    """
    Receives a 4-byte length-prefixed JSON message from a socket.
    Returns None if connection is closed.
    """
    # Read the 4-byte prefix
    prefix = _recv_exact(sock, 4)
    if not prefix:
        return None
    
    msg_length = struct.unpack(">I", prefix)[0]
    payload_bytes = _recv_exact(sock, msg_length)
    if not payload_bytes:
        return None
    
    return json.loads(payload_bytes.decode("utf-8"))


def _recv_exact(sock: socket.socket, num_bytes: int) -> bytes | None:
    """
    Helper to read exactly num_bytes from a socket stream.
    """
    chunks = []
    received = 0
    while received < num_bytes:
        chunk = sock.recv(num_bytes - received)
        if not chunk:
            return None
        chunks.append(chunk)
        received += len(chunk)
    return b"".join(chunks)

