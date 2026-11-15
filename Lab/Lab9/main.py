"""
Main Entry Point for Lab 9: Secure RPC & KDC Authentication Proxy Simulator
Runs the full Needham-Schroeder handshake, AES-CBC encrypted RPCs,
HMAC-SHA256 integrity checks, and attacks simulations (Anti-Replay & Tampering).
"""

import sys
from run_simulation import main

if __name__ == "__main__":
    main()
