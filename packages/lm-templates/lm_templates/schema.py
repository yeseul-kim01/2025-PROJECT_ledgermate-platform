# packages/lm-templates/lm_templates/schema.py
from dataclasses import dataclass, field
from typing import List, Dict, Optional

@dataclass
class Column:
    raw_name: str                  # 원문 컬럼명 (예: "집행액", "결산액")
    canonical: str                 # 표준화명 (예: "actual_amount")
    index: int

@dataclass
class TableSchema:
    name: str                      # "결산표"/"지출내역" 등 감지 이름
    page: Optional[int] = None
    columns: List[Column] = field(default_factory=list)

@dataclass
class HeaderField:
    raw_key: str                   # "학기", "부서", "작성일" 등
    canonical: str                 # "term", "org_name", "doc_date" 등
    value_hint: Optional[str] = None

@dataclass
class TemplateSchema:
    file_id: str                   # 원본 파일 ID(or 경로 hash)
    detected_tables: List[TableSchema] = field(default_factory=list)
    detected_headers: List[HeaderField] = field(default_factory=list)
    confidence: float = 0.0        # 전반적 감지 신뢰도
    meta: Dict[str, str] = field(default_factory=dict)
