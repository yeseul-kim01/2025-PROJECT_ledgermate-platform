# packages/lm-reasoner/lm_reasoner/strategies/base.py
from __future__ import annotations
from abc import ABC, abstractmethod
from typing import List
from ..types import Receipt, Recommendation

class RecommenderStrategy(ABC):
    name: str = "base"

    @abstractmethod
    def recommend(self, *, receipt: Receipt, policy_id: str, k: int = 8) -> Recommendation:
        ...
