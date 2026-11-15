"""
Start a Chord DHT node.

Usage examples
--------------
# First node (creates a new ring):
  python run_node.py --port 5001 --name alice

# Subsequent nodes (join existing ring):
  python run_node.py --port 5002 --name bob   --join-ip 127.0.0.1 --join-port 5001
  python run_node.py --port 5003 --name carol --join-ip 127.0.0.1 --join-port 5001

Interactive commands while running
-----------------------------------
  status   – print finger table and node state
  register – re-register this node's name in the DHT
  quit     – gracefully stop
"""
import argparse
import logging
import sys
import time

from chord.node import ChordNode

# ── Logging ────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  [%(levelname)-5s]  %(message)s",
    datefmt="%H:%M:%S",
)


def main():
    parser = argparse.ArgumentParser(
        description="Chord DHT Node",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("--ip",        default="127.0.0.1", help="Bind IP (default: 127.0.0.1)")
    parser.add_argument("--port",      type=int, required=True, help="Bind port")
    parser.add_argument("--name",      default="",           help="Human-readable node name")
    parser.add_argument("--join-ip",   default=None,         help="IP of an existing ring node")
    parser.add_argument("--join-port", type=int, default=None, help="Port of an existing ring node")
    args = parser.parse_args()

    node = ChordNode(ip=args.ip, port=args.port, name=args.name)

    try:
        node.start(
            bootstrap_ip=args.join_ip,
            bootstrap_port=args.join_port,
        )
    except RuntimeError as exc:
        print(f"[ERROR] {exc}")
        sys.exit(1)

    label = f"'{args.name}'" if args.name else "(unnamed)"
    print()
    print(f"  Chord node {label} started")
    print(f"  ID   : {node.id}")
    print(f"  Addr : {args.ip}:{args.port}")
    if args.join_ip:
        print(f"  Joined ring via {args.join_ip}:{args.join_port}")
    else:
        print("  Created new ring (bootstrap node)")
    print()
    print("  Commands: status | register | quit")
    print()

    try:
        while True:
            try:
                cmd = input(f"[{args.name or node.id}]> ").strip().lower()
            except EOFError:
                break

            if cmd == "status":
                node.print_status()
            elif cmd == "register":
                node.register()
                print("  Re-registered in DHT.")
            elif cmd == "quit":
                break
            elif cmd == "":
                pass
            else:
                print(f"  Unknown command: '{cmd}'")
    except KeyboardInterrupt:
        pass

    print("\n  Stopping node...")
    node.stop()
    print("  Done.")


if __name__ == "__main__":
    main()
