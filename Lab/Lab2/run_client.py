"""
Interactive Chord DHT client.

Usage
-----
  python run_client.py --connect-port 5001

Connect to any node in the ring; the DHT will route your
requests to the correct node automatically.

Commands
--------
  register <name> <ip> <port>  – register a name → address mapping
  lookup   <name>              – find a node's current address
  message  <name> <text>       – send a message to a named node
  info                         – print status of the connected node
  help                         – show this help
  quit                         – exit
"""
import argparse
import logging
import sys

from chord.network import send_rpc
from chord.finger_table import NodeInfo
from chord.utils import hash_key

logging.basicConfig(level=logging.WARNING)

HELP = """
  Commands:
    register <name> <ip> <port>   register a node name in the DHT
    lookup   <name>               look up a node by name
    message  <name> <text>        send a message to a named node
    info                          show status of the gateway node
    help                          print this help
    quit                          exit
"""


def main():
    parser = argparse.ArgumentParser(description="Chord DHT Client")
    parser.add_argument("--connect-ip",   default="127.0.0.1", help="Gateway node IP")
    parser.add_argument("--connect-port", type=int, required=True, help="Gateway node port")
    parser.add_argument("--name",         default="client",     help="Your client name (used as sender)")
    args = parser.parse_args()

    gw   = (args.connect_ip, args.connect_port)
    name = args.name

    print()
    print(f"  Chord DHT Client  —  connected to {gw[0]}:{gw[1]}")
    print(HELP)

    while True:
        try:
            line = input("client> ").strip()
        except (EOFError, KeyboardInterrupt):
            break

        if not line:
            continue

        parts = line.split(maxsplit=3)
        cmd   = parts[0].lower()

        # ── quit ──────────────────────────────────────────
        if cmd in ("quit", "exit", "q"):
            break

        # ── help ──────────────────────────────────────────
        elif cmd == "help":
            print(HELP)

        # ── register <name> <ip> <port> ───────────────────
        elif cmd == "register":
            if len(parts) < 4:
                print("  Usage: register <name> <ip> <port>")
                continue
            n_name, n_ip, n_port = parts[1], parts[2], int(parts[3])
            n_id  = hash_key(f"{n_ip}:{n_port}")
            entry = {"id": n_id, "ip": n_ip, "port": n_port, "name": n_name}
            resp  = send_rpc(*gw, {
                "type": "STORE",
                "key":  f"node:{n_name}",
                "value": entry,
            })
            if "error" in resp:
                print(f"  [ERROR] {resp['error']}")
            else:
                print(f"  Registered '{n_name}' → {n_ip}:{n_port}  (DHT id={n_id})")

        # ── lookup <name> ─────────────────────────────────
        elif cmd == "lookup":
            if len(parts) < 2:
                print("  Usage: lookup <name>")
                continue
            n_name = parts[1]
            resp   = send_rpc(*gw, {"type": "LOOKUP", "key": f"node:{n_name}"})
            if "error" in resp:
                print(f"  [ERROR] {resp['error']}")
            elif resp.get("value"):
                v = resp["value"]
                print(f"  Found '{n_name}':  id={v['id']}  address={v['ip']}:{v['port']}")
            else:
                print(f"  '{n_name}' not found in DHT.")

        # ── message <name> <text> ─────────────────────────
        elif cmd == "message":
            if len(parts) < 3:
                print("  Usage: message <name> <text>")
                continue
            target, text = parts[1], parts[2] if len(parts) > 2 else ""

            # Step 1: lookup target's current address
            resp = send_rpc(*gw, {"type": "LOOKUP", "key": f"node:{target}"})
            if "error" in resp or not resp.get("value"):
                print(f"  '{target}' not found in DHT.")
                continue

            v      = resp["value"]
            t_ip   = v["ip"]
            t_port = v["port"]

            # Step 2: deliver message directly
            resp2 = send_rpc(t_ip, t_port, {
                "type":    "MESSAGE",
                "from":    name,
                "content": text,
            })
            if "error" in resp2:
                print(f"  [ERROR] Could not reach {target} at {t_ip}:{t_port}")
            else:
                print(f"  Message delivered to '{target}' at {t_ip}:{t_port}")

        # ── info ──────────────────────────────────────────
        elif cmd == "info":
            resp = send_rpc(*gw, {"type": "GET_INFO"})
            if "error" in resp:
                print(f"  [ERROR] {resp['error']}")
            else:
                print()
                print(f"  Node  : '{resp.get('name')}'  (ID = {resp.get('id')})")
                print(f"  Addr  : {resp.get('ip')}:{resp.get('port')}")
                print(f"  Succ  : {resp.get('successor')}")
                print(f"  Pred  : {resp.get('predecessor')}")
                print(f"  Keys  : {resp.get('keys')}")
                print()
                print("  Finger Table:")
                print(resp.get("finger_table", "  (empty)"))
                print()

        else:
            print(f"  Unknown command '{cmd}'. Type 'help' for usage.")

    print("\n  Disconnected.")


if __name__ == "__main__":
    main()
