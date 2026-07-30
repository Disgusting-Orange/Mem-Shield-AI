from dataclasses import dataclass
from typing import List

@dataclass
class TrustScoreResult:
    """Result of a memory‑write trust evaluation.

    Attributes
    ----------
    score: int
        Combined trust score (0‑100).
    reasons: List[str]
        Human‑readable reasons why the score was assigned.
    accepted: bool
        True if the score meets the configured threshold.
    """
    score: int
    reasons: List[str]
    accepted: bool
