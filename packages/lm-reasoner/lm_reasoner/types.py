from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

@dataclass
class Receipt:
    raw_text: str
    fields: Dict[str, Any] = field(default_factory=dict)

@dataclass
class Evidence:
    kind: str
    ref: Any
    preview: str

@dataclass
class Recommendation:
    code: Optional[str]
    confidence: float
    rationale: str
    evidence: List[Evidence] = field(default_factory=list)
    provider: str = ""
