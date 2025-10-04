from __future__ import annotations
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field

class OcrPage(BaseModel):
    page: int
    text: str = ""

class OcrResult(BaseModel):
    filename: str
    pages: List[OcrPage] = Field(default_factory=list)
    full_text: str = ""        # 페이지 합본
    provider: str = "upstage"
    model: str = "ocr"
    meta: Dict[str, Any] = Field(default_factory=dict)  # 업스테이지 응답의 요약 메타

class OcrBundle(BaseModel):
    """저장 편의용: 정제 결과 + 원본 응답"""
    result: OcrResult
    raw: Dict[str, Any]
