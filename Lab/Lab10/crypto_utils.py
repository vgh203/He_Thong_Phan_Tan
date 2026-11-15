"""
crypto_utils.py
Utility module for AES-256-GCM authenticated encryption and key generation.
Used for LKH tree KEK/Root key management and multicast payload encryption.
"""

import os
from typing import Tuple, Dict, Any
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

def generate_key_256() -> bytes:
    """Generate a cryptographically secure 256-bit (32-byte) key."""
    return AESGCM.generate_key(bit_length=256)

def encrypt_aes_gcm(key: bytes, plaintext: bytes, associated_data: bytes = None) -> Tuple[bytes, bytes]:
    """
    Encrypt plaintext using AES-256-GCM.
    Returns:
        (nonce_12_bytes, ciphertext_with_tag)
    Note: cryptography AESGCM.encrypt appends 16-byte authentication tag to ciphertext.
    """
    aesgcm = AESGCM(key)
    nonce = os.urandom(12)  # Standard 96-bit nonce for GCM
    ciphertext = aesgcm.encrypt(nonce, plaintext, associated_data)
    return nonce, ciphertext

def decrypt_aes_gcm(key: bytes, nonce: bytes, ciphertext: bytes, associated_data: bytes = None) -> bytes:
    """
    Decrypt and verify ciphertext using AES-256-GCM.
    Raises cryptography.exceptions.InvalidTag if authentication fails or key is wrong.
    """
    aesgcm = AESGCM(key)
    return aesgcm.decrypt(nonce, ciphertext, associated_data)

def key_to_hex(key: bytes) -> str:
    """Convert binary key to hex representation."""
    return key.hex()

def hex_to_key(hex_str: str) -> bytes:
    """Convert hex string back to binary key."""
    return bytes.fromhex(hex_str)

def format_key_short(key: bytes) -> str:
    """Return a short prefix/suffix representation of a key for logging."""
    h = key.hex()
    return f"{h[:6]}...{h[-6:]}"

