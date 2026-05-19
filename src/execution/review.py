from __future__ import annotations

from .models import ReviewPacket
from .store import build_packet_id


def build_review_packet(kind: str, run_id: str, task_id: str, reason: str, candidate_payload: dict, suggested_action: str = "") -> ReviewPacket:
    return ReviewPacket(
        packet_id=build_packet_id(kind),
        run_id=run_id,
        task_id=task_id,
        kind=kind,
        reason=reason,
        candidate_payload=candidate_payload,
        suggested_action=suggested_action,
    )
