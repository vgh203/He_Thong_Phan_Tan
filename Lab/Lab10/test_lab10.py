"""
test_lab10.py
Pytest unit and integration test suite for Secure Group Multicast & ABAC Policy Simulator.
Covers:
  - AES-256-GCM encryption and authentication validation
  - LKH tree construction (N=8, h=3, 15 nodes)
  - Forward Secrecy Join rekeying (h=3 blocks)
  - Backward Secrecy Leave rekeying (d*h=6 blocks)
  - ABAC Policy engine rules (Role + Time boundaries)
  - Security Verification Checklist
"""

import pytest
from crypto_utils import generate_key_256, encrypt_aes_gcm, decrypt_aes_gcm
from lkh_tree import LKHTree
from abac_engine import ABACPolicyEngine
from cryptography.exceptions import InvalidTag

def test_aes_gcm_correctness():
    """Verify AES-256-GCM encrypts, authenticates, and decrypts accurately."""
    key = generate_key_256()
    assert len(key) == 32
    plaintext = b"Secret Group Payload Data"
    nonce, ciphertext = encrypt_aes_gcm(key, plaintext)

    assert len(nonce) == 12
    assert len(ciphertext) == len(plaintext) + 16  # Ciphertext + 16-byte GCM tag

    decrypted = decrypt_aes_gcm(key, nonce, ciphertext)
    assert decrypted == plaintext

def test_aes_gcm_wrong_key_fails():
    """Verify decryption fails when an incorrect or stale key is provided."""
    key1 = generate_key_256()
    key2 = generate_key_256()
    nonce, ct = encrypt_aes_gcm(key1, b"Confidential")

    with pytest.raises(InvalidTag):
        decrypt_aes_gcm(key2, nonce, ct)

def test_lkh_tree_structure():
    """Verify tree initialization properties for N=8, height=3."""
    tree = LKHTree(num_members=8)
    assert tree.height == 3
    assert tree.degree == 2
    assert len(tree.nodes) == 15  # 1 root + 6 internal + 8 leaves

    # Verify client leaf assignments
    for i in range(1, 9):
        cid = f"CLIENT_{i}"
        leaf_id = tree.client_to_leaf[cid]
        assert leaf_id == 7 + i
        path = tree.get_path_to_root(leaf_id)
        # Each client path contains h + 1 = 4 nodes (leaf -> parent -> ancestor -> root)
        assert len(path) == 4
        assert path[-1] == 1  # Root node

def test_lkh_join_forward_secrecy():
    """Verify dynamic JOIN rekeys path to root producing h=3 encrypted blocks."""
    tree = LKHTree(num_members=8)
    for i in [1, 2, 4, 5, 6, 7, 8]:
        tree.register_initial_member(f"CLIENT_{i}")

    old_root_key = tree.root_key

    # CLIENT_3 joins
    rekey_msg, c3_keys = tree.handle_join("CLIENT_3")

    assert rekey_msg["msg_type"] == "JOIN"
    assert rekey_msg["blocks_count"] == 3  # Exactly h = 3 blocks
    assert len(rekey_msg["rekey_blocks"]) == 3

    # New root key has been updated
    assert tree.root_key != old_root_key

    # New member received 4 path keys
    assert len(c3_keys) == 4
    assert c3_keys[1] == tree.root_key

def test_lkh_leave_backward_secrecy():
    """Verify dynamic LEAVE rekeys path producing d*h=6 encrypted blocks."""
    tree = LKHTree(num_members=8)
    for i in range(1, 9):
        tree.register_initial_member(f"CLIENT_{i}")

    old_root_key = tree.root_key
    c7_keys = tree.get_keys_for_client("CLIENT_7")

    # CLIENT_7 leaves
    rekey_msg = tree.handle_leave("CLIENT_7")

    assert rekey_msg["msg_type"] == "LEAVE"
    assert rekey_msg["blocks_count"] == 6  # Exactly d*h = 2*3 = 6 blocks
    assert rekey_msg["revoked_client_id"] == "CLIENT_7"
    assert not tree.nodes[tree.client_to_leaf["CLIENT_7"]].is_active

    # Root key is refreshed
    new_root_key = tree.root_key
    assert new_root_key != old_root_key

    # Verification: Old root key held by CLIENT_7 cannot decrypt messages encrypted under new_root_key
    nonce, ct = encrypt_aes_gcm(new_root_key, b"Message after CLIENT_7 left")
    with pytest.raises(InvalidTag):
        decrypt_aes_gcm(c7_keys[1], nonce, ct)

