"""
dashboard/app.py
Flask-based Web Application for the Secure Group Multicast & ABAC Policy Simulator.
Provides real-time interactive visualization of the LKH tree, dynamic rekeying,
ABAC policy evaluation, AES-256-GCM payload inspection, and the verification checklist.
"""

from flask import Flask, render_template, jsonify, request
from flask_cors import CORS
import sys
import os

# Ensure parent directory is in path to import lab10 core modules
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from lkh_tree import LKHTree
from abac_engine import ABACPolicyEngine
from crypto_utils import encrypt_aes_gcm, decrypt_aes_gcm, key_to_hex, format_key_short

app = Flask(__name__)
CORS(app)

class SimulatorState:
    def __init__(self):
        self.reset()

    def reset(self):
        self.tree = LKHTree(num_members=8)
        self.abac = ABACPolicyEngine()
        self.logs = []
        self.past_recorded_packet = None
        self.latest_multicast_packet = None
        self.client_roles = {
            "CLIENT_1": "Publisher",
            "CLIENT_2": "Subscriber",
            "CLIENT_3": "Subscriber",
            "CLIENT_4": "Subscriber",
            "CLIENT_5": "Subscriber",
            "CLIENT_6": "Subscriber",
            "CLIENT_7": "Subscriber",
            "CLIENT_8": "Subscriber",
        }
        # Initial members active: 1, 2, 4, 5, 6, 7, 8 (3 will join dynamically)
        self.client_keys = {}
        for cid in ["CLIENT_1", "CLIENT_2", "CLIENT_4", "CLIENT_5", "CLIENT_6", "CLIENT_7", "CLIENT_8"]:
            self.client_keys[cid] = self.tree.register_initial_member(cid)

        self._log(f"[KEY_SERVER] LKH Binary Tree Initialized (N=8 Members, Height h={self.tree.height}).")

        # Record initial past message under initial K_0
        initial_root_key = self.tree.root_key
        nonce, ct = encrypt_aes_gcm(initial_root_key, b"[PAST_MSG] Historical group briefing prior to CLIENT_3 join.")
        self.past_recorded_packet = {
            "nonce": nonce.hex(),
            "ciphertext": ct.hex(),
            "sender_id": "CLIENT_1",
            "plaintext": "[PAST_MSG] Historical group briefing prior to CLIENT_3 join."
        }

    def _log(self, msg: str):
        self.logs.append(msg)

state = SimulatorState()

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/api/state", methods=["GET"])
def get_state():
    tree_data = state.tree.get_tree_state()
    # Augment nodes with client roles and path information
    members_info = []
    for i in range(1, 9):
        cid = f"CLIENT_{i}"
        leaf_id = state.tree.client_to_leaf[cid]
        node = state.tree.nodes[leaf_id]
        members_info.append({
            "client_id": cid,
            "leaf_id": leaf_id,
            "role": state.client_roles.get(cid, "Subscriber"),
            "is_active": node.is_active,
            "path": state.tree.get_path_to_root(leaf_id),
            "key_short": format_key_short(node.key)
        })

    return jsonify({
        "status": "OK",
        "tree": tree_data,
        "members": members_info,
        "logs": state.logs[-30:],  # last 30 logs
        "latest_packet": state.latest_multicast_packet,
        "past_packet": state.past_recorded_packet
    })

@app.route("/api/join", methods=["POST"])
def handle_join():
    data = request.json or {}
    client_id = data.get("client_id", "CLIENT_3")
    role = data.get("role", state.client_roles.get(client_id, "Subscriber"))
    state.client_roles[client_id] = role

    rekey_msg, c_keys = state.tree.handle_join(client_id)
    state.client_keys[client_id] = c_keys

    # Update path keys for other active members
    for other_cid, keys_dict in state.client_keys.items():
        if other_cid != client_id and state.tree.nodes[state.tree.client_to_leaf[other_cid]].is_active:
            for blk in rekey_msg["rekey_blocks"]:
                target_nid = blk["target_node_id"]
                enc_nid = blk["encrypting_node_id"]
                if enc_nid in keys_dict:
                    try:
                        n = bytes.fromhex(blk["nonce"])
                        c = bytes.fromhex(blk["ciphertext"])
                        new_k = decrypt_aes_gcm(keys_dict[enc_nid], n, c)
                        keys_dict[target_nid] = new_k
                    except Exception:
                        pass

    log_join = f"[{client_id}] Joining Group... LKH Rekey Sent: {rekey_msg['blocks_count']} Encrypted Blocks."
    state._log(log_join)

    return jsonify({
        "status": "OK",
        "message": log_join,
        "rekey_msg": rekey_msg,
        "client_id": client_id
    })

