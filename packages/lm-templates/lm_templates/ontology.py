from __future__ import annotations
from dataclasses import dataclass
from typing import List, Optional, Iterable, Tuple, Dict, Any
import re

# ---- 데이터 모델 -------------------------------------------------------------

@dataclass
class ItemRule:
    """
    한 결산 비목(예: '회의비>간담회비')에 대한 규칙.
    """
    category: str                    # "대분류>소분류" 고정 포맷
    keywords_any: List[str]          # 하나라도 포함되면 가산점
    keywords_all: List[str] = None   # 모두 포함되어야 추가 가산점
    merchant_hint: List[str] = None  # 상호/브랜드 힌트
    amount_min: Optional[int] = None
    amount_max: Optional[int] = None
    vat_required: Optional[bool] = None
    notes: Optional[str] = None      # 정책 메모/주의사항(감사 노트)

@dataclass
class Ontology:
    rules: List[ItemRule]

# ---- 유틸: 카테고리 표준화/검증 ---------------------------------------------

_DELIM = ">"

def canonical_category(cat: str | Tuple[str, str]) -> str:
    """
    카테고리 표준화. ('회의비','간담회비') -> '회의비>간담회비'
    """
    if isinstance(cat, tuple):
        return f"{cat[0]}{_DELIM}{cat[1]}"
    s = str(cat).strip()
    return s.replace(" -> ", _DELIM).replace("/", _DELIM)

def validate(onto: Ontology) -> List[str]:
    """
    룰 세트를 빠르게 검증해 경고 리스트를 반환.
    - 중복 카테고리
    - 빈 키워드
    - 금액 범위 이상/이하 이상치
    """
    warnings: List[str] = []
    seen = set()
    for i, r in enumerate(onto.rules):
        cat = canonical_category(r.category)
        if _DELIM not in cat:
            warnings.append(f"[rule#{i}] category 포맷 권장: '대분류>소분류' (현재: {cat})")
        if cat in seen:
            warnings.append(f"[rule#{i}] category 중복: {cat}")
        seen.add(cat)

        if not r.keywords_any:
            warnings.append(f"[rule#{i}] keywords_any 비어있음: {cat}")

        if (r.amount_min is not None and r.amount_max is not None
            and r.amount_min > r.amount_max):
            warnings.append(f"[rule#{i}] amount_min > amount_max: {cat}")

    return warnings

# ---- MVP 온톨로지 -----------------------------------------------------------

DEFAULT_ONTOLOGY = Ontology(rules=[
    # 회의/간담회
    ItemRule(category="회의비>간담회비",
             keywords_any=["회의","간담","식사","음료","다과","카페","미팅"],
             merchant_hint=["스타벅스","이디야","투썸","파스쿠찌","메가커피","빽다방","카페","커피","베이커리"]),

    # 소모품
    ItemRule(category="운영비>소모품비",
             keywords_any=["복사용지","A4","토너","테이프","볼펜","형광펜","문구","스테이플러","지우개","노트","포스트잇","라벨지"],
             vat_required=True),

    # 인쇄/출력
    ItemRule(category="홍보비>인쇄비",
             keywords_any=["현수막","배너","전단","전단지","스티커","인쇄","출력","포스터","플랜카드"]),

    # 대여/대관
    ItemRule(category="사업비>대여료",
             keywords_any=["대여","렌탈","대관","장비대여","공간대여","마이크","프로젝터","천막","테이블","의자"]),

    # 통신
    ItemRule(category="운영비>통신비",
             keywords_any=["통신","요금","데이터","유심","USIM","유선","와이파이","인터넷","휴대폰"],
             amount_max=300000),

    # 택배/운송
    ItemRule(category="운영비>택배운송비",
             keywords_any=["택배","운송","배송","퀵","화물","발송","집하"],
             merchant_hint=["우체국","로젠","CJ","롯데","한진"]),

    # 기념품/굿즈
    ItemRule(category="행사비>기념품",
             keywords_any=["기념품","선물","굿즈","텀블러","에코백","스티커","키링","볼펜세트","머그컵"]),
])

# ---- (선택) 유지보수 팁 ------------------------------------------------------
# - 키워드는 '영수증에 실제로 찍히는 문자열' 위주로 구성하세요.
# - 분류가 애매한 경우 keywords_all에 좁히는 단서(예: '회의','영수증')를 추가하세요.
# - merchant_hint에는 브랜드/유형 단어(예: '카페','우체국')를 둡니다.
# - 통신비/대여료 등 금액이 과도하면 정책상 다른 절차가 필요한 경우 amount_max로 필터하세요.
