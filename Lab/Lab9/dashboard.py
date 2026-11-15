"""
Interactive Web Dashboard for Secure RPC & KDC Authentication Proxy Simulator
Lecture 09 (Slides 39-40)

Features:
- Single-page responsive interactive UI (Flask + HTML5/CSS3/JavaScript)
- Real-time synchronized console trace log matching Slide 40
- Step-by-step interactive controls for Needham-Schroeder & RPC
- 1-Click automated full flow execution
- Anti-Replay attack simulation & verification
- HMAC-SHA256 message integrity tampering attack simulation
- Cryptographic packet inspector (Plaintext, AES-CBC, HMAC, Nonce)
"""

import sys
import os
import time
import json
import threading
import webbrowser
from flask import Flask, render_template, jsonify, request

from common import (
    KDC_HOST,
    KDC_PORT,
    SERVER_HOST,
    SERVER_PORT,
    DEFAULT_NONCE_RA,
    DEFAULT_NONCE_RB,
)
from kdc import KDCDaemon
from server import SecureResourceServer
from rpc_proxy import SecureRPCProxy

# Initialize Flask App
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
app = Flask(__name__, template_folder=os.path.join(BASE_DIR, "templates"))

# Thread-safe log collection
dashboard_logs = []
logs_lock = threading.Lock()

class StdoutLogInterceptor:
    def __init__(self, original_stdout):
        self.original_stdout = original_stdout

    def write(self, text):
        self.original_stdout.write(text)
        stripped = text.strip()
        if stripped:
            with logs_lock:
                dashboard_logs.append(stripped)

    def flush(self):
        self.original_stdout.flush()

sys.stdout = StdoutLogInterceptor(sys.stdout)

# Global Service Instances
kdc_instance = None
server_instance = None
proxy_instance = None
last_packet_info = None


def ensure_services_running():
    global kdc_instance, server_instance, proxy_instance
    if kdc_instance is None:
        kdc_instance = KDCDaemon(host=KDC_HOST, port=KDC_PORT)
        t_kdc = threading.Thread(target=kdc_instance.start, daemon=True)
        t_kdc.start()
        time.sleep(0.3)

    if server_instance is None:
        server_instance = SecureResourceServer(host=SERVER_HOST, port=SERVER_PORT)
        t_srv = threading.Thread(target=server_instance.start, daemon=True)
        t_srv.start()
        time.sleep(0.3)

    if proxy_instance is None:
        proxy_instance = SecureRPCProxy(
            kdc_host=KDC_HOST,
            kdc_port=KDC_PORT,
            server_host=SERVER_HOST,
            server_port=SERVER_PORT
        )


@app.route("/")
def index():
    ensure_services_running()
    return render_template("index.html")


@app.route("/api/logs")
def get_logs():
    since = request.args.get("since", 0, type=int)
    with logs_lock:
        new_logs = dashboard_logs[since:]
        next_idx = len(dashboard_logs)

    balance = server_instance.resources.get("Balance", 0) if server_instance else 0
    seen_count = len(server_instance.seen_nonces) if server_instance else 0
    k_ab_hex = proxy_instance.session_key.hex() if (proxy_instance and proxy_instance.session_key) else None
    is_connected = proxy_instance.is_connected if proxy_instance else False

    status_data = {
        "balance": balance,
        "seen_nonces_count": seen_count,
        "k_ab": k_ab_hex,
        "is_connected": is_connected,
        "last_packet": last_packet_info,
    }

    return jsonify({
        "logs": new_logs,
        "next_index": next_idx,
        "status": status_data
    })


@app.route("/api/step/kdc", methods=["POST"])
def step_kdc():
    ensure_services_running()
    data = request.get_json() or {}
    nonce_a = data.get("nonce_a", DEFAULT_NONCE_RA)
    try:
        success = proxy_instance.authenticate_with_kdc(nonce_a=nonce_a)
        return jsonify({"status": "SUCCESS", "authenticated": success})
    except Exception as e:
        print(f"[CLIENT ERROR] KDC Auth Failed: {e}", flush=True)
        return jsonify({"status": "ERROR", "message": str(e)}), 400


@app.route("/api/step/handshake", methods=["POST"])
def step_handshake():
    ensure_services_running()
    data = request.get_json() or {}
    nonce_b = data.get("nonce_b", DEFAULT_NONCE_RB)
    try:
        success = proxy_instance.establish_channel_with_server(challenge_hint=nonce_b)
        return jsonify({"status": "SUCCESS", "connected": success})
    except Exception as e:
        print(f"[CLIENT ERROR] Server Handshake Failed: {e}", flush=True)
        return jsonify({"status": "ERROR", "message": str(e)}), 400


