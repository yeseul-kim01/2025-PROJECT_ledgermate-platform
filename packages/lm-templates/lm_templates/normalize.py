# -*- coding: utf-8 -*-
"""
예산/결산 공통 표준 컬럼 Canon map
"""
CANON_MAP = {
    # 카테고리/코드/설명
    "비목": "category",
    "세목": "category",
    "코드": "budget_code",
    "내역": "description",
    "내용": "description",
    "세부내역": "description",

    # 금액(예산/결산)
    "예산액": "expected_amount",
    "편성액": "expected_amount",
    "금액(원)": "expected_amount",     # 일부 예산 템플릿
    "결산액": "actual_amount",
    "집행액": "actual_amount",

    # 보조
    "차액": "difference",
    "전년결산대비": "last_year_ratio",
    "전년 결산대비": "last_year_ratio",
    "비고": "note",

    # 날짜/상호
    "지출일자": "date",
    "집행일자": "date",
    "사용처": "merchant",
    "거래처": "merchant",
    "상호": "merchant",
}

HEADER_CANON_MAP = {
    # 문서 헤더(본문 키:값) → 표준 키
    "학기": "term",
    "부서": "org_name",
    "작성일": "doc_date",
    "작성자": "author",
}