def test_abac_policy_engine_evaluation():
    """Verify ABAC rules: ALLOW IF Role == 'Publisher' AND 08:00 <= Time <= 18:00."""
    engine = ABACPolicyEngine()

    # Case 1: Valid Publisher during working hours -> ALLOW
    res1 = engine.evaluate(
        subject={"id": "CLIENT_1", "role": "Publisher"},
        action="PUBLISH",
        environment={"time": "10:30"}
    )
    assert res1.allowed is True
    assert "PASSED" in res1.reason

    # Case 2: Boundary Start (08:00) -> ALLOW
    res2 = engine.evaluate(
        subject={"id": "CLIENT_1", "role": "Publisher"},
        action="PUBLISH",
        environment={"time": "08:00"}
    )
    assert res2.allowed is True

    # Case 3: Boundary End (18:00) -> ALLOW
    res3 = engine.evaluate(
        subject={"id": "CLIENT_1", "role": "Publisher"},
        action="PUBLISH",
        environment={"time": "18:00"}
    )
    assert res3.allowed is True

    # Case 4: Role violation (Subscriber) -> DENY
    res4 = engine.evaluate(
        subject={"id": "CLIENT_2", "role": "Subscriber"},
        action="PUBLISH",
        environment={"time": "11:00"}
    )
    assert res4.allowed is False
    assert "Role violation" in res4.reason

    # Case 5: Time violation - before hours (07:45) -> DENY
    res5 = engine.evaluate(
        subject={"id": "CLIENT_1", "role": "Publisher"},
        action="PUBLISH",
        environment={"time": "07:45"}
    )
    assert res5.allowed is False
    assert "Time boundary violation" in res5.reason

    # Case 6: Time violation - after hours (19:30) -> DENY
    res6 = engine.evaluate(
        subject={"id": "CLIENT_1", "role": "Publisher"},
        action="PUBLISH",
        environment={"time": "19:30"}
    )
    assert res6.allowed is False
    assert "Time boundary violation" in res6.reason

    # Case 7: Action violation -> DENY
    res7 = engine.evaluate(
        subject={"id": "CLIENT_1", "role": "Publisher"},
        action="DELETE",
        environment={"time": "12:00"}
    )
    assert res7.allowed is False

def test_dashboard_api_endpoints():
    """Verify Flask dashboard endpoints: state, join, leave, publish, verify, reset."""
    from dashboard.app import app
    client = app.test_client()

    # 1. Test index page
    res_index = client.get("/")
    assert res_index.status_code == 200

    # 2. Test get state
    res_state = client.get("/api/state")
    assert res_state.status_code == 200
    state_json = res_state.get_json()
    assert state_json["status"] == "OK"
    assert "tree" in state_json
    assert len(state_json["members"]) == 8

    # 3. Test Join CLIENT_3
    res_join = client.post("/api/join", json={"client_id": "CLIENT_3"})
    assert res_join.status_code == 200
    join_json = res_join.get_json()
    assert join_json["status"] == "OK"
    assert join_json["rekey_msg"]["blocks_count"] == 3

    # 4. Test Leave CLIENT_7
    res_leave = client.post("/api/leave", json={"client_id": "CLIENT_7"})
    assert res_leave.status_code == 200
    leave_json = res_leave.get_json()
    assert leave_json["status"] == "OK"
    assert leave_json["rekey_msg"]["blocks_count"] == 6

    # 5. Test Publish with ABAC PASS
    res_pub = client.post("/api/publish", json={
        "client_id": "CLIENT_1",
        "role": "Publisher",
        "time": "14:00",
        "payload": "Test Broadcast"
    })
    assert res_pub.status_code == 200
    pub_json = res_pub.get_json()
    assert pub_json["status"] == "OK"
    assert pub_json["decision"]["allowed"] is True

    # 6. Test Publish with ABAC DENY (Subscriber)
    res_pub_deny = client.post("/api/publish", json={
        "client_id": "CLIENT_2",
        "role": "Subscriber",
        "time": "14:00",
        "payload": "Test Broadcast"
    })
    assert res_pub_deny.status_code == 200
    pub_deny_json = res_pub_deny.get_json()
    assert pub_deny_json["status"] == "DENIED"

    # 7. Test Verification suite
    res_verify = client.post("/api/verify")
    assert res_verify.status_code == 200
    verify_json = res_verify.get_json()
    assert verify_json["all_passed"] is True
    assert len(verify_json["results"]) == 4

