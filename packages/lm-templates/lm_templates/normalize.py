CANON_MAP = {
  # 표 헤더 → 표준 컬럼
  "예산액": "expected_amount",
  "편성액": "expected_amount",
  "결산액": "actual_amount",
  "집행액": "actual_amount",
  "차액": "difference",
  "비목": "category",
  "세목": "category",
  "코드": "budget_code",
  "내역": "description",
  "내용": "description",
  "비고": "note",
  "지출일자": "date",
  "집행일자": "date",
  "사용처": "merchant",
  "거래처": "merchant",
  "상호": "merchant",
}
HEADER_CANON_MAP = {
  # 문서 헤더 필드
  "학기": "term",
  "부서": "org_name",
  "작성일": "doc_date",
  "작성자": "author",
}
