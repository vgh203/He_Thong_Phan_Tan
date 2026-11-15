"""
Utility helpers: hashing and circular-ring arithmetic.
"""
import hashlib
from .config import RING_SIZE


def hash_key(key: str) -> int:
    """Hash an arbitrary string to a ring position [0, RING_SIZE)."""
    digest = hashlib.sha256(key.encode("utf-8")).hexdigest()
    return int(digest, 16) % RING_SIZE


def node_id_from_address(ip: str, port: int) -> int:
    """Derive a stable node ID from its (ip, port) pair."""
    return hash_key(f"{ip}:{port}")


def in_range(x: int, a: int, b: int, include_b: bool = True) -> bool:
    """
    Test whether x lies in the half-open interval (a, b] on the
    circular ring [0, RING_SIZE).

    Parameters
    ----------
    x         : value to test
    a         : left  endpoint (exclusive)
    b         : right endpoint (inclusive when include_b=True)
    include_b : if False the interval is open on both sides (a, b)
    """
    a = a % RING_SIZE
    b = b % RING_SIZE
    x = x % RING_SIZE

    # Degenerate case: the whole ring
    if a == b:
        return True

    if include_b:
        if a < b:
            return a < x <= b
        else:                   # wrap-around  e.g. (60, 5]
            return x > a or x <= b
    else:
        if a < b:
            return a < x < b
        else:
            return x > a or x < b
