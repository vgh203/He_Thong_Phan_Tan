"""
Low-level TCP RPC helpers.

Wire format: 4-byte big-endian length  +  UTF-8 JSON payload.
"""
import socket
import json
import logging
from .config import TIMEOUT, BUFFER_SIZE

logger = logging.getLogger(__name__)


def send_rpc(ip: str, port: int,
             message: dict,
             timeout: float = TIMEOUT) -> dict:
    """
    Open a short-lived TCP connection, send *message* as JSON,
    and return the decoded JSON response.

    Returns ``{"error": "..."}`` on any failure so callers can
    check ``"error" in response`` without try/except.
    """
    sock = None
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(timeout)
        sock.connect((ip, port))

        # Send
        payload = json.dumps(message).encode("utf-8")
        sock.sendall(len(payload).to_bytes(4, "big") + payload)

        # Receive
        raw_len = _recv_exact(sock, 4)
        if not raw_len:
            return {"error": "empty response"}
        length   = int.from_bytes(raw_len, "big")
        raw_body = _recv_exact(sock, length)
        if not raw_body:
            return {"error": "truncated response"}
        return json.loads(raw_body.decode("utf-8"))

    except Exception as exc:
        logger.debug("RPC %s:%d failed: %s", ip, port, exc)
        return {"error": str(exc)}
    finally:
        if sock:
            try:
                sock.close()
            except Exception:
                pass


def _recv_exact(sock: socket.socket, n: int) -> bytes:
    """Receive exactly *n* bytes; returns empty bytes on EOF."""
    buf = b""
    while len(buf) < n:
        chunk = sock.recv(min(BUFFER_SIZE, n - len(buf)))
        if not chunk:
            return b""
        buf += chunk
    return buf
