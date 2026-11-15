"""
NodeInfo dataclass and FingerTable for the Chord DHT.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Optional
from .config import M, RING_SIZE


@dataclass
class NodeInfo:
    """Lightweight descriptor for a remote Chord node."""
    id:   int
    ip:   str
    port: int
    name: str = ""

    # ── Serialisation ───────────────────────────────────────
    def to_dict(self) -> dict:
        return {"id": self.id, "ip": self.ip,
                "port": self.port, "name": self.name}

    @classmethod
    def from_dict(cls, d: dict) -> "NodeInfo":
        return cls(id=d["id"], ip=d["ip"],
                   port=d["port"], name=d.get("name", ""))

    # ── Helpers ─────────────────────────────────────────────
    def address(self) -> tuple[str, int]:
        return (self.ip, self.port)

    def __eq__(self, other) -> bool:
        if other is None:
            return False
        return self.id == other.id

    def __repr__(self) -> str:
        label = f"'{self.name}'" if self.name else str(self.id)
        return f"NodeInfo({label}, {self.ip}:{self.port})"


class FingerTable:
    """
    Chord finger table.

    finger[i] points to successor( (node_id + 2^i) mod 2^M )
    Enables O(log N) key lookups.
    """

    def __init__(self, local_id: int):
        self.local_id = local_id
        # Pre-compute the start of each finger interval
        self.starts: list[int] = [
            (local_id + 2 ** i) % RING_SIZE for i in range(M)
        ]
        self.fingers: list[Optional[NodeInfo]] = [None] * M

    # ── Access ──────────────────────────────────────────────
    def __getitem__(self, i: int) -> Optional[NodeInfo]:
        return self.fingers[i]

    def __setitem__(self, i: int, value: Optional[NodeInfo]):
        self.fingers[i] = value

    @property
    def successor(self) -> Optional[NodeInfo]:
        """Finger[0] is always the immediate successor."""
        return self.fingers[0]

    @successor.setter
    def successor(self, value: Optional[NodeInfo]):
        self.fingers[0] = value

    # ── Display ─────────────────────────────────────────────
    def display(self) -> str:
        header = f"  {'i':>2}  {'start':>6}  {'node_id':>8}  {'address':>22}  name"
        sep    = "  " + "-" * 56
        rows   = [header, sep]
        for i in range(M):
            f = self.fingers[i]
            if f:
                addr = f"{f.ip}:{f.port}"
                rows.append(
                    f"  {i:>2}  {self.starts[i]:>6}  {f.id:>8}  {addr:>22}  {f.name}"
                )
            else:
                rows.append(
                    f"  {i:>2}  {self.starts[i]:>6}  {'—':>8}  {'—':>22}"
                )
        return "\n".join(rows)
