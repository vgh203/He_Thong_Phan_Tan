"""
Common constants, network configuration, and shared settings
for the Secure RPC & KDC Authentication Proxy Simulator.
"""

import hashlib

# Network Host & Port Configurations
KDC_HOST = "127.0.0.1"
KDC_PORT = 9001

SERVER_HOST = "127.0.0.1"
SERVER_PORT = 9002

# Principal Identifiers
CLIENT_ID = "Alice"
SERVER_ID = "Server_Bob"

# Pre-shared Long-term Secret Keys (32 bytes / 256 bits for AES-256)
# Derived via SHA-256 from master credentials to guarantee exactly 32 bytes.
KEY_A_CLIENT_KDC = hashlib.sha256(b"Alice_Secret_Master_Key_Credentials_2026").digest()
KEY_B_SERVER_KDC = hashlib.sha256(b"Bob_Server_Secret_Master_Key_Credentials_2026").digest()

# Sample Nonces matching Slide 39-40
DEFAULT_NONCE_RA = 84920
DEFAULT_NONCE_RB = 10492