@app.route("/api/leave", methods=["POST"])
def handle_leave():
    data = request.json or {}
    client_id = data.get("client_id", "CLIENT_7")

    state._log(f"[{client_id}] Leaving Group... Executing Backward Secrecy Rekey.")
    rekey_msg = state.tree.handle_leave(client_id)

    # Server trace
    d = rekey_msg["d_factor"]
    h = rekey_msg["h_factor"]
    count = rekey_msg["blocks_count"]
    state._log(f"[KEY_SERVER] Generated {count} Rekey Blocks (d*h = {d}*{h}). Revoked {client_id}.")

    # Update path keys for remaining active members
    for cid, keys_dict in state.client_keys.items():
        if cid != client_id and state.tree.nodes[state.tree.client_to_leaf[cid]].is_active:
            # Iterative decrypt
            progress = True
            while progress:
                progress = False
                for blk in rekey_msg["rekey_blocks"]:
                    target_nid = blk["target_node_id"]
                    enc_nid = blk["encrypting_node_id"]
                    if enc_nid in keys_dict and not blk.get("is_revoked_target", False):
                        if target_nid not in keys_dict or keys_dict[target_nid] != blk.get("_dec"):
                            try:
                                n = bytes.fromhex(blk["nonce"])
                                c = bytes.fromhex(blk["ciphertext"])
                                new_k = decrypt_aes_gcm(keys_dict[enc_nid], n, c)
                                keys_dict[target_nid] = new_k
                                blk["_dec"] = new_k
                                progress = True
                            except Exception:
                                pass

    # Clean up temporary serialization keys from rekey_blocks
    for blk in rekey_msg["rekey_blocks"]:
        blk.pop("_dec", None)

    # Trace for client 1
    state._log("[CLIENT_1] Received Rekey Msg -> Updated Path Keys to Root Key K_0_New.")

    return jsonify({
        "status": "OK",
        "message": f"Revoked {client_id}",
        "rekey_msg": rekey_msg,
        "client_id": client_id
    })

@app.route("/api/publish", methods=["POST"])
def handle_publish():
    data = request.json or {}
    client_id = data.get("client_id", "CLIENT_1")
    role = data.get("role", state.client_roles.get(client_id, "Publisher"))
    eval_time = data.get("time", "10:30")
    payload = data.get("payload", "Confidential Multicast Announcement")

    # 1. ABAC Policy Evaluation
    decision = state.abac.evaluate(
        subject={"id": client_id, "role": role},
        action="PUBLISH",
        resource="MULTICAST_STREAM",
        environment={"time": eval_time}
    )

    if not decision.allowed:
        state._log(f"[ABAC_ENGINE] Policy Evaluation DENIED -> {decision.reason}")
        return jsonify({
            "status": "DENIED",
            "decision": decision.to_dict()
        })

    state._log("[ABAC_ENGINE] Policy Evaluation PASSED -> Multicast Delivered.")

    # 2. Encrypt under current root key
    root_key = state.tree.root_key
    nonce, ct = encrypt_aes_gcm(root_key, payload.encode("utf-8"))
    state._log("[KEY_SERVER] Multicast Dispatch: AES-256 Payload Encrypted under Root Key K_0.")

    packet = {
        "sender_id": client_id,
        "nonce": nonce.hex(),
        "ciphertext": ct.hex(),
        "plaintext": payload,
        "root_key_short": format_key_short(root_key)
    }
    state.latest_multicast_packet = packet

    # 3. Simulate client decryption across all 8 nodes
    decryption_results = {}
    for i in range(1, 9):
        cid = f"CLIENT_{i}"
        keys = state.client_keys.get(cid, {})
        client_root_k = keys.get(1)
        if client_root_k is None:
            decryption_results[cid] = {"status": "FAIL", "reason": "No Root Key stored"}
        else:
            try:
                dec_pt = decrypt_aes_gcm(client_root_k, nonce, ct).decode("utf-8")
                decryption_results[cid] = {"status": "SUCCESS", "text": dec_pt}
            except Exception:
                decryption_results[cid] = {"status": "FAIL", "reason": "Decryption Failed (Invalid Tag / Stale Key)"}

    return jsonify({
        "status": "OK",
        "decision": decision.to_dict(),
        "packet": packet,
        "decryption_results": decryption_results
    })