@app.route("/api/rpc", methods=["POST"])
def execute_rpc():
    global last_packet_info
    ensure_services_running()
    data = request.get_json() or {}
    method = data.get("method", "Write")
    params = data.get("params", ["Balance", 500])

    try:
        res = proxy_instance.call(method, *params)
        
        # Capture packet for inspector
        if proxy_instance.last_sent_packet:
            last_packet_info = {
                "plaintext": {"method": method, "params": params},
                "payload": proxy_instance.last_sent_packet["payload"][:40] + "...",
                "hmac": proxy_instance.last_sent_packet["hmac"],
                "nonce": server_instance.resources.get("last_nonce", "Dynamic"),
            }
        return jsonify({"status": "SUCCESS", "result": res})
    except Exception as e:
        print(f"[CLIENT ERROR] RPC Execution Failed: {e}", flush=True)
        return jsonify({"status": "ERROR", "message": str(e)}), 400


@app.route("/api/attack/replay", methods=["POST"])
def attack_replay():
    ensure_services_running()
    try:
        res = proxy_instance.replay_last_rpc()
        return jsonify({"status": "SUCCESS", "response": res})
    except Exception as e:
        print(f"[CLIENT ERROR] Replay test failed: {e}", flush=True)
        return jsonify({"status": "ERROR", "message": str(e)}), 400


@app.route("/api/attack/tamper", methods=["POST"])
def attack_tamper():
    ensure_services_running()
    try:
        res = proxy_instance.send_tampered_rpc("Write", "Balance", 999999)
        return jsonify({"status": "SUCCESS", "response": res})
    except Exception as e:
        print(f"[CLIENT ERROR] Tamper test failed: {e}", flush=True)
        return jsonify({"status": "ERROR", "message": str(e)}), 400


@app.route("/api/run-all", methods=["POST"])
def run_all():
    """Runs the complete Slide 40 sequence step-by-step with realistic delays."""
    global last_packet_info
    ensure_services_running()

    def worker():
        try:
            print("\n>>> STARTING AUTOMATED SEQUENCE (SLIDE 40 TRACE) <<<", flush=True)
            time.sleep(0.3)
            proxy_instance.authenticate_with_kdc(nonce_a=DEFAULT_NONCE_RA)
            time.sleep(0.4)
            proxy_instance.establish_channel_with_server(challenge_hint=DEFAULT_NONCE_RB)
            time.sleep(0.4)
            proxy_instance.Write("Balance", 500)
            time.sleep(0.4)
            proxy_instance.Read("Balance")
            time.sleep(0.5)

            # Attack Tests
            print("\n--- ATTACK TEST 1: REPLAY OLD RPC PACKET ---", flush=True)
            proxy_instance.replay_last_rpc()
            time.sleep(0.5)

            print("\n--- ATTACK TEST 2: MITM CIPHERTEXT TAMPERING ---", flush=True)
            proxy_instance.send_tampered_rpc("Write", "Balance", 999999)
            time.sleep(0.3)
            print(">>> AUTOMATED SEQUENCE COMPLETE <<<\n", flush=True)
        except Exception as e:
            print(f"[ERROR IN RUN-ALL] {e}", flush=True)

    t = threading.Thread(target=worker, daemon=True)
    t.start()
    return jsonify({"status": "STARTED"})


@app.route("/api/reset", methods=["POST"])
def reset():
    global proxy_instance, last_packet_info
    with logs_lock:
        dashboard_logs.clear()

    if server_instance:
        server_instance.resources = {"Balance": 0}
        server_instance.seen_nonces.clear()

    if proxy_instance:
        proxy_instance.close()
        proxy_instance = SecureRPCProxy(
            kdc_host=KDC_HOST,
            kdc_port=KDC_PORT,
            server_host=SERVER_HOST,
            server_port=SERVER_PORT
        )

    last_packet_info = None
    print("[SYSTEM] All states, nonces, and session keys have been reset.", flush=True)
    return jsonify({"status": "RESET_COMPLETE"})


def start_dashboard():
    ensure_services_running()
    port = 5000
    url = f"http://127.0.0.1:{port}"
    print(f"\n=======================================================", flush=True)
    print(f"🚀 SECURE RPC INTERACTIVE DASHBOARD RUNNING", flush=True)
    print(f"👉 Open in browser: {url}", flush=True)
    print(f"=======================================================\n", flush=True)

    # Open browser automatically after 0.8s
    threading.Timer(0.8, lambda: webbrowser.open(url)).start()
    app.run(host="127.0.0.1", port=port, debug=False, use_reloader=False)


if __name__ == "__main__":
    start_dashboard()

