from __future__ import annotations

import math
import re
from collections import Counter


def normalize_text(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").strip().lower())


def build_terms(text: str) -> list[str]:
    normalized = normalize_text(text)
    if not normalized:
        return []

    ascii_terms = [token for token in normalized.split(" ") if token]
    compact = normalized.replace(" ", "")
    cjk_terms = [compact[i:i + 2] for i in range(max(len(compact) - 1, 0))]
    return ascii_terms + cjk_terms


def vectorize_text(text: str) -> dict[str, float]:
    counts = Counter(build_terms(text))
    if not counts:
        return {}
    norm = math.sqrt(sum(value * value for value in counts.values())) or 1.0
    return {key: value / norm for key, value in counts.items()}


def cosine_similarity(vec_a: dict[str, float], vec_b: dict[str, float]) -> float:
    if not vec_a or not vec_b:
        return 0.0
    if len(vec_a) > len(vec_b):
        vec_a, vec_b = vec_b, vec_a
    return sum(value * vec_b.get(key, 0.0) for key, value in vec_a.items())
