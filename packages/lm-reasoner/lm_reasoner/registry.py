from __future__ import annotations
from typing import Dict, Type
from .strategies.base import RecommenderStrategy

_REG: Dict[str, Type[RecommenderStrategy]] = {}

def register(cls: Type[RecommenderStrategy]):
    _REG[cls.__name__] = cls
    return cls

def build(name: str, **kwargs) -> RecommenderStrategy:
    return _REG[name](**kwargs)