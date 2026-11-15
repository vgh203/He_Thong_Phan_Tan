"""
abac_engine.py
Attribute-Based Access Control (ABAC) Policy Engine.
Evaluates multicast publication requests based on Subject, Action, Resource, and Environment attributes.

Mandatory Policy Rule:
  ALLOW IF Client.Role == 'Publisher' AND Time >= '08:00' AND Time <= '18:00'
  DENY OTHERWISE
"""

from typing import Dict, Any, Optional, Tuple
from datetime import datetime, time

class ABACDecision:
    """Represents the outcome of an ABAC policy evaluation."""
    def __init__(self, allowed: bool, reason: str, details: Optional[Dict[str, Any]] = None):
        self.allowed: bool = allowed
        self.reason: str = reason
        self.details: Dict[str, Any] = details or {}

    def to_dict(self) -> Dict[str, Any]:
        return {
            "allowed": self.allowed,
            "status": "PASSED" if self.allowed else "DENIED",
            "reason": self.reason,
            "details": self.details
        }

    def __repr__(self):
        return f"<ABACDecision allowed={self.allowed} reason='{self.reason}'>"

class ABACPolicyEngine:
    """
    ABAC Engine enforcing authorization rules on Multicast Dispatches.
    Standard attributes:
      - Subject: client_id, role ('Publisher' | 'Subscriber' | etc.)
      - Action: 'PUBLISH' | 'SUBSCRIBE' | 'QUERY'
      - Resource: 'MULTICAST_STREAM'
      - Environment: current_time (HH:MM or HH:MM:SS), simulated_time
    """
    def __init__(self, allowed_start_time: str = "08:00", allowed_end_time: str = "18:00"):
        self.start_time: time = self._parse_time(allowed_start_time)
        self.end_time: time = self._parse_time(allowed_end_time)

    def _parse_time(self, t_input: Any) -> time:
        """Parse string 'HH:MM' or 'HH:MM:SS' or datetime/time object into datetime.time."""
        if isinstance(t_input, time):
            return t_input
        if isinstance(t_input, datetime):
            return t_input.time()
        if isinstance(t_input, str):
            parts = t_input.strip().split(":")
            if len(parts) >= 2:
                hour = int(parts[0])
                minute = int(parts[1])
                second = int(parts[2]) if len(parts) > 2 else 0
                return time(hour, minute, second)
        raise ValueError(f"Invalid time format: {t_input}")

    def evaluate(
        self,
        subject: Dict[str, Any],
        action: str,
        resource: str = "MULTICAST_STREAM",
        environment: Optional[Dict[str, Any]] = None
    ) -> ABACDecision:
        """
        Evaluate access request.
        Rule: ALLOW IF Client.Role == 'Publisher' AND Time >= 08:00 AND Time <= 18:00
        """
        environment = environment or {}

        client_id = subject.get("id", "UNKNOWN_CLIENT")
        client_role = subject.get("role", "Subscriber")

        # Resolve evaluation time (can be passed via environment or default to current real time)
        raw_time = environment.get("time")
        if raw_time is None:
            now = datetime.now().time()
            eval_time = now
            time_str = now.strftime("%H:%M")
        else:
            eval_time = self._parse_time(raw_time)
            time_str = eval_time.strftime("%H:%M")

        details = {
            "client_id": client_id,
            "role": client_role,
            "action": action,
            "resource": resource,
            "evaluation_time": time_str,
            "working_hours": f"{self.start_time.strftime('%H:%M')} - {self.end_time.strftime('%H:%M')}"
        }

        # Check Action
        if action != "PUBLISH":
            return ABACDecision(
                allowed=False,
                reason=f"Action '{action}' is not permitted for multicast dispatch.",
                details=details
            )

        # Check Role attribute
        if client_role != "Publisher":
            return ABACDecision(
                allowed=False,
                reason=f"Role violation: Client '{client_id}' has role '{client_role}', but 'Publisher' is required.",
                details=details
            )

        # Check Time attribute: 08:00 <= eval_time <= 18:00
        if not (self.start_time <= eval_time <= self.end_time):
            return ABACDecision(
                allowed=False,
                reason=f"Time boundary violation: Request time {time_str} is outside working hours (08:00 - 18:00).",
                details=details
            )

        # All attributes satisfy policy!
        return ABACDecision(
            allowed=True,
            reason="Policy Evaluation PASSED: Role 'Publisher' verified and request within business hours (08:00-18:00).",
            details=details
        )

