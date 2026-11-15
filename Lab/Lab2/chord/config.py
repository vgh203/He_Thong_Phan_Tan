# ─── Chord DHT Configuration ───────────────────────────────
# M: Number of bits in node ID  →  Ring size = 2^M
# For demo with a few nodes, M=6 (ring size 64) is plenty.
M = 6
RING_SIZE = 2 ** M          # 64 slots on the ring

# Maintenance intervals (seconds)
STABILIZE_INTERVAL   = 5    # How often stabilize() runs
FIX_FINGERS_INTERVAL = 7    # How often fix_fingers() runs
CHECK_PRED_INTERVAL  = 10   # How often check_predecessor() runs

# Network
TIMEOUT     = 4.0   # RPC call timeout (seconds)
BUFFER_SIZE = 65536 # TCP receive buffer
