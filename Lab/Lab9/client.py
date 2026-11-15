"""
Client App (Alice)
Uses SecureRPCProxy to authenticate with KDC and execute secure RPCs
against Server_Bob. Demonstrates normal execution, anti-replay protection,
and HMAC integrity verification.
"""

import time
import sys
from rpc_proxy import SecureRPCProxy
from common import DEFAULT_NONCE_RA, DEFAULT_NONCE_RB


def run_client(test_attacks: bool = True):
    print("=" * 70, flush=True)
    print("          STARTING CLIENT APP (ALICE) - SECURE RPC DEMO          ", flush=True)
    print("=" * 70, flush=True)

    proxy = SecureRPCProxy()

    try:
        # Step 1 & 2: Needham-Schroeder KDC Authentication
        proxy.authenticate_with_kdc(nonce_a=DEFAULT_NONCE_RA)
        time.sleep(0.1)

        # Step 3, 4, 5: Mutual Authentication Handshake with Server_Bob
        proxy.establish_channel_with_server(challenge_hint=DEFAULT_NONCE_RB)
        time.sleep(0.1)

        # Execute Secure RPC: Write('Balance', 500)
        res_write = proxy.Write("Balance", 500)
        time.sleep(0.1)
        print(f"[CLIENT] RPC Result: {res_write.get('result')}\n", flush=True)

        # Execute Secure RPC: Read('Balance')
        res_read = proxy.Read("Balance")
        time.sleep(0.1)
        print(f"[CLIENT] RPC Result: {res_read.get('result')}\n", flush=True)

        if test_attacks:
            print("-" * 70, flush=True)
            print(">>> DEMONSTRATION 1: ANTI-REPLAY ATTACK TEST <<<", flush=True)
            print("-" * 70, flush=True)
            print("[INFO] Simulating an attacker re-sending the earlier Write('Balance', 500) packet...", flush=True)
            replay_res = proxy.replay_last_rpc()
            time.sleep(0.1)
            print(f"[CLIENT] Server Response to Replayed Packet: {replay_res}", flush=True)
            if replay_res.get("code") == "REPLAY_ATTACK_DETECTED":
                print("[SUCCESS] Anti-Replay Protection verified: Server rejected replayed RPC packet!\n", flush=True)
            else:
                print("[WARNING] Anti-Replay protection did not reject packet.\n", flush=True)

            print("-" * 70, flush=True)
            print(">>> DEMONSTRATION 2: HMAC INTEGRITY TAMPERING ATTACK TEST <<<", flush=True)
            print("-" * 70, flush=True)
            print("[INFO] Simulating a Man-in-the-Middle attacker tampering with ciphertext in transit...", flush=True)
            tamper_res = proxy.send_tampered_rpc("Write", "Balance", 999999)
            time.sleep(0.1)
            print(f"[CLIENT] Server Response to Tampered Packet: {tamper_res}", flush=True)
            if tamper_res.get("code") == "HMAC_VERIFICATION_FAILED":
                print("[SUCCESS] Message Integrity verified: Server detected tampering and dropped packet!\n", flush=True)
            else:
                print("[WARNING] HMAC verification did not detect tampering.\n", flush=True)

    except Exception as e:
        print(f"[CLIENT ERROR] {e}", file=sys.stderr, flush=True)
    finally:
        proxy.close()
        print("=" * 70, flush=True)
        print("                 CLIENT APP EXECUTION COMPLETE                   ", flush=True)
        print("=" * 70, flush=True)


if __name__ == "__main__":
    run_client()
