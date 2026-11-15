"""
Automated Test Suite for Secure RPC & KDC Authentication Proxy Simulator
Run with: pytest -v test_secure_rpc.py
"""

import threading
import time
import pytest
from common import (
    KDC_HOST,
    KDC_PORT,
    SERVER_HOST,
    SERVER_PORT,
    CLIENT_ID,
    SERVER_ID,
    KEY_A_CLIENT_KDC,
    KEY_B_SERVER_KDC,
)
from crypto_utils import (
    encrypt_aes_cbc,
    decrypt_aes_cbc,
    compute_hmac_sha256,
    verify_hmac_sha256,
    generate_session_key,
)
from kdc import KDCDaemon
from server import SecureResourceServer
from rpc_proxy import SecureRPCProxy


# -------------------------------------------------------------
# Unit Tests for Cryptographic Primitives
# -------------------------------------------------------------

def test_aes_cbc_encryption_decryption():
    key = generate_session_key(32)
    plaintext = "Confidential Banking Payload: Transfer $1,000,000 to Bob!"
    ciphertext = encrypt_aes_cbc(key, plaintext)

    assert ciphertext != plaintext
    decrypted = decrypt_aes_cbc(key, ciphertext)
    assert decrypted == plaintext


def test_hmac_sha256_verification_and_tamper_detection():
    key = generate_session_key(32)
    message = "Sensitive Transaction Metadata"
    mac = compute_hmac_sha256(key, message)

    # Valid check
    assert verify_hmac_sha256(key, message, mac) is True

    # Tampered message
    tampered_msg = message + "!"
    assert verify_hmac_sha256(key, tampered_msg, mac) is False

    # Tampered key
    wrong_key = generate_session_key(32)
    assert verify_hmac_sha256(wrong_key, message, mac) is False


# -------------------------------------------------------------
# Integration Tests for Full Distributed RPC System
# -------------------------------------------------------------

@pytest.fixture(scope="module")
def setup_services():
    """Starts KDC Daemon and Secure Resource Server in background threads."""
    kdc = KDCDaemon(port=9101)
    server = SecureResourceServer(port=9102)

    t_kdc = threading.Thread(target=kdc.start, daemon=True)
    t_server = threading.Thread(target=server.start, daemon=True)

    t_kdc.start()
    t_server.start()
    time.sleep(0.5)

    yield {
        "kdc_port": 9101,
        "server_port": 9102,
        "kdc": kdc,
        "server": server,
    }

    server.stop()
    kdc.stop()


def test_kdc_authentication_and_handshake(setup_services):
    cfg = setup_services
    proxy = SecureRPCProxy(
        kdc_port=cfg["kdc_port"],
        server_port=cfg["server_port"]
    )

    # Test KDC Authentication
    assert proxy.authenticate_with_kdc(nonce_a=12345) is True
    assert proxy.session_key is not None
    assert len(proxy.session_key) == 32
    assert proxy.ticket_bob is not None

    # Test Handshake with Server_Bob
    assert proxy.establish_channel_with_server(challenge_hint=98765) is True
    assert proxy.is_connected is True

    proxy.close()


def test_secure_rpc_read_write(setup_services):
    cfg = setup_services
    proxy = SecureRPCProxy(
        kdc_port=cfg["kdc_port"],
        server_port=cfg["server_port"]
    )
    proxy.authenticate_with_kdc(nonce_a=84920)
    proxy.establish_channel_with_server(challenge_hint=10492)

    # Test Write
    write_res = proxy.Write("Balance", 500)
    assert write_res["status"] == "SUCCESS"
    assert write_res["result"]["Balance"] == 500

    # Test Read
    read_res = proxy.Read("Balance")
    assert read_res["status"] == "SUCCESS"
    assert read_res["result"]["Balance"] == 500

    proxy.close()


def test_anti_replay_protection(setup_services):
    cfg = setup_services
    proxy = SecureRPCProxy(
        kdc_port=cfg["kdc_port"],
        server_port=cfg["server_port"]
    )
    proxy.authenticate_with_kdc(nonce_a=77777)
    proxy.establish_channel_with_server(challenge_hint=88888)

    # First legitimate RPC
    res1 = proxy.Write("Score", 100, custom_nonce=555123)
    assert res1["status"] == "SUCCESS"

    # Replay identical RPC packet
    replay_res = proxy.replay_last_rpc()
    assert replay_res["status"] == "ERROR"
    assert replay_res["code"] == "REPLAY_ATTACK_DETECTED"
    assert "already processed" in replay_res["message"]

    proxy.close()


def test_hmac_integrity_tampering(setup_services):
    cfg = setup_services
    proxy = SecureRPCProxy(
        kdc_port=cfg["kdc_port"],
        server_port=cfg["server_port"]
    )
    proxy.authenticate_with_kdc(nonce_a=11111)
    proxy.establish_channel_with_server(challenge_hint=22222)

    # Send tampered ciphertext
    tamper_res = proxy.send_tampered_rpc("Write", "Balance", 999999)
    assert tamper_res["status"] == "ERROR"
    assert tamper_res["code"] == "HMAC_VERIFICATION_FAILED"
    assert "HMAC integrity check failed" in tamper_res["message"]

    proxy.close()