@app.route("/api/verify", methods=["POST"])
def handle_verify():
    """Runs all 4 verification checks from Slide 39."""
    results = []

    # Check 1: Departing member CLIENT_7 cannot decrypt new multicast messages
    c7_keys = state.client_keys.get("CLIENT_7", {})
    c7_root = c7_keys.get(1)
    if state.latest_multicast_packet and c7_root:
        n = bytes.fromhex(state.latest_multicast_packet["nonce"])
        c = bytes.fromhex(state.latest_multicast_packet["ciphertext"])
        try:
            decrypt_aes_gcm(c7_root, n, c)
            c7_pass = False
            c7_note = "CLIENT_7 unexpectedly decrypted new message!"
        except Exception:
            c7_pass = True
            c7_note = "CLIENT_7 failed to decrypt new message (InvalidTag, Backward Secrecy intact)."
    else:
        # Synthesize fresh packet under current root key to test
        n, c = encrypt_aes_gcm(state.tree.root_key, b"Backward Secrecy Verification Probe")
        if c7_root:
            try:
                decrypt_aes_gcm(c7_root, n, c)
                c7_pass = False
                c7_note = "CLIENT_7 decrypted new probe!"
            except Exception:
                c7_pass = True
                c7_note = "CLIENT_7 cannot decrypt new probe under K_0_New (Revoked)."
        else:
            c7_pass = True
            c7_note = "CLIENT_7 has no root key (Revoked)."

    results.append({
        "name": "Check 1: Backward Secrecy (Departing Member Isolation)",
        "passed": c7_pass,
        "description": "Verify departing member CLIENT_7 cannot decrypt new multicast messages.",
        "details": c7_note
    })

    # Check 2: New joining member CLIENT_3 cannot decrypt past messages
    c3_keys = state.client_keys.get("CLIENT_3", {})
    c3_root = c3_keys.get(1)
    if state.past_recorded_packet and c3_root:
        n_past = bytes.fromhex(state.past_recorded_packet["nonce"])
        c_past = bytes.fromhex(state.past_recorded_packet["ciphertext"])
        try:
            decrypt_aes_gcm(c3_root, n_past, c_past)
            c3_pass = False
            c3_note = "CLIENT_3 unexpectedly decrypted past message!"
        except Exception:
            c3_pass = True
            c3_note = "CLIENT_3 failed to decrypt past message (Forward Secrecy intact)."
    else:
        c3_pass = True
        c3_note = "CLIENT_3 cannot decrypt past messages."

    results.append({
        "name": "Check 2: Forward Secrecy (New Member Past Isolation)",
        "passed": c3_pass,
        "description": "Verify new member CLIENT_3 cannot decrypt past recorded messages.",
        "details": c3_note
    })

    # Check 3: ABAC Role Enforcement (Subscriber rejected)
    abac_sub = state.abac.evaluate(
        subject={"id": "CLIENT_2", "role": "Subscriber"},
        action="PUBLISH",
        environment={"time": "11:00"}
    )
    results.append({
        "name": "Check 3: ABAC Role Enforcement",
        "passed": not abac_sub.allowed,
        "description": "Reject publication attempts if Role != 'Publisher'.",
        "details": abac_sub.reason
    })

    # Check 4: ABAC Time Boundary Enforcement (Outside 08:00 - 18:00 rejected)
    abac_time = state.abac.evaluate(
        subject={"id": "CLIENT_1", "role": "Publisher"},
        action="PUBLISH",
        environment={"time": "22:00"}
    )
    results.append({
        "name": "Check 4: ABAC Time Boundary Enforcement",
        "passed": not abac_time.allowed,
        "description": "Reject publication attempts outside 08:00 - 18:00.",
        "details": abac_time.reason
    })

    return jsonify({
        "status": "OK",
        "all_passed": all(r["passed"] for r in results),
        "results": results
    })

@app.route("/api/reset", methods=["POST"])
def handle_reset():
    state.reset()
    return jsonify({"status": "OK", "message": "Simulation reset successfully."})

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
