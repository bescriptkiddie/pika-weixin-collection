from __future__ import annotations

from .models import FailureState


def build_failure_state(**kwargs):
    return FailureState(**kwargs)
